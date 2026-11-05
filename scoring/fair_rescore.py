"""Re-score saved RuVLLM paired runs under three markers: strict, format-tolerant and fair.

Reads model text only. Never executes tool calls or generated code.

  strict  Reimplements upstream ruvllm measurement.py grade(). Its counts must match
          upstream report.json, or this script stops (a self-check that we parse
          the same way before we change anything).
  format  Also accepts True/False booleans and ignores trailing whitespace
          in string arguments (e.g. a file's final newline).
  fair    Also accepts extra *optional* arguments that do not change what the
          tool call does: Bash.timeout, Bash.description, Grep.-n.
          Arguments that change results (Grep.glob, Read.limit/offset,
          Edit.replace_all) still count as wrong.

Derived from ruvnet/ruvllm (Apache 2.0), experiments/model-improvement/measurement.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path

MARKERS = ('strict', 'format', 'fair')
HARMLESS_OPTIONAL = {('Bash', 'timeout'), ('Bash', 'description'), ('Grep', '-n')}
RUNS = {
    'v3 confirmation: base vs coding-4b': ('frozen/v3', 'results/qwen35-4b-adapter-confirmation-v3'),
    'v4 held-out: base vs coding-4b': ('frozen/v4', 'results/qwen35-4b-heldout-v4-coding-4b'),
    'v5 held-out: base vs coding-4b-r2': ('frozen/v5', 'results/qwen35-4b-heldout-v5-coding-4b-r2'),
}


def canon(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Bad(ValueError):
    pass


def need(ok, why):
    if not ok:
        raise Bad(why)


def parse_calls(text, tools, marker):
    blocks = re.findall(r'<tool_call>(.*?)</tool_call>', text, re.S)
    if not blocks and text.strip().startswith('{'):
        blocks = [text.strip()]
    else:
        need(text.count('<tool_call>') == len(blocks) == text.count('</tool_call>'), 'incomplete envelope')
    calls = []
    for block in blocks:
        block = block.strip()
        if block.startswith('{'):
            value = json.loads(block)
            need(set(value) == {'name', 'arguments'}, 'unexpected fields')
            calls.append(value)
            continue
        match = re.fullmatch(r'<function=([^<>]+)>(.*?)</function>', block, re.S)
        need(match is not None, 'malformed call')
        name, body = match.groups()
        schema = next(t['function']['parameters']['properties'] for t in tools if t['function']['name'] == name)
        args, offset = {}, 0
        for p in re.finditer(r'<parameter=([^<>]+)>(.*?)</parameter>', body, re.S):
            need(not body[offset:p.start()].strip(), 'unparsed content')
            key, value = p.groups()
            need(key in schema and key not in args, 'unknown/duplicate argument')
            value = value.removeprefix('\n').removesuffix('\n')
            kind = schema[key]['type']
            if kind == 'integer':
                need(re.fullmatch(r'-?\d+', value.strip() if marker != 'strict' else value) is not None, 'bad integer')
                value = int(value)
            elif kind == 'boolean':
                if marker != 'strict':
                    value = value.strip().lower()
                need(value in ('true', 'false'), 'bad boolean')
                value = value == 'true'
            args[key] = value
            offset = p.end()
        need(not body[offset:].strip(), 'trailing content')
        calls.append(dict(name=name, arguments=args))
    return calls


def normalise(call, expected, marker):
    if marker == 'strict':
        return call
    args = {k: (v.rstrip() if isinstance(v, str) else v) for k, v in call.get('arguments', {}).items()}
    if marker == 'fair':
        args = {k: v for k, v in args.items()
                if k in expected['arguments'] or (call.get('name'), k) not in HARMLESS_OPTIONAL}
    return dict(name=call.get('name'), arguments=args)


def grade(case, row, marker):
    text = row['text']
    closed = text.rfind('<think>') <= text.rfind('</think>')
    visible = re.sub(r'<\|(?:im_end|endoftext)\|>', '', text.rsplit('</think>', 1)[-1]).strip()
    completed = row['finish_reason'] == 'stop' and closed
    try:
        if case['kind'] == 'math':
            values = re.findall(r'\\boxed\{\s*([+-]?\d+)\s*\}', visible)
            correct = bool(values) and int(values[-1]) == case['answer']
        else:
            calls = parse_calls(visible, case['tools'], marker)
            expected = case['expected']
            if marker != 'strict':
                expected = dict(name=expected['name'],
                                arguments={k: (v.rstrip() if isinstance(v, str) else v)
                                           for k, v in expected['arguments'].items()})
            correct = canon([normalise(c, expected, marker) for c in calls]) == canon([expected])
    except (ValueError, TypeError, KeyError, StopIteration):
        correct = False
    return bool(correct and completed)


def mcnemar(gains, losses):
    n = gains + losses
    if not n:
        return 1.0
    return min(1.0, 2 * sum(math.comb(n, k) for k in range(min(gains, losses) + 1)) / 2 ** n)


def family(case_id):
    return case_id.split('-tool-')[1].rsplit('-', 1)[0] if '-tool-' in case_id else 'math'


def load(folder):
    return {json.loads(line)['id']: json.loads(line) for line in (folder / 'responses.jsonl').open()}


def score_pair(bundle, run_dir):
    """bundle: frozen panel folder; run_dir: folder with base/, adapter/ and scored/report.json."""
    cases = json.loads((bundle / 'cases.json').read_text())
    base, tuned = load(run_dir / 'base'), load(run_dir / 'adapter')
    out = {}
    for marker in MARKERS:
        rows = [(c, grade(c, base[c['id']], marker), grade(c, tuned[c['id']], marker)) for c in cases]
        tool = [(c, b, a) for c, b, a in rows if c['kind'] == 'tool']
        math_rows = [(b, a) for c, b, a in rows if c['kind'] == 'math']
        gains = sum(a and not b for _, b, a in tool)
        losses = sum(b and not a for _, b, a in tool)
        fams = defaultdict(lambda: [0, 0])
        for c, b, a in tool:
            fams[family(c['id'])][0] += b
            fams[family(c['id'])][1] += a
        up, down = sum(a > b for b, a in fams.values()), sum(a < b for b, a in fams.values())
        out[marker] = dict(
            tool_base=sum(b for _, b, _ in tool), tool_adapter=sum(a for _, _, a in tool), tool_of=len(tool),
            gains=gains, regressions=losses, net=gains - losses, case_level_p=mcnemar(gains, losses),
            families={k: dict(base=v[0], adapter=v[1]) for k, v in sorted(fams.items())},
            families_improved=up, families_worse=down, family_level_p=mcnemar(up, down),
            math_base=sum(b for b, _ in math_rows), math_adapter=sum(a for _, a in math_rows), math_of=len(math_rows))
    report = json.loads((run_dir / 'scored' / 'report.json').read_text())
    s = out['strict']
    need(s['tool_base'] == report['panels']['tool']['base_correct']
         and s['tool_adapter'] == report['panels']['tool']['adapter_correct']
         and s['math_base'] == report['panels']['math']['base_correct']
         and s['math_adapter'] == report['panels']['math']['adapter_correct'],
         f'strict self-check failed for {run_dir}: reimplementation disagrees with report.json')
    return out


def render(all_results, upstream_commit):
    lines = ['# Fair re-score of RuVLLM paired runs', '',
             f'Upstream: ruvnet/ruvllm @ `{upstream_commit}`. Saved model answers only; nothing re-generated.',
             'Strict counts reproduce upstream `report.json` exactly (checked by the script).', '',
             '| Run | Marker | Tool base → adapter (of 192) | Gains / regressions | Net | Case-level p | Families better / worse | Family-level p | Arithmetic (of 64) |',
             '|---|---|---|---|---|---|---|---|---|']
    for run, res in all_results.items():
        for m in MARKERS:
            r = res[m]
            lines.append(f"| {run} | {m} | {r['tool_base']} → {r['tool_adapter']} | {r['gains']} / {r['regressions']} | "
                         f"{r['net']:+d} | {r['case_level_p']:.2g} | {r['families_improved']} / {r['families_worse']} | "
                         f"{r['family_level_p']:.2g} | {r['math_base']} → {r['math_adapter']} |")
    lines += ['', '## Per-family tool passes (base → adapter, of 24)', '']
    for run, res in all_results.items():
        lines += [f'**{run}**', '', '| Family | strict | format | fair |', '|---|---|---|---|']
        for fam in res['strict']['families']:
            cells = [f"{res[m]['families'][fam]['base']} → {res[m]['families'][fam]['adapter']}" for m in MARKERS]
            lines.append(f'| {fam} | ' + ' | '.join(cells) + ' |')
        lines.append('')
    lines += ['## Reading this', '',
              '- *Case-level p* treats the 192 tool tasks as independent, as upstream does.',
              '- *Family-level p* is a sign test over the 8 tool families. Each family is 24 variants of one template, '
              'so this is a conservative view of how much independent evidence there is. With 8 families, '
              'p cannot go below 0.0078.',
              '- The fair marker is a judgement call, written down before scoring: see HARMLESS_OPTIONAL in the script.']
    return '\n'.join(lines) + '\n'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--upstream', required=True, type=Path, help='path to ruvllm/experiments/model-improvement')
    ap.add_argument('--upstream-commit', default='unknown')
    ap.add_argument('--pair', nargs=3, action='append', metavar=('LABEL', 'BUNDLE', 'RUN_DIR'),
                    help='score your own run instead of the published ones (repeatable)')
    ap.add_argument('--out', required=True, type=Path, help='output directory')
    args = ap.parse_args()
    if args.pair:
        results = {label: score_pair(Path(b), Path(r)) for label, b, r in args.pair}
    else:
        results = {run: score_pair(args.upstream / b, args.upstream / r) for run, (b, r) in RUNS.items()}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'fair-rescore.json').write_text(json.dumps(results, indent=2) + '\n')
    (args.out / 'fair-rescore.md').write_text(render(results, args.upstream_commit))
    print(render(results, args.upstream_commit))


if __name__ == '__main__':
    main()

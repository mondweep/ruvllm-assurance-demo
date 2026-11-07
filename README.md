# RuVLLM assurance demo

**Trust but verify:** an independent check of a published AI fine-tuning result, built as a
show-don't-tell demo for CIOs and CEOs.

[RuVLLM](https://github.com/ruvnet/ruvllm) reports that its `coding-4b` adapter improves
Qwen3.5 4B on tool use by **+50 tasks out of 192 (p = 1.8 × 10⁻¹⁵)**. Its process is unusually
disciplined: rules fixed in advance, every answer kept, and paired tests. This repo reuses that
evidence and asks one more question: *is the marking fair?*

## Finding (from the published answers, nothing re-generated)

| Run | Strict marker (as published) | Fair marker | Where the fair gain comes from |
|---|---|---|---|
| v3 confirmation, `coding-4b` | 123 → 173 (**+50**) | 147 → 173 (**+26**) | grep (+24), glob (+2) |
| v4 held-out, `coding-4b` | 149 → 176 (**+27**, 13 regressions) | 168 → 192 (**+24**, 0 regressions) | grep only |
| v5 held-out, `coding-4b-r2` (rejected) | 149 → 192 (**+43**) | 168 → 192 (**+24**) | grep only; arithmetic 62 → 46 |

What this means:

1. **About half the headline gain is marking strictness.** The base model added a harmless
   `timeout` to test commands (24 cases) and was marked wrong. The fair marker accepts it.
2. **The real gain is one habit.** The base model searches by putting the folder into Grep's
   `glob` filter instead of `path`. The adapter fixes that, consistently. It's genuine and useful,
   but it's one lesson repeated across 24 near-identical tasks, not 24 pieces of independent evidence.
3. **The 13 held-out "regressions" were a missing final newline** in written files. Under fair
   marking, `coding-4b` has no regressions.
4. **The rejected second adapter bought nothing.** Under fair marking it matches `coding-4b`
   exactly on tools, while losing 16 arithmetic answers. RuVLLM's gate was right to reject it.

Full tables: [`results/published/fair-rescore.md`](results/published/fair-rescore.md).

**Takeaway for leadership:** the result is real but narrow. Low p-values prove a difference
isn't luck; they don't prove it matters. Keeping every raw answer is what made this check possible.

## Independent re-test (7 Nov 2026)

We re-ran the v4 held-out test ourselves, using upstream's own worker and scorer at commit `890a5d7`,
on a rented RTX 3090 (upstream used an RTX 4090). Run time was 64 minutes and the cost was $0.24.
The machine was destroyed afterwards, and we confirmed it was gone.

| | Upstream published | Our re-test |
|---|---|---|
| Tool tasks, strict | 149 → 176 (+27, 13 regressions) | 149 → 176 (+27, 13 regressions) |
| Tool tasks, fair | 168 → 192 (+24, 0 regressions) | 168 → 192 (+24, 0 regressions) |
| Arithmetic (of 64) | 62 → 64 | 63 → 62 |
| Upstream's own gate | improvement confirmed | **not confirmed** (`math_anchor_regressed`) |

- **The tool-use result reproduces exactly** on different hardware.
- **The answers' wording varied between GPUs.** 25 base and 28 adapter answers out of 256 differed in
  text, mostly arithmetic working. That was enough to move one arithmetic answer, and that single answer
  flipped the gate's verdict.
- **The lesson:** a pass/fail rule that hinges on one answer is fragile. Treat a single run as a measurement,
  not a verdict.

Raw answers, logs and the cost receipt are in [`results/vast-v4-rtx3090/`](results/vast-v4-rtx3090/), and the
three-way marking is in [`results/vast-v4-rtx3090/fair/fair-rescore.md`](results/vast-v4-rtx3090/fair/fair-rescore.md).
The runner, which needs no SSH and has hard limits of $0.90 and 3 hours plus a self-destruct, is in
[`tools/vast/`](tools/vast/).

## The three markers

| Marker | Accepts |
|---|---|
| strict | Exactly what upstream accepts. Reimplemented here; the script stops unless it reproduces upstream `report.json` counts. |
| format | Also `True`/`False` booleans, and trailing whitespace in string arguments. |
| fair | Also harmless optional settings: `Bash.timeout`, `Bash.description`, `Grep.-n`. Settings that change results (`Grep.glob`, `Read.limit/offset`) still count as wrong. |

The fair marker is a judgement call, written down in [`scoring/fair_rescore.py`](scoring/fair_rescore.py)
(`HARMLESS_OPTIONAL`). Change it and re-run to test your own view.

## Reproduce

**Re-mark the published answers (no GPU, seconds):**

```sh
git clone https://github.com/ruvnet/ruvllm.git
git -C ruvllm checkout 890a5d72c9550bb53df7e57b2b4503fa20dd080f
python3 -I scoring/fair_rescore.py \
  --upstream ruvllm/experiments/model-improvement \
  --upstream-commit 890a5d72c9550bb53df7e57b2b4503fa20dd080f \
  --out results/published
```

**Re-run the models yourself (Colab L4 or A100):** open
[`notebooks/ruvllm_paired_replication.ipynb`](notebooks/ruvllm_paired_replication.ipynb) in Colab
(*File → Open notebook → GitHub*, then paste this repo's URL). It covers a live side-by-side (Act 1),
a full paired replication with rUv's own worker and scorer (Act 2), and three-way marking of your
answers (Act 3). A T4 won't work: the worker requires native BF16.

## Scope and caveats

- The panel is synthetic and templated: 8 tool families × 24 variants, plus 64 arithmetic tasks.
- *Family-level p* in the tables is a sign test over the 8 families. It's a deliberately
  conservative view; neither it nor the case-level p is the "true" answer.
- A Colab replication runs on a different GPU from the published RTX 3090, so a few answers may differ.
- Nothing here executes model-generated tool calls or code.

## Attribution

Built on [ruvnet/ruvllm](https://github.com/ruvnet/ruvllm) at commit `890a5d7` (Apache 2.0).
`scoring/fair_rescore.py` adapts the parsing and grading in
`experiments/model-improvement/measurement.py`. Upstream code and data are referenced, not copied.

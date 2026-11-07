"""Rent one Vast.ai GPU, run the v4 paired test, collect results via Vast logs, destroy.

Hard limits: estimated spend <= $0.90 and wall-clock <= 3h from creation, else destroy.
The API key is read from a private file and never printed.
"""
import base64, hashlib, io, json, re, sys, tarfile, time, urllib.request, urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = (HERE / 'key').read_text().strip()
API = 'https://console.vast.ai/api/v0'
OFFERS = [int(x) for x in sys.argv[1].split(',')]
OUT = Path(sys.argv[2])
MAX_USD, MAX_HOURS, MAX_DPH = 0.90, 3.0, 0.30
LOG = HERE / 'controller.log'
STATE = HERE / 'state.json'


def log(msg):
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with LOG.open('a') as f:
        f.write(line + '\n')


def call(method, path, body=None, timeout=30):
    req = urllib.request.Request(API + path, method=method,
                                 data=None if body is None else json.dumps(body).encode(),
                                 headers={'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b'{}')
    except urllib.error.HTTPError as e:
        return e.code, {'error': e.read()[:300].decode(errors='replace')}


def fetch(url, timeout=30):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode(errors='replace')
    except urllib.error.HTTPError as e:
        return e.code, ''


def instance(iid):
    code, data = call('GET', f'/instances/{iid}/')
    if code == 404:
        return None
    inst = data.get('instances') if isinstance(data, dict) else None
    return inst if inst else None


def destroy(iid, why):
    log(f'DESTROY {iid}: {why}')
    for attempt in range(6):
        code, data = call('DELETE', f'/instances/{iid}/')
        time.sleep(10)
        if instance(iid) is None:
            log(f'verified destroyed (attempt {attempt + 1})')
            return True
    log('WARNING: could not verify destruction')
    return False


def logs(iid, tail=4000):
    code, data = call('PUT', f'/instances/request_logs/{iid}/', {'tail': str(tail)})
    url = data.get('result_url') if isinstance(data, dict) else None
    if not url:
        return ''
    for _ in range(10):
        time.sleep(3)
        code, text = fetch(url)
        if code == 200 and text:
            return text
    return ''


def create():
    onstart = (HERE / 'onstart.sh').read_text()
    image = 'pytorch/pytorch@sha256:eee11b3b3872a8c838e35ef48f08b2d5def2080902c7f666831310ca1a0ef2be'
    for offer in OFFERS:
        code, data = call('POST', '/bundles/', {'ask_contract_id': {'eq': offer}, 'rentable': {'eq': True},
                                               'type': 'on-demand', 'allocated_storage': 60, 'limit': 2})
        offers = data.get('offers', []) if isinstance(data, dict) else []
        if len(offers) != 1:
            log(f'offer {offer} unavailable')
            continue
        dph = offers[0]['dph_total']
        if dph > MAX_DPH or dph * MAX_HOURS > MAX_USD:
            log(f'offer {offer} too expensive: ${dph:.3f}/h')
            continue
        code, data = call('PUT', f'/asks/{offer}/', {'client_id': 'me', 'image': image, 'env': {}, 'price': None,
                                                     'disk': 60, 'label': 'ruvllm-assurance-demo-v4', 'onstart': onstart,
                                                     'runtype': 'ssh', 'force': False, 'cancel_unavail': True})
        if code == 200 and data.get('success'):
            iid = data['new_contract']
            st = dict(instance=iid, offer=offer, gpu=offers[0]['gpu_name'], dph=dph, created=time.time())
            STATE.write_text(json.dumps(st))
            log(f"created instance {iid} on offer {offer} ({st['gpu']}, ${dph:.3f}/h)")
            return st
        log(f'create on {offer} failed: {code} {str(data)[:200]}')
    sys.exit('no offer could be rented')


def main():
    st = json.loads(STATE.read_text()) if STATE.exists() else create()
    iid, dph, created = st['instance'], st['dph'], st['created']
    last = ''
    while True:
        hours = (time.time() - created) / 3600
        cost = dph * hours
        inst = instance(iid)
        if inst is None:
            log(f'instance {iid} no longer exists (est. cost ${cost:.3f})')
            break
        if cost >= MAX_USD or hours >= MAX_HOURS:
            destroy(iid, f'limit reached: {hours:.2f}h, est ${cost:.3f}')
            break
        text = logs(iid) if inst.get('actual_status') == 'running' else ''
        prog = [l for l in text.splitlines() if l.startswith(('RUVLLM-START', 'RUVLLM-PROGRESS', 'RUVLLM-FINISHED'))]
        status = prog[-1][:240] if prog else f"status={inst.get('actual_status')} {(inst.get('status_msg') or '')[:120]}"
        if status != last:
            log(f'{hours * 60:.0f} min, est ${cost:.3f} | {status}')
            last = status
        m = re.search(r'RUVLLM-RESULT-BEGIN ([0-9a-f]{64})\n(.*?)RUVLLM-RESULT-END', text, re.S)
        if m:
            blob = base64.b64decode(''.join(l[len('RUVLLM-B64 '):] for l in m.group(2).splitlines()
                                            if l.startswith('RUVLLM-B64 ')))
            if hashlib.sha256(blob).hexdigest() == m.group(1):
                OUT.mkdir(parents=True, exist_ok=True)
                with tarfile.open(fileobj=io.BytesIO(blob)) as t:
                    t.extractall(OUT, filter='data')
                log(f'results verified (sha256 {m.group(1)[:12]}…) and saved to {OUT}')
                destroy(iid, 'results collected')
                break
            log('result block incomplete or hash mismatch; retrying')
        time.sleep(60)
    hours = (time.time() - created) / 3600
    receipt = dict(st, ended=time.time(), hours=round(hours, 3), est_cost_usd=round(dph * hours, 4))
    (HERE / 'receipt.json').write_text(json.dumps(receipt, indent=2))
    log(f"done: {hours * 60:.0f} min, est. ${dph * hours:.3f}")


if __name__ == '__main__':
    main()

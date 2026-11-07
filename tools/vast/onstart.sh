#!/bin/bash
# Runs on the rented GPU. Receives no user credential.
mkdir -p /workspace/run
cat > /workspace/job.sh <<'JOB'
#!/bin/bash
COMMIT=890a5d72c9550bb53df7e57b2b4503fa20dd080f
LOG=/proc/1/fd/1
say() { echo "$*" > $LOG 2>/dev/null || echo "$*"; }
envv() { v=$(printenv $1); [ -n "$v" ] || v=$(tr '\0' '\n' </proc/1/environ | sed -n "s/^$1=//p"); echo "$v"; }
destroy() { curl -sS -m 20 -X DELETE "https://console.vast.ai/api/v0/instances/$(envv CONTAINER_ID)/" -H "Authorization: Bearer $(envv CONTAINER_API_KEY)" >/dev/null 2>&1; }
# Kill switch: self-destroy after 3 hours whatever happens.
( sleep 10800; say "RUVLLM-WATCHDOG destroying"; destroy ) &
( while sleep 120; do say "RUVLLM-PROGRESS $(cat /workspace/run/status.json 2>/dev/null | tr -d '\n') base=$(cat /workspace/out/base/responses.jsonl 2>/dev/null | wc -l) adapter=$(cat /workspace/out/adapter/responses.jsonl 2>/dev/null | wc -l)"; done ) &
P=$!
say "RUVLLM-START $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader)"
export DEBIAN_FRONTEND=noninteractive
(command -v git >/dev/null || (apt-get update -qq && apt-get install -y -qq git >/dev/null)) \
  && git clone --quiet https://github.com/ruvnet/ruvllm.git /workspace/ruvllm \
  && git -C /workspace/ruvllm checkout --quiet $COMMIT \
  && bash /workspace/ruvllm/experiments/model-improvement/vast/remote-run.sh $COMMIT 5400 v4 coding-4b > /workspace/run/remote.log 2>&1
say "RUVLLM-FINISHED exit=$? $(cat /workspace/run/status.json 2>/dev/null | tr -d '\n')"
kill $P
tail -c 20000 /workspace/run/remote.log > /workspace/run/remote-tail.log 2>/dev/null
tar -C /workspace -czf /workspace/result.tgz out run/status.json run/gpu.txt run/pip-freeze.txt run/remote-tail.log run/run-pair.log 2>/dev/null
say "RUVLLM-RESULT-BEGIN $(sha256sum /workspace/result.tgz | cut -d' ' -f1)"
base64 -w 100 /workspace/result.tgz | while read -r l; do say "RUVLLM-B64 $l"; done
say "RUVLLM-RESULT-END"
# Give the controller time to collect, then self-destroy.
sleep 1500; say "RUVLLM-IDLE destroying"; destroy
JOB
nohup bash /workspace/job.sh > /workspace/run/job.log 2>&1 &

#!/usr/bin/env bash
set -euo pipefail

SPS="${SPS:-http://127.0.0.1:8090}"

echo "===== redis health (10 probes) ====="
for i in $(seq 1 10); do
  start=$(python3 -c "import time; print(time.time())")
  body=$(curl -m 2 -s "$SPS/api/v1/runtime/redis-health" || echo '{}')
  end=$(python3 -c "import time; print(time.time())")
  ms=$(python3 -c "print(int((${end} - ${start}) * 1000))")

  echo "$body" | python3 -c "
import sys,json
d=json.load(sys.stdin)
state=d.get('state','?')
lat=d.get('latency_ms','?')
skeys=list(d.get('streams',{}).keys())
dead=d.get('streams',{}).get('stream:dead:letter',{})
print(f'  [{i}] {ms}ms state={state} latency={lat}ms streams={len(skeys)} dead_len={dead.get(\"length\",\"?\")}')" 2>/dev/null || echo "  [$i] ${ms}ms parse_error"

  test -n "$body" || { echo "FAIL: empty body"; exit 1; }

  echo "$body" | python3 -c "
import sys,json
d=json.load(sys.stdin)
assert 'state' in d, 'missing state'
assert 'latency_ms' in d, 'missing latency_ms'
assert 'streams' in d, 'missing streams'
assert 'server' in d, 'missing server'
assert 'blockers' in d, 'missing blockers'
" || { echo "FAIL: schema mismatch"; exit 1; }

  if [ "$ms" -gt 2000 ]; then
    echo "FAIL: too slow ${ms}ms"
    exit 1
  fi
done

echo ""
echo "OK: redis health endpoint stable"

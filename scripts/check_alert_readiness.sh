#!/usr/bin/env bash
set -euo pipefail

SPS="${SPS:-http://127.0.0.1:8090}"

for path in \
  /api/v1/w2s-alerts/readiness \
  /api/v1/kline-alerts/readiness
do
  echo "===== $path ====="
  for i in 1 2 3 4 5; do
    start=$(python3 -c "import time; print(time.time())")
    body=$(curl -m 1.5 -s "$SPS$path" || echo '{}')
    end=$(python3 -c "import time; print(time.time())")
    ms=$(python3 -c "print(int((${end} - ${start}) * 1000))")
    short=$(echo "$body" | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps({'state':d.get('state'),'stream_length':d.get('stream_length'),'blockers':d.get('blockers')},ensure_ascii=False))" 2>/dev/null || echo "parse_error")
    echo "  [$i] ${ms}ms $short"

    test -n "$body" || { echo "FAIL: empty body"; exit 1; }

    echo "$body" | python3 -c "
import sys,json
d=json.load(sys.stdin)
assert 'ready' in d, 'missing ready'
assert 'state' in d, 'missing state'
assert 'blockers' in d, 'missing blockers'
assert 'evidence' in d, 'missing evidence'
" || { echo "FAIL: schema mismatch"; exit 1; }

    if [ "$ms" -gt 1500 ]; then
      echo "FAIL: too slow ${ms}ms"
      exit 1
    fi
  done
done

echo ""
echo "OK: alert readiness endpoints stable"

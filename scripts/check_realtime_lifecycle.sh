#!/usr/bin/env bash
set -euo pipefail

SPS="http://127.0.0.1:8090"

echo "===== status before ====="
curl -s "$SPS/api/v1/realtime/status" | tee /tmp/rt_before.json | python -m json.tool

echo ""
echo "===== start ====="
curl -s "$SPS/api/v1/realtime/start" | tee /tmp/rt_start.json | python -m json.tool

sleep 5

echo ""
echo "===== status after start ====="
curl -s "$SPS/api/v1/realtime/status" | tee /tmp/rt_running.json | python -m json.tool

python - <<'PY'
import json, subprocess
d=json.load(open("/tmp/rt_running.json"))
pids=[d.get(k) for k in ["raw_news_pid","decision_pid"] if d.get(k)]
assert pids, f"expected realtime core pids, got: {d}"
for pid in pids:
    r=subprocess.run(["ps","-p",str(pid)],capture_output=True,text=True)
    assert r.returncode==0, f"pid not alive: {pid}"
print("alive pids:", pids)
PY

echo ""
echo "===== stop ====="
curl -s "$SPS/api/v1/realtime/stop" | tee /tmp/rt_stop.json | python -m json.tool

sleep 3

echo ""
echo "===== status after stop ====="
curl -s "$SPS/api/v1/realtime/status" | tee /tmp/rt_stopped.json | python -m json.tool

python - <<'PY'
import json
d=json.load(open("/tmp/rt_stopped.json"))
assert d.get("running") is False, d
assert not d.get("raw_news_pid"), d
assert not d.get("decision_pid"), d
print("stopped verified")
PY

echo ""
echo "===== refresh: should still be stopped (no stale PID) ====="
curl -s "$SPS/api/v1/realtime/status" | tee /tmp/rt_stopped2.json | python -m json.tool

python - <<'PY'
import json
d=json.load(open("/tmp/rt_stopped2.json"))
assert d.get("running") is False, d
assert not d.get("raw_news_pid"), d
assert not d.get("decision_pid"), d
print("no stale PID verified")
PY

echo ""
echo "===== ALL CHECKS PASSED ====="

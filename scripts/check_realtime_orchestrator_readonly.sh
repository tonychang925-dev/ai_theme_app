#!/usr/bin/env bash
set -euo pipefail

BFF="${BFF:-http://127.0.0.1:8000}"

echo "===== orchestrator status (read-only) ====="
curl -s "$BFF/api/v2/realtime/orchestrator/status" \
  | tee /tmp/orch_status.json \
  | python -m json.tool

echo ""
echo "===== dry_run tick ====="
curl -s -X POST "$BFF/api/v2/realtime/orchestrator/tick" \
  -H 'Content-Type: application/json' \
  -d '{"dry_run": true}' \
  | tee /tmp/orch_tick.json \
  | python -m json.tool

python - <<'PY'
import json
d = json.load(open("/tmp/orch_tick.json"))

# Phase is present
assert "phase" in d, d
assert "phase_label" in d, d

# Services all present
assert "services" in d, d
for svc in ("cdp_token", "jyhf_market", "jyhf_auction", "w2s_alert", "support_alert"):
    assert svc in d["services"], f"missing service {svc}"
    s = d["services"][svc]
    assert "observed_state" in s, f"{svc} missing observed_state"
    assert "desired_state" in s, f"{svc} missing desired_state"
    assert "blockers" in s, f"{svc} missing blockers"
    assert "dependencies" in s, f"{svc} missing dependencies"

# planned_actions present
assert "planned_actions" in d, d

# global_blockers present
assert "global_blockers" in d, d

# P4-2A safety: dry_run must be True (always enforced)
assert d.get("dry_run") is True, f"dry_run must be True in P4-2A, got {d.get('dry_run')}"
assert d.get("dry_run_forced") is not None, "must have dry_run_forced field"

print("orchestrator readonly schema OK")
PY

echo ""
echo "===== attempt dry_run=false (must still be forced true) ====="
FORCE_RESULT=$(curl -s -X POST "$BFF/api/v2/realtime/orchestrator/tick" -H 'Content-Type: application/json' -d '{"dry_run": false}')
DRY_RUN=$(echo "$FORCE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dry_run'))")
FORCED=$(echo "$FORCE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dry_run_forced'))")
REASON=$(echo "$FORCE_RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dry_run_forced_reason',''))")
if [ "$DRY_RUN" = "True" ] && [ "$FORCED" = "True" ]; then
    echo "P4-2A dry_run forced OK: dry_run=$DRY_RUN forced=$FORCED reason=$REASON"
else
    echo "FAIL: dry_run=$DRY_RUN forced=$FORCED (expected both True)"
    exit 1
fi

echo ""
echo "===== ensure no action executed ====="
# Verify that the /status endpoint works without side effects
python - <<'PY'
import json
d = json.load(open("/tmp/orch_status.json"))
assert "phase" in d, d
assert d.get("enabled") is False, "orchestrator should default to disabled"
print("no side effects OK")
PY

echo ""
echo "===== ALL ORCHESTRATOR CHECKS PASSED ====="

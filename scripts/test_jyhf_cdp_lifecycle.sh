#!/usr/bin/env bash
# JYHF CDP Lifecycle Regression Test
# Run: bash scripts/test_jyhf_cdp_lifecycle.sh
# Requires: web_app_service running on :8000, SPS on :8090
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'
PASS="${GREEN}PASS${NC}"
FAIL="${RED}FAIL${NC}"

BFF="http://127.0.0.1:8000"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() {
  kill $(lsof -t -i TCP:8095 -s TCP:LISTEN 2>/dev/null) 2>/dev/null || true
}
trap cleanup EXIT

echo "========================================"
echo " JYHF CDP Lifecycle Regression Test"
echo "========================================"

# Ensure clean
cleanup
sleep 1

# ── 1. Cold start no residue ──
echo -n "1. 冷启动无残留 ... "
if lsof -t -i TCP:8095 -s TCP:LISTEN >/dev/null 2>&1; then
  echo -e "$FAIL"
  exit 1
fi
echo -e "$PASS"

# ── 2. Start managed ──
echo -n "2. 启动 managed ... "
RESP=$(curl -s -X POST "$BFF/api/v2/realtime/jyhf-cdp/start" -H "Content-Type: application/json" -d '{}')
OK=$(echo "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['ok'])" 2>/dev/null || echo "False")
OWNER=$(echo "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin).get('service_owner',''))" 2>/dev/null || echo "")
sleep 5
STATUS=$(curl -s "$BFF/api/v2/realtime/jyhf-cdp/status")
ST_OWNER=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('service_owner',''))" 2>/dev/null || echo "")
ST_COLLECTOR=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('collector_running',''))" 2>/dev/null || echo "")

if [ "$OK" != "True" ] || [ "$OWNER" != "managed" ]; then
  echo -e "$FAIL (ok=$OK owner=$OWNER)"
  exit 1
fi
# Verify _cmd_result has all fields
HAS_SR=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if 'service_running' in d else 'no')" 2>/dev/null)
HAS_SPID=$(echo "$RESP" | python3 -c "import json,sys; d=json.load(sys.stdin); print('yes' if 'service_pid' in d else 'no')" 2>/dev/null)
if [ "$HAS_SR" != "yes" ] || [ "$HAS_SPID" != "yes" ]; then
  echo -e "$FAIL (missing _cmd_result fields: sr=$HAS_SR spid=$HAS_SPID)"
  exit 1
fi
echo -e "$PASS (owner=$ST_OWNER collector=$ST_COLLECTOR)"

# ── 3. Stop managed → port released ──
echo -n "3. 停止 managed → 端口释放 ... "
curl -s -X POST "$BFF/api/v2/realtime/jyhf-cdp/stop" -H "Content-Type: application/json" -d '{}' > /dev/null
sleep 2
if lsof -t -i TCP:8095 -s TCP:LISTEN >/dev/null 2>&1; then
  echo -e "$FAIL"
  exit 1
fi
echo -e "$PASS"

# ── 4. External start → owner=external ──
echo -n "4. 外部脚本启动 → owner=external ... "
PYTHONPATH="$PROJECT_ROOT" bash "$PROJECT_ROOT/scripts/start_jyhf_cdp_service.sh"
sleep 4
# Trigger external detection
curl -s -X POST "$BFF/api/v2/realtime/jyhf-cdp/start" -H "Content-Type: application/json" -d '{}' > /dev/null
sleep 2
EXT_OWNER=$(curl -s "$BFF/api/v2/realtime/jyhf-cdp/status" | python3 -c "import json,sys; print(json.load(sys.stdin).get('service_owner',''))" 2>/dev/null)
if [ "$EXT_OWNER" != "external" ]; then
  echo -e "$FAIL (owner=$EXT_OWNER)"
  exit 1
fi
echo -e "$PASS"

# ── 5. External stop → process alive, collector stopped ──
echo -n "5. external stop → 不杀进程 ... "
STOP_MSG=$(curl -s -X POST "$BFF/api/v2/realtime/jyhf-cdp/stop" -H "Content-Type: application/json" -d '{}' | python3 -c "import json,sys; print(json.load(sys.stdin).get('message',''))" 2>/dev/null)
if ! echo "$STOP_MSG" | grep -q "external"; then
  echo -e "$FAIL (msg=$STOP_MSG)"
  exit 1
fi
ALIVE=$(curl -s http://127.0.0.1:8095/status 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('running',''))" 2>/dev/null || echo "dead")
COLL=$(curl -s http://127.0.0.1:8095/status 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('collector_running',''))" 2>/dev/null || echo "")
if [ "$ALIVE" != "True" ] || [ "$COLL" != "False" ]; then
  echo -e "$FAIL (alive=$ALIVE collector=$COLL)"
  exit 1
fi
echo -e "$PASS (alive collector=False)"

# ── 6. force-stop → port released ──
echo -n "6. force-stop → 端口释放 ... "
FS_MSG=$(curl -s -X POST "$BFF/api/v2/realtime/jyhf-cdp/service/force-stop" -H "Content-Type: application/json" -d '{}' | python3 -c "import json,sys; print(json.load(sys.stdin).get('message',''))" 2>/dev/null)
sleep 2
if lsof -t -i TCP:8095 -s TCP:LISTEN >/dev/null 2>&1; then
  echo -e "$FAIL"
  exit 1
fi
echo -e "$PASS"

# ── 7. Status consistency ──
echo -n "7. get_status / _cmd_result 状态口径 ... "
FINAL=$(curl -s "$BFF/api/v2/realtime/jyhf-cdp/status")
F_OWNER=$(echo "$FINAL" | python3 -c "import json,sys; print(json.load(sys.stdin).get('service_owner',''))" 2>/dev/null)
F_SR=$(echo "$FINAL" | python3 -c "import json,sys; print(json.load(sys.stdin).get('service_running',''))" 2>/dev/null)
F_CR=$(echo "$FINAL" | python3 -c "import json,sys; print(json.load(sys.stdin).get('collector_running',''))" 2>/dev/null)
if [ "$F_OWNER" != "none" ] || [ "$F_SR" != "False" ] || [ "$F_CR" != "False" ]; then
  echo -e "$FAIL (owner=$F_OWNER sr=$F_SR cr=$F_CR)"
  exit 1
fi
echo -e "$PASS"

echo "========================================"
echo -e " ${GREEN}ALL 7 PASSED${NC}"
echo "========================================"

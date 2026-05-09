#!/usr/bin/env bash
# smoke_jyhf_cdp_push_intel.sh
# 灰度验收脚本：验证 JYHF CDP → Redis Stream 推送链路
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

HOST="${JYHF_CDP_SERVICE_HOST:-127.0.0.1}"
PORT="${JYHF_CDP_SERVICE_PORT:-8095}"
BASE="http://${HOST}:${PORT}"

echo "============================================"
echo " JYHF CDP Push Intel Smoke Test"
echo "============================================"

# 1. Health
echo -n "[1] Health check ... "
if curl -fsS "${BASE}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC} (service not running on ${BASE})"
    exit 1
fi

# 2. Status
echo -n "[2] Status ... "
STATUS=$(curl -fsS "${BASE}/status" 2>/dev/null || echo "{}")
COLLECTOR_RUNNING=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('collector_running',False))" 2>/dev/null || echo "False")
PUSHED=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('pushed_to_stream_count_total',0))" 2>/dev/null || echo "0")
NEW=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('new_event_count_total',0))" 2>/dev/null || echo "0")
DUP=$(echo "$STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('duplicate_count_total',0))" 2>/dev/null || echo "0")
echo -e "${GREEN}PASS${NC}"
echo "    collector_running=${COLLECTOR_RUNNING}"
echo "    new_event_count_total=${NEW}"
echo "    duplicate_count_total=${DUP}"
echo "    pushed_to_stream_count_total=${PUSHED}"

# 3. Redis connectivity
echo -n "[3] Redis ping ... "
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC} (redis not reachable)"
    exit 1
fi

# 4. Stream exists and has items
STREAM="stream:event:feed"
STREAM_LEN=$(redis-cli XLEN "$STREAM" 2>/dev/null || echo "0")
echo -n "[4] Redis stream ${STREAM} ... "
if [ "$STREAM_LEN" -gt 0 ] 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} (length=${STREAM_LEN})"
else
    echo -e "${YELLOW}WARN${NC} (stream empty or missing)"
fi

# 5. Latest JYHF CDP items in stream
echo -n "[5] jyhf_cdp items in stream ... "
JYHF_COUNT=$(redis-cli XREVRANGE "$STREAM" + - COUNT 50 2>/dev/null | grep -c 'jyhf_cdp' || echo "0")
if [ "$JYHF_COUNT" -gt 0 ] 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} (found ${JYHF_COUNT} jyhf_cdp items in last 50)"
else
    echo -e "${YELLOW}WARN${NC} (no jyhf_cdp items in last 50 messages)"
fi

# 6. Latest 3 JYHF CDP items (sample)
echo "[6] Latest 3 jyhf_cdp items:"
redis-cli XREVRANGE "$STREAM" + - COUNT 20 2>/dev/null | while read -r line; do
    case "$line" in
        *jyhf_cdp*)
            echo "$line" | python3 -c "
import sys, json
try:
    payload = json.loads(sys.stdin.read())
    print(f\"  {payload.get('title','?')} | {payload.get('summary','')[:60]} | review={payload.get('review_required')} | conf={payload.get('confidence')}\")
except: pass
" 2>/dev/null || true
            ;;
    esac
done | head -3

# 7. Check for duplicate item_ids in stream (last 100 items)
echo -n "[7] Duplicate item_id check (last 100) ... "
DUPS=$(redis-cli XREVRANGE "$STREAM" + - COUNT 100 2>/dev/null | grep -o '"item_id":[[:space:]]*"[^"]*"' | sort | uniq -d | wc -l | tr -d ' ')
if [ "$DUPS" -eq 0 ] 2>/dev/null; then
    echo -e "${GREEN}PASS${NC} (0 duplicates)"
else
    echo -e "${RED}FAIL${NC} (${DUPS} duplicate item_ids found)"
fi

echo "============================================"
echo " Smoke test complete"
echo "============================================"

#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
WEB_PYTHON="${WEB_PYTHON:-$ROOT_DIR/.venv/bin/python}"
SPS_PYTHON="${SPS_PYTHON:-/opt/miniconda3/envs/theme_matcher_env/bin/python}"
SPS_RUNTIME_PROFILE="${SPS_RUNTIME_PROFILE:-sps-conda-ml}"
WEB_APP_PATTERN="uvicorn web_app_service.main:app --host 0.0.0.0 --port 8000"
WEB_APP_HEALTH_URL="http://127.0.0.1:8000/healthz"
SPS_PATTERN="uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port 8090"
SPS_HEALTH_URL="http://127.0.0.1:8090/healthz"
CHECK_TRADE_DATE="${CHECK_TRADE_DATE:-$(date +%F)}"
WORKSPACE_CHAIN_URL="http://127.0.0.1:8000/api/v2/workspace/market-validation?trade_date=${CHECK_TRADE_DATE}"
INTEL_FEED_CHAIN_URL="http://127.0.0.1:8000/api/v2/intel/feed?date=${CHECK_TRADE_DATE}&type=all&session=all&limit=1"
RECAP_SNAPSHOT_CHAIN_URL="http://127.0.0.1:8000/api/v2/post_market_snapshot?trade_date=${CHECK_TRADE_DATE}"

JSON_PYTHON="$WEB_PYTHON"
if [[ ! -x "$JSON_PYTHON" ]]; then
  JSON_PYTHON="python3"
fi

first_listener_pid() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true
  fi
}

print_process_runtime() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    echo "       pid: -"
    return 0
  fi
  echo "       pid: $pid"
  ps -p "$pid" -o command= 2>/dev/null | sed 's/^/       command: /' || true
  if command -v lsof >/dev/null 2>&1; then
    lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n/       cwd: /p' || true
  fi
}

print_json_summary() {
  local label="$1"
  local payload="$2"
  JSON_PAYLOAD="$payload" "$JSON_PYTHON" - "$label" <<'PY'
import json
import os
import sys

label = sys.argv[1]
try:
    data = json.loads(os.environ["JSON_PAYLOAD"])
except Exception as exc:
    print(f"[fail] {label}: invalid json: {exc}")
    sys.exit(1)

if label == "sps_health":
    print(f"       runtime_profile: {data.get('runtime_profile')}")
    print(f"       python: {data.get('python')}")
    print(f"       cwd: {data.get('cwd')}")
    print(f"       torch_available: {data.get('torch_available')} version={data.get('torch_version') or '-'}")
    print(f"       text2vec_available: {data.get('text2vec_available')} version={data.get('text2vec_version') or '-'}")
elif label == "realtime":
    fields = [
        "running", "run_id", "raw_news_pid", "decision_pid", "db_collector_pid",
        "intel_producer_pid", "intel_collection_pid", "last_error",
    ]
    for key in fields:
        print(f"       {key}: {data.get(key)}")
elif label == "jyhf_dom":
    fields = ["service_running", "service_owner", "collector_running", "cdp_connected", "last_capture_at", "capture_count_total"]
    for key in fields:
        print(f"       {key}: {data.get(key)}")
elif label == "intel_feed":
    items = data.get("items") or []
    latest = None
    if items:
        latest = items[0].get("occurred_at") or items[0].get("created_at") or items[0].get("published_at")
    print(f"       today_count: {data.get('count', len(items))}")
    print(f"       latest_item_time: {latest or '-'}")
else:
    print(json.dumps(data, ensure_ascii=False, indent=2))
PY
}

echo "New-chain Stack Status"
echo "======================"
echo "Project: $ROOT_DIR"
echo "Runtime contract:"
echo "  web_app python: $WEB_PYTHON"
echo "  sps python: $SPS_PYTHON"
echo "  sps profile: $SPS_RUNTIME_PROFILE"
echo
echo "[web_app_service]"
WEB_PID="$(first_listener_pid 8000)"
if pgrep -f "$WEB_APP_PATTERN" >/dev/null 2>&1 || [[ -n "$WEB_PID" ]]; then
  echo "[up]   web_app_service:8000"
  pgrep -fal "$WEB_APP_PATTERN" | sed 's/^/       /'
  print_process_runtime "$WEB_PID"
else
  echo "[down] web_app_service:8000"
fi

if curl -fsS --max-time 2 "$WEB_APP_HEALTH_URL" >/dev/null 2>&1; then
  echo "[ok]   web_app_service /healthz"
else
  echo "[fail] web_app_service /healthz"
fi

echo
echo "[stock_processing_service]"
SPS_PID="$(first_listener_pid 8090)"
if pgrep -f "$SPS_PATTERN" >/dev/null 2>&1 || [[ -n "$SPS_PID" ]]; then
  echo "[up]   stock_processing_service:8090"
  pgrep -fal "$SPS_PATTERN" | sed 's/^/       /'
  print_process_runtime "$SPS_PID"
else
  echo "[down] stock_processing_service:8090"
fi

if SPS_HEALTH_PAYLOAD="$(curl -fsS --max-time 3 "$SPS_HEALTH_URL" 2>/dev/null)"; then
  echo "[ok]   stock_processing_service /healthz"
  print_json_summary "sps_health" "$SPS_HEALTH_PAYLOAD" || true
else
  echo "[fail] stock_processing_service /healthz"
fi

echo
echo "[realtime]"
if REALTIME_PAYLOAD="$(curl -fsS --max-time 5 "http://127.0.0.1:8000/api/v2/realtime/new-chain/status" 2>/dev/null)"; then
  if print_json_summary "realtime" "$REALTIME_PAYLOAD"; then
    echo "[ok]   realtime new-chain status"
  else
    echo "[fail] realtime new-chain status returned non-json"
  fi
else
  echo "[fail] realtime new-chain status"
fi

echo
echo "[jyhf_dom]"
if JYHF_PAYLOAD="$(curl -fsS --max-time 5 "http://127.0.0.1:8000/api/v2/realtime/jyhf-cdp/status" 2>/dev/null)"; then
  echo "[ok]   JYHF DOM status"
  print_json_summary "jyhf_dom" "$JYHF_PAYLOAD" || true
else
  echo "[fail] JYHF DOM status"
fi

echo
echo "[intel_feed]"
if INTEL_PAYLOAD="$(curl -fsS --max-time 5 "$INTEL_FEED_CHAIN_URL" 2>/dev/null)"; then
  echo "[ok]   web_app intel feed chain"
  print_json_summary "intel_feed" "$INTEL_PAYLOAD" || true
else
  echo "[fail] web_app intel feed chain"
fi

if curl -fsS --max-time 3 "$WORKSPACE_CHAIN_URL" >/dev/null 2>&1; then
  echo "[ok]   web_app workspace chain"
else
  echo "[fail] web_app workspace chain"
fi

if curl -fsS --max-time 3 "$RECAP_SNAPSHOT_CHAIN_URL" >/dev/null 2>&1; then
  echo "[ok]   web_app recap snapshot chain"
else
  echo "[fail] web_app recap snapshot chain"
fi

#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
WEB_APP_PATTERN="uvicorn web_app_service.main:app --host 0.0.0.0 --port 8000"
WEB_APP_HEALTH_URL="http://127.0.0.1:8000/healthz"
SPS_PATTERN="uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port 8090"
SPS_HEALTH_URL="http://127.0.0.1:8090/healthz"
CHECK_TRADE_DATE="${CHECK_TRADE_DATE:-$(date +%F)}"
WORKSPACE_CHAIN_URL="http://127.0.0.1:8000/api/v2/workspace/market-validation?trade_date=${CHECK_TRADE_DATE}"
INTEL_FEED_CHAIN_URL="http://127.0.0.1:8000/api/v2/intel/feed?date=${CHECK_TRADE_DATE}&type=all&session=all&limit=1"
RECAP_SNAPSHOT_CHAIN_URL="http://127.0.0.1:8000/api/v2/post_market_snapshot?trade_date=${CHECK_TRADE_DATE}"

echo "New-chain Stack Status"
echo "======================"
echo "Project: $ROOT_DIR"
echo
echo "[web_app_service]"
if pgrep -f "$WEB_APP_PATTERN" >/dev/null 2>&1; then
  echo "[up]   web_app_service:8000"
  pgrep -fal "$WEB_APP_PATTERN" | sed 's/^/       /'
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
if pgrep -f "$SPS_PATTERN" >/dev/null 2>&1; then
  echo "[up]   stock_processing_service:8090"
  pgrep -fal "$SPS_PATTERN" | sed 's/^/       /'
else
  echo "[down] stock_processing_service:8090"
fi

if curl -fsS --max-time 2 "$SPS_HEALTH_URL" >/dev/null 2>&1; then
  echo "[ok]   stock_processing_service /healthz"
else
  echo "[fail] stock_processing_service /healthz"
fi

if curl -fsS --max-time 3 "$WORKSPACE_CHAIN_URL" >/dev/null 2>&1; then
  echo "[ok]   web_app workspace chain"
else
  echo "[fail] web_app workspace chain"
fi

if curl -fsS --max-time 3 "$INTEL_FEED_CHAIN_URL" >/dev/null 2>&1; then
  echo "[ok]   web_app intel feed chain"
else
  echo "[fail] web_app intel feed chain"
fi

if curl -fsS --max-time 3 "$RECAP_SNAPSHOT_CHAIN_URL" >/dev/null 2>&1; then
  echo "[ok]   web_app recap snapshot chain"
else
  echo "[fail] web_app recap snapshot chain"
fi

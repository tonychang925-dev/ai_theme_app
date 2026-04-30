#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

: "${REPLAY_DB_NAME:=stock_data_test}"
: "${SPS_PORT:=8090}"
: "${WEB_PORT:=8081}"

cleanup() {
  set +e
  if [[ -n "${WEB_PID:-}" ]]; then kill "$WEB_PID" >/dev/null 2>&1 || true; fi
  if [[ -n "${SPS_PID:-}" ]]; then kill "$SPS_PID" >/dev/null 2>&1 || true; fi
}
trap cleanup EXIT

echo "[smoke] starting stock_processing_service api on :${SPS_PORT} (db=${REPLAY_DB_NAME})"
REPLAY_DB_NAME="$REPLAY_DB_NAME" python3 -m uvicorn stock_processing_service.api_app:app --port "$SPS_PORT" >/tmp/sps_api.log 2>&1 &
SPS_PID=$!

sleep 2

echo "[smoke] starting web_app_service on :${WEB_PORT}"
WEB_APP_READ_MODE=http \
STOCK_PROCESSING_READ_BASE_URL="http://127.0.0.1:${SPS_PORT}" \
python3 -m uvicorn web_app_service.main:app --port "$WEB_PORT" >/tmp/web_app.log 2>&1 &
WEB_PID=$!

sleep 2

echo "[smoke] probing endpoints"
curl -sf "http://127.0.0.1:${SPS_PORT}/healthz" | tee /tmp/sps_healthz.json
curl -sf "http://127.0.0.1:${WEB_PORT}/healthz" | tee /tmp/web_healthz.json
curl -sf "http://127.0.0.1:${WEB_PORT}/api/v2/post_market_snapshot?trade_date=2026-04-23" | tee /tmp/web_post_market_snapshot.json
curl -sf "http://127.0.0.1:${WEB_PORT}/api/v2/strong_watch?trade_date=2026-04-23" | tee /tmp/web_strong_watch.json
curl -sf "http://127.0.0.1:${WEB_PORT}/api/v2/w2s_candidates?trade_date=2026-04-23" | tee /tmp/web_w2s_candidates.json

echo "[smoke] done"

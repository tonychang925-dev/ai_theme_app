#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
PYTHON_CMD="${PYTHON_CMD:-/opt/miniconda3/envs/theme_matcher_env/bin/python}"
RUN_ID="${RUN_ID:-pm_e2e_new_chain_$(date +%Y%m%d_%H%M%S)}"
WRITE_DB_NAME="${WRITE_DB_NAME:-${PG_DATABASE:-stock_data}}"
READ_DB_NAME="${READ_DB_NAME:-${READ_PG_DATABASE:-stock_data_test}}"
REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
SPS_PORT="${SPS_PORT:-8090}"
START_SPS="${START_SPS:-true}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/logs/pre_market_e2e/$RUN_ID}"

mkdir -p "$LOG_DIR"

export DB_TYPE="${DB_TYPE:-postgresql}"
export PG_DATABASE="$WRITE_DB_NAME"
export DB_NAME="$WRITE_DB_NAME"
export REPLAY_DB_NAME="$WRITE_DB_NAME"
export READ_PG_DATABASE="$READ_DB_NAME"
export REDIS_URL

export THEME_PROFILE_VERSION="${THEME_PROFILE_VERSION:-v2}"
export THEME_PROFILE_V2_STATUS="${THEME_PROFILE_V2_STATUS:-draft}"
export THEME_PROFILE_V2_FALLBACK_TO_V1="${THEME_PROFILE_V2_FALLBACK_TO_V1:-true}"
export THEME_PROFILE_V2_REQUIRE_LOADED="${THEME_PROFILE_V2_REQUIRE_LOADED:-true}"
export THEME_PROFILE_CACHE_TTL_SECONDS="${THEME_PROFILE_CACHE_TTL_SECONDS:-300}"
export THEME_MATCH_LLM_JUDGE_MODE="${THEME_MATCH_LLM_JUDGE_MODE:-auto}"
export THEME_PROCESSOR_STRUCTURED_CONCURRENCY="${THEME_PROCESSOR_STRUCTURED_CONCURRENCY:-2}"
export THEME_MATCH_ENABLE_EVENT_PROFILE_LLM="${THEME_MATCH_ENABLE_EVENT_PROFILE_LLM:-false}"

pids=()

cleanup() {
  local rc=$?
  echo "[stop] stopping new-chain E2E stack, rc=$rc"
  for pid in "${pids[@]:-}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait "${pids[@]:-}" >/dev/null 2>&1 || true
  exit "$rc"
}
trap cleanup INT TERM EXIT

start_bg() {
  local name="$1"
  shift
  local log_file="$LOG_DIR/$name.log"
  echo "[start] $name -> $log_file"
  (cd "$ROOT_DIR" && "$@") >"$log_file" 2>&1 &
  pids+=("$!")
  echo "[pid] $name ${pids[-1]}"
}

wait_http() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + 60))
  while (( SECONDS < deadline )); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      echo "[ok] $label $url"
      return 0
    fi
    sleep 1
  done
  echo "[fail] $label not ready: $url" >&2
  return 1
}

echo "New-chain PreMarket E2E stack"
echo "================================"
echo "root=$ROOT_DIR"
echo "run_id=$RUN_ID"
echo "write_db=$WRITE_DB_NAME"
echo "read_db=$READ_DB_NAME"
echo "redis_url=$REDIS_URL"
echo "sps_port=$SPS_PORT start_sps=$START_SPS"
echo "theme_profile_version=$THEME_PROFILE_VERSION status=$THEME_PROFILE_V2_STATUS fallback=$THEME_PROFILE_V2_FALLBACK_TO_V1"
echo "logs=$LOG_DIR"
echo

if [[ "$START_SPS" == "true" ]]; then
  if curl -fsS --max-time 2 "http://127.0.0.1:$SPS_PORT/healthz" >/dev/null 2>&1; then
    echo "[skip] SPS already healthy on $SPS_PORT"
  else
    start_bg "stock_processing_service_${SPS_PORT}" \
      "$PYTHON_CMD" -m uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port "$SPS_PORT"
    wait_http "http://127.0.0.1:$SPS_PORT/healthz" "SPS"
  fi
fi

start_bg "raw_news_services" \
  "$PYTHON_CMD" evaluate_service/e2e/pre_market_brief/run_raw_news_services.py \
    --db-name "$WRITE_DB_NAME" \
    --run-id "$RUN_ID" \
    --redis-url "$REDIS_URL"

start_bg "phase0_decision_services" \
  "$PYTHON_CMD" evaluate_service/e2e/pre_market_brief/run_phase0_decision_services.py \
    --db-name "$WRITE_DB_NAME" \
    --run-id "$RUN_ID" \
    --redis-url "$REDIS_URL"

echo
echo "[ready] new-chain E2E services are running without frontend_bff."
echo "[next] run E2E with:"
echo "  RUN_ID=$RUN_ID $PYTHON_CMD evaluate_service/e2e/pre_market_brief/run_pre_market_e2e.py \\"
echo "    --test-cases evaluate_service/data/raw/test_cases.txt \\"
echo "    --db-name $WRITE_DB_NAME --trade-date 2026-05-15 --run-id $RUN_ID \\"
echo "    --limit 100 --force-clean --delete-final-snapshot --clean-trade-date-all-e2e \\"
echo "    --inject --wait --wait-timeout 1800 --quiet-window-seconds 60 --require-ready \\"
echo "    --rebuild --force-rebuild --evaluate --sps-base-url http://127.0.0.1:$SPS_PORT \\"
echo "    --copy-snapshot-to-db $READ_DB_NAME"
echo
echo "[hold] press Ctrl-C to stop services."

while true; do
  sleep 30
done

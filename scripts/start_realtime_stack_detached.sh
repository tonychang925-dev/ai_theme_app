#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
LOG_DIR="$ROOT_DIR/logs/realtime"
STREAM_SESSION="ai_theme_realtime_streams"
THEME_SESSION="ai_theme_theme_8002"
BFF_SESSION="ai_theme_bff_8003"
FRONTEND_SESSION="ai_theme_frontend_5173"

mkdir -p "$LOG_DIR"

stop_screen_session() {
  local session="$1"
  screen -S "$session" -X quit >/dev/null 2>&1 || true
}

wait_http() {
  local name="$1"
  local url="$2"
  local attempts="${3:-40}"
  for _ in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
      sleep 1
      if curl -fsS --max-time 2 "$url" >/dev/null 2>&1; then
        echo "[ok] ${name} ready"
        return 0
      fi
    fi
    sleep 1
  done
  echo "[fail] ${name} not ready: ${url}"
  return 1
}

runtime_env_prefix='
cd /Users/admin/Desktop/ai_theme_app
if [[ -f .env.local ]]; then set -a; source .env.local; set +a; fi
if [[ -f .env.theme ]]; then set -a; source .env.theme; set +a; fi
if [[ -f .env ]]; then set -a; source .env; set +a; fi
export ALLOW_REALTIME_AUTO_THEME_CREATE=false
export THEME_PROFILE_VERSION=v2
export THEME_PROFILE_V2_STATUS=accepted_candidate
export THEME_PROFILE_V2_FALLBACK_TO_V1=true
export THEME_PROFILE_V2_REQUIRE_LOADED=true
export PG_DATABASE=stock_data_test
export DB_NAME=stock_data_test
export READ_PG_DATABASE=stock_data_test
export POSTGRES_DATABASE=stock_data_test
export STREAM_CLEANUP_INTERVAL_HOURS="${STREAM_CLEANUP_INTERVAL_HOURS:-2}"
export CONSUMER_GROUP_CLEANUP_INTERVAL_SECONDS="${CONSUMER_GROUP_CLEANUP_INTERVAL_SECONDS:-1800}"
export PENDING_RECLAIM_ENABLED="${PENDING_RECLAIM_ENABLED:-true}"
export PENDING_RECLAIM_INTERVAL_SECONDS="${PENDING_RECLAIM_INTERVAL_SECONDS:-300}"
'

echo "[restart] stopping existing realtime screen sessions"
stop_screen_session "$STREAM_SESSION"
stop_screen_session "$THEME_SESSION"
stop_screen_session "$BFF_SESSION"
stop_screen_session "$FRONTEND_SESSION"

pkill -f "python.*-m database_service.streams.start_services" >/dev/null 2>&1 || true
pkill -f "uvicorn theme_service.app:app --host 0.0.0.0 --port 8002" >/dev/null 2>&1 || true
pkill -f "uvicorn frontend_bff.app:app --host 0.0.0.0 --port 8003" >/dev/null 2>&1 || true
pkill -f "bash.*scripts/start_frontend_bff_wrapper.sh" >/dev/null 2>&1 || true

echo "[start] stream services detached screen=${STREAM_SESSION}"
screen -dmS "$STREAM_SESSION" bash -lc "${runtime_env_prefix}
export PYTHONPATH=/Users/admin/Desktop/ai_theme_app
exec /opt/miniconda3/envs/theme_matcher_env/bin/python -m database_service.streams.start_services >>'$LOG_DIR/realtime_stream_services.detached.log' 2>&1"

echo "[start] theme_service:8002 detached screen=${THEME_SESSION}"
screen -dmS "$THEME_SESSION" bash -lc "${runtime_env_prefix}
exec /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m uvicorn theme_service.app:app --host 0.0.0.0 --port 8002 --no-access-log >>'$LOG_DIR/theme_service_8002.detached.log' 2>&1"
wait_http "theme_service:8002" "http://127.0.0.1:8002/health"

echo "[start] frontend_bff:8003 detached screen=${BFF_SESSION}"
screen -dmS "$BFF_SESSION" bash -lc "${runtime_env_prefix}
export BFF_ACCESS_LOG_FLAG=--no-access-log
export BFF_PYTHON_CMD=/Users/admin/Desktop/ai_theme_app/.venv/bin/python
exec bash /Users/admin/Desktop/ai_theme_app/scripts/start_frontend_bff_wrapper.sh >>'$LOG_DIR/frontend_bff_8003.detached.log' 2>&1"
wait_http "frontend_bff:8003" "http://127.0.0.1:8003/health"

if [[ -f "$ROOT_DIR/frontend/package.json" ]] && command -v npm >/dev/null 2>&1; then
  echo "[start] frontend vite detached screen=${FRONTEND_SESSION}"
  screen -dmS "$FRONTEND_SESSION" bash -lc "cd '$ROOT_DIR/frontend' && exec npm run dev -- --host >>'$LOG_DIR/frontend_vite.detached.log' 2>&1"
fi

echo "$$" >"$LOG_DIR/start_realtime_stack.detached.pid"
"$ROOT_DIR/scripts/status_realtime_stack.sh"

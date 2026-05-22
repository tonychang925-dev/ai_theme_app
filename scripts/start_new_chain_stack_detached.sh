#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
LOG_DIR="$ROOT_DIR/logs/realtime"
SPS_SESSION="ai_theme_sps_8090"
WEB_SESSION="ai_theme_web_8000"
FRONTEND_SESSION="ai_theme_frontend_5173"
FRONTEND_PATTERN="vite --host|node .*vite .*--port 5173"

mkdir -p "$LOG_DIR"

stop_screen_session() {
  local session="$1"
  screen -S "$session" -X quit >/dev/null 2>&1 || true
}

wait_health() {
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

write_pid_file() {
  local name="$1"
  local port="$2"
  local path="$3"
  local pid=""
  if command -v lsof >/dev/null 2>&1; then
    pid="$(lsof -t -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
  fi
  if [[ -z "$pid" ]]; then
    pid="$(pgrep -f "$name" | head -1 || true)"
  fi
  if [[ -n "$pid" ]]; then
    echo "$pid" >"$path"
    echo "[pid] ${name}: ${pid} -> ${path}"
    return 0
  fi
  echo "[warn] ${name} pid not found"
  return 1
}

runtime_env_prefix='
cd /Users/admin/Desktop/ai_theme_app
if [[ -f .env.theme ]]; then set -a; source .env.theme; set +a; fi
if [[ -f .env ]]; then set -a; source .env; set +a; fi
export THEME_PROFILE_VERSION=v2
export THEME_PROFILE_V2_STATUS=accepted_candidate
export THEME_PROFILE_V2_FALLBACK_TO_V1=true
export THEME_PROFILE_V2_REQUIRE_LOADED=true
export PG_DATABASE=stock_data_test
export DB_NAME=stock_data_test
export READ_PG_DATABASE=stock_data_test
export POSTGRES_DATABASE=stock_data_test
'

"$ROOT_DIR/scripts/stop_new_chain_stack.sh" --force --with-frontend >/dev/null 2>&1 || true
stop_screen_session "$SPS_SESSION"
stop_screen_session "$WEB_SESSION"
stop_screen_session "$FRONTEND_SESSION"

echo "[start] stock_processing_service:8090 detached screen=${SPS_SESSION}"
screen -dmS "$SPS_SESSION" bash -lc "${runtime_env_prefix}
export PYTHONPATH=/Users/admin/Desktop/ai_theme_app
export HF_HUB_OFFLINE=1
exec /opt/miniconda3/envs/theme_matcher_env/bin/python -m uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port 8090 >>'$LOG_DIR/stock_processing_service_8090.detached.log' 2>&1"
wait_health "stock_processing_service:8090" "http://127.0.0.1:8090/healthz"

echo "[start] web_app_service:8000 detached screen=${WEB_SESSION}"
screen -dmS "$WEB_SESSION" bash -lc "${runtime_env_prefix}
export WEB_APP_READ_MODE=http
export STOCK_PROCESSING_READ_BASE_URL=http://127.0.0.1:8090
exec /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m uvicorn web_app_service.main:app --host 0.0.0.0 --port 8000 >>'$LOG_DIR/web_app_service_8000.detached.log' 2>&1"
wait_health "web_app_service:8000" "http://127.0.0.1:8000/healthz"

if [[ -f "$ROOT_DIR/frontend/package.json" ]] && command -v npm >/dev/null 2>&1; then
  if pgrep -f "$FRONTEND_PATTERN" >/dev/null 2>&1 && curl -fsS --max-time 2 http://127.0.0.1:5173/ >/dev/null 2>&1; then
    echo "[skip] frontend vite already running"
  else
    pkill -f "$FRONTEND_PATTERN" >/dev/null 2>&1 || true
    echo "[start] frontend vite detached screen=${FRONTEND_SESSION}"
    screen -dmS "$FRONTEND_SESSION" bash -lc "cd '$ROOT_DIR/frontend' && exec npm run dev -- --host >>'$LOG_DIR/frontend_vite.detached.log' 2>&1"
  fi
fi

write_pid_file "stock_processing_service.api_app:app" 8090 "$LOG_DIR/stock_processing_service_8090.pid"
write_pid_file "web_app_service.main:app" 8000 "$LOG_DIR/web_app_service_8000.pid"
echo "$$" >"$LOG_DIR/start_new_chain_stack.detached.pid"

"$ROOT_DIR/scripts/status_new_chain_stack.sh"

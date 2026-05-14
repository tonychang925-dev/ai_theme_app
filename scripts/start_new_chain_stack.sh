#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
LOG_DIR="/tmp/ai_theme_realtime"
WEB_APP_PATTERN="uvicorn web_app_service.main:app --host 0.0.0.0 --port 8000"
WEB_APP_HEALTH_URL="http://127.0.0.1:8000/healthz"
SPS_PATTERN="uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port 8090"
SPS_HEALTH_URL="http://127.0.0.1:8090/healthz"
FRONTEND_PATTERN="vite --host|node .*vite .*--port 5173"
FRONTEND_HEALTH_URL="http://127.0.0.1:5173/"
WORKSPACE_VALIDATION_URL="http://127.0.0.1:8000/api/v2/workspace/market-validation?trade_date=2026-05-01"
INTEL_FEED_URL="http://127.0.0.1:8000/api/v2/intel/feed?date=2026-05-01&type=all&session=all&limit=1"
RECAP_SNAPSHOT_URL="http://127.0.0.1:8000/api/v2/post_market_snapshot?trade_date=2026-04-30"
CHECK_TRADE_DATE="${CHECK_TRADE_DATE:-$(date +%F)}"
WORKSPACE_VALIDATION_URL="http://127.0.0.1:8000/api/v2/workspace/market-validation?trade_date=${CHECK_TRADE_DATE}"
INTEL_FEED_URL="http://127.0.0.1:8000/api/v2/intel/feed?date=${CHECK_TRADE_DATE}&type=all&session=all&limit=1"
RECAP_SNAPSHOT_URL="http://127.0.0.1:8000/api/v2/post_market_snapshot?trade_date=${CHECK_TRADE_DATE}"

WITH_FRONTEND=false
RESTART=false

build_env_source_cmd() {
  cat <<'EOF'
load_env_file() {
  local file="$1"
  [[ -f "$file" ]] || return 0
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    local line="${raw#"${raw%%[![:space:]]*}"}"
    line="${line%"${line##*[![:space:]]}"}"
    [[ -n "$line" ]] || continue
    [[ "$line" == \#* ]] && continue
    [[ "$line" == *=* ]] || continue
    export "$line"
  done <"$file"
}
load_env_file .env.theme
load_env_file .env
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-frontend)
      WITH_FRONTEND=true
      shift
      ;;
    --restart)
      RESTART=true
      shift
      ;;
    *)
      echo "Unknown arg: $1"
      echo "Usage: ./scripts/start_new_chain_stack.sh [--with-frontend] [--restart]"
      exit 1
      ;;
  esac
done

mkdir -p "$LOG_DIR"

if [[ "$RESTART" == "true" ]]; then
  "$ROOT_DIR/scripts/stop_new_chain_stack.sh" --force $( [[ "$WITH_FRONTEND" == "true" ]] && echo "--with-frontend" )
fi

ensure_redis_up() {
  if ! command -v redis-cli >/dev/null 2>&1; then
    echo "[warn] redis-cli not found, skip redis bootstrap"
    return 1
  fi
  if redis-cli ping >/dev/null 2>&1; then
    echo "[ok] redis is up"
    return 0
  fi
  echo "[warn] redis is down, trying to start it..."
  if command -v brew >/dev/null 2>&1; then
    brew services start redis >/dev/null 2>&1 || true
    sleep 2
    if redis-cli ping >/dev/null 2>&1; then
      echo "[ok] redis started by brew services"
      return 0
    fi
  fi
  echo "[warn] redis still unavailable"
  return 1
}

start_frontend_if_needed() {
  if [[ "$WITH_FRONTEND" != "true" ]]; then
    return 0
  fi
  if pgrep -f "$FRONTEND_PATTERN" >/dev/null 2>&1; then
    if curl -fsS --max-time 2 "$FRONTEND_HEALTH_URL" >/dev/null 2>&1; then
      echo "[skip] frontend vite already running"
      return 0
    fi
    echo "[repair] frontend vite process exists but 5173 is not reachable, restarting..."
    pkill -f "$FRONTEND_PATTERN" || true
    sleep 1
  fi
  if [[ -f "$ROOT_DIR/frontend/package.json" ]] && command -v npm >/dev/null 2>&1; then
    echo "[start] frontend vite (fallback path)"
    (cd "$ROOT_DIR/frontend" && nohup npm run dev -- --host >"$LOG_DIR/frontend_vite.log" 2>&1 &)
    return 0
  fi
  echo "[warn] frontend vite not started (missing npm or frontend/package.json)"
  return 1
}

start_web_app_service() {
  # clear stale 8000 listeners to avoid bind conflicts
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -t -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | xargs || true)"
    if [[ -n "$pids" ]]; then
      echo "[repair] clearing existing 8000 listeners: $pids"
      kill $pids 2>/dev/null || true
      sleep 1
      pids="$(lsof -t -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | xargs || true)"
      if [[ -n "$pids" ]]; then
        kill -9 $pids 2>/dev/null || true
        sleep 1
      fi
    fi
  fi

  local max_attempts=3
  local attempt=1
  while [[ $attempt -le $max_attempts ]]; do
    echo "[start] web_app_service:8000 (attempt $attempt/$max_attempts)"
    (
      cd "$ROOT_DIR"
      nohup bash -lc "$(build_env_source_cmd) && . .venv/bin/activate && WEB_APP_READ_MODE=http STOCK_PROCESSING_READ_BASE_URL=http://127.0.0.1:8090 uvicorn web_app_service.main:app --host 0.0.0.0 --port 8000" \
        >"$LOG_DIR/web_app_service_8000.log" 2>&1 &
    )

    for _ in $(seq 1 25); do
      if curl -fsS --max-time 2 "$WEB_APP_HEALTH_URL" >/dev/null 2>&1; then
        # stability gate: must stay healthy for a short window
        sleep 1
        if curl -fsS --max-time 2 "$WEB_APP_HEALTH_URL" >/dev/null 2>&1; then
          echo "[ok] web_app_service:8000 ready"
          return 0
        fi
      fi
      sleep 1
    done

    echo "[warn] web_app_service:8000 not stable, restarting..."
    pkill -f "uvicorn web_app_service.main:app" >/dev/null 2>&1 || true
    sleep 1
    attempt=$((attempt + 1))
  done
  echo "[fail] web_app_service:8000 failed after retries"
  tail -n 120 "$LOG_DIR/web_app_service_8000.log" || true
  return 1
}

start_stock_processing_service() {
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -t -nP -iTCP:8090 -sTCP:LISTEN 2>/dev/null | xargs || true)"
    if [[ -n "$pids" ]]; then
      echo "[repair] clearing existing 8090 listeners: $pids"
      kill $pids 2>/dev/null || true
      sleep 1
      pids="$(lsof -t -nP -iTCP:8090 -sTCP:LISTEN 2>/dev/null | xargs || true)"
      if [[ -n "$pids" ]]; then
        kill -9 $pids 2>/dev/null || true
        sleep 1
      fi
    fi
  fi

  echo "[start] stock_processing_service:8090"
  (
    cd "$ROOT_DIR"
    nohup bash -lc "$(build_env_source_cmd) && PYTHONPATH=$ROOT_DIR HF_HUB_OFFLINE=1 /opt/miniconda3/envs/theme_matcher_env/bin/python -m uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port 8090" \
      >"$LOG_DIR/stock_processing_service_8090.log" 2>&1 &
  )

  for _ in $(seq 1 25); do
    if curl -fsS --max-time 2 "$SPS_HEALTH_URL" >/dev/null 2>&1; then
      echo "[ok] stock_processing_service:8090 ready"
      return 0
    fi
    sleep 1
  done
  echo "[fail] stock_processing_service:8090 failed"
  tail -n 120 "$LOG_DIR/stock_processing_service_8090.log" || true
  return 1
}

redis_ok=true
ensure_redis_up || redis_ok=false

# Root-cause fix: web_app_service must be up and stable first.
start_stock_processing_service || exit 1
start_web_app_service || exit 1
# hard cleanup old-chain runtime (8002/8003 wrappers etc)
pkill -f "theme_service.app:app.*8002" >/dev/null 2>&1 || true
pkill -f "frontend_bff.app:app.*8003" >/dev/null 2>&1 || true
pkill -f "start_frontend_bff_wrapper.sh" >/dev/null 2>&1 || true

realtime_ok=true
start_frontend_if_needed || realtime_ok=false

for _ in $(seq 1 20); do
  if curl -fsS --max-time 2 "$WORKSPACE_VALIDATION_URL" >/dev/null 2>&1; then
    echo "[ok] web_app workspace chain ready"
    break
  fi
  sleep 1
done

for _ in $(seq 1 20); do
  if curl -fsS --max-time 3 "$INTEL_FEED_URL" >/dev/null 2>&1; then
    echo "[ok] web_app intel feed chain ready"
    break
  fi
  sleep 1
done

if curl -fsS --max-time 3 "$RECAP_SNAPSHOT_URL" >/dev/null 2>&1; then
  echo "[ok] web_app recap snapshot chain ready"
else
  echo "[warn] web_app recap snapshot chain check failed: $RECAP_SNAPSHOT_URL"
fi

echo
echo "New-chain stack started."
if [[ "$realtime_ok" != "true" ]]; then
  echo "[warn] frontend may be unavailable (check frontend_vite.log)"
fi
echo "Status: ./scripts/status_new_chain_stack.sh"

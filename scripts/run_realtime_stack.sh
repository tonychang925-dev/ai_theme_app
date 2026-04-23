#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
LOG_DIR="/tmp/ai_theme_realtime"
mkdir -p "$LOG_DIR"

WITH_FRONTEND=false
RESTART=false
WATCHDOG_SECONDS=60

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
      echo "Usage: ./scripts/run_realtime_stack.sh [--with-frontend] [--restart]"
      exit 1
      ;;
  esac
done

if [[ ! -d "$ROOT_DIR" ]]; then
  echo "Project dir not found: $ROOT_DIR"
  exit 1
fi

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON_CMD="$ROOT_DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
else
  echo "python not found"
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl not found"
  exit 1
fi

if ! command -v redis-cli >/dev/null 2>&1; then
  echo "redis-cli not found"
  exit 1
fi

stop_pattern_if_running() {
  local pattern="$1"
  local name="$2"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "[restart] stopping ${name}..."
    pkill -f "$pattern" || true
    sleep 1
  fi
}

start_if_absent() {
  local pattern="$1"
  local cmd="$2"
  local log_file="$3"
  local name="$4"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "[skip] ${name} already running"
    return
  fi
  echo "[start] ${name}"
  (cd "$ROOT_DIR" && nohup bash -lc "$cmd" >"$log_file" 2>&1 &)
  sleep 1
}

ensure_bff_running() {
  local pattern="$1"
  local health_url="$2"
  local cmd="$3"
  local log_file="$4"

  if pgrep -f "$pattern" >/dev/null 2>&1; then
    if curl -fsS --max-time 2 "$health_url" >/dev/null 2>&1; then
      echo "[skip] frontend_bff:8003 already running"
      return
    fi
    echo "[repair] frontend_bff:8003 process exists but health check failed, restarting..."
    pkill -f "$pattern" || true
    sleep 1
  fi

  # 兜底：清理仍占用8003端口的残留进程（常见于--reload子进程残留）
  if command -v lsof >/dev/null 2>&1; then
    local port_pids
    port_pids="$(lsof -t -nP -iTCP:8003 -sTCP:LISTEN 2>/dev/null | xargs || true)"
    if [[ -n "$port_pids" ]]; then
      echo "[repair] port 8003 still occupied (PIDs: $port_pids), terminating..."
      kill $port_pids 2>/dev/null || true
      sleep 1
      local remain_pids
      remain_pids="$(lsof -t -nP -iTCP:8003 -sTCP:LISTEN 2>/dev/null | xargs || true)"
      if [[ -n "$remain_pids" ]]; then
        echo "[repair] force kill remaining 8003 listeners: $remain_pids"
        kill -9 $remain_pids 2>/dev/null || true
        sleep 1
      fi
    fi
  fi

  echo "[start] frontend_bff:8003"
  (cd "$ROOT_DIR" && nohup bash -lc "$cmd" >"$log_file" 2>&1 &)
  sleep 1
}

wait_http_ok() {
  local url="$1"
  local name="$2"
  local max_try="${3:-30}"
  local i=1
  while [[ $i -le $max_try ]]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[ok] ${name}: $url"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "[fail] ${name} not ready: $url"
  return 1
}

wait_proc_ok() {
  local pattern="$1"
  local name="$2"
  local max_try="${3:-10}"
  local i=1
  while [[ $i -le $max_try ]]; do
    if pgrep -f "$pattern" >/dev/null 2>&1; then
      echo "[ok] ${name} process ready"
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  echo "[fail] ${name} process not running"
  return 1
}

watchdog_proc_alive() {
  local pattern="$1"
  local name="$2"
  local wait_seconds="$3"
  sleep "$wait_seconds"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "[ok] ${name} still alive after ${wait_seconds}s"
    return 0
  fi
  echo "[fail] ${name} exited within ${wait_seconds}s"
  return 1
}

check_redis_ready() {
  local info loading bgsave
  if ! info="$(redis-cli INFO persistence 2>/dev/null)"; then
    echo "[fail] redis unavailable: redis-cli INFO persistence failed"
    return 1
  fi
  loading="$(printf '%s\n' "$info" | awk -F: '/^loading:/{print $2}' | tr -d '\r' | tail -n1)"
  bgsave="$(printf '%s\n' "$info" | awk -F: '/^rdb_bgsave_in_progress:/{print $2}' | tr -d '\r' | tail -n1)"

  if [[ "$loading" == "1" ]]; then
    echo "[fail] redis is loading dataset (loading=1), abort start to avoid memory pressure"
    echo "[tip] restart redis first, then rerun ./scripts/run_realtime_stack.sh --with-frontend --restart"
    return 1
  fi

  if [[ "$bgsave" == "1" ]]; then
    echo "[fail] redis bgsave in progress (rdb_bgsave_in_progress=1), abort start to avoid memory spikes"
    echo "[tip] wait for bgsave to finish or restart redis, then rerun start"
    return 1
  fi

  echo "[ok] redis persistence state healthy (loading=${loading:-unknown}, bgsave=${bgsave:-unknown})"
  return 0
}

START_SERVICES_PATTERN="python.*-m database_service.streams.start_services"
THEME_SERVICE_PATTERN="uvicorn theme_service.app:app --host 0.0.0.0 --port 8002"
BFF_WRAPPER_PATTERN="bash.*scripts/start_frontend_bff_wrapper.sh"
BFF_PATTERN="uvicorn frontend_bff.app:app --host 0.0.0.0 --port 8003"
FRONTEND_PATTERN="vite --host"

if [[ "$RESTART" == "true" ]]; then
  stop_pattern_if_running "$START_SERVICES_PATTERN" "stream services"
  stop_pattern_if_running "$THEME_SERVICE_PATTERN" "theme_service:8002"
  stop_pattern_if_running "$BFF_WRAPPER_PATTERN" "frontend_bff wrapper"
  stop_pattern_if_running "$BFF_PATTERN" "frontend_bff:8003"
  if [[ "$WITH_FRONTEND" == "true" ]]; then
    stop_pattern_if_running "$FRONTEND_PATTERN" "frontend vite"
  fi

  # 重启模式下清空旧日志，避免控制台持续显示历史错误。
  : > "$LOG_DIR/start_services.log"
  : > "$LOG_DIR/theme_service_8002.log"
  : > "$LOG_DIR/frontend_bff_8003.log"
  : > "$LOG_DIR/frontend_vite.log"
fi

echo "[env] export ALLOW_REALTIME_AUTO_THEME_CREATE=false"
export ALLOW_REALTIME_AUTO_THEME_CREATE=false
export STREAM_CLEANUP_INTERVAL_HOURS="${STREAM_CLEANUP_INTERVAL_HOURS:-2}"
export CONSUMER_GROUP_CLEANUP_INTERVAL_SECONDS="${CONSUMER_GROUP_CLEANUP_INTERVAL_SECONDS:-1800}"
export CONSUMER_GROUP_MAX_AGE_HOURS="${CONSUMER_GROUP_MAX_AGE_HOURS:-12}"
export PENDING_RECLAIM_ENABLED="${PENDING_RECLAIM_ENABLED:-true}"
export PENDING_RECLAIM_INTERVAL_SECONDS="${PENDING_RECLAIM_INTERVAL_SECONDS:-300}"
export PENDING_RECLAIM_STREAM_PATTERN="${PENDING_RECLAIM_STREAM_PATTERN:-stream:*}"
export PENDING_RECLAIM_MIN_IDLE_MS="${PENDING_RECLAIM_MIN_IDLE_MS:-300000}"
export PENDING_RECLAIM_COUNT="${PENDING_RECLAIM_COUNT:-50}"
export PENDING_RECLAIM_MAX_PER_GROUP="${PENDING_RECLAIM_MAX_PER_GROUP:-200}"
echo "[env] STREAM_CLEANUP_INTERVAL_HOURS=$STREAM_CLEANUP_INTERVAL_HOURS"
echo "[env] CONSUMER_GROUP_CLEANUP_INTERVAL_SECONDS=$CONSUMER_GROUP_CLEANUP_INTERVAL_SECONDS"
echo "[env] PENDING_RECLAIM_ENABLED=$PENDING_RECLAIM_ENABLED"
echo "[env] PENDING_RECLAIM_INTERVAL_SECONDS=$PENDING_RECLAIM_INTERVAL_SECONDS"

# Load local env files for runtime secrets/config.
load_env_file() {
  local file_path="$1"
  local line key value
  if [[ -f "$file_path" ]]; then
    echo "[env] load $(basename "$file_path")"
    while IFS= read -r line || [[ -n "$line" ]]; do
      line="${line%$'\r'}"
      [[ -z "${line//[[:space:]]/}" ]] && continue
      [[ "$line" =~ ^[[:space:]]*# ]] && continue
      [[ "$line" != *=* ]] && continue

      key="${line%%=*}"
      value="${line#*=}"
      key="${key//[[:space:]]/}"
      value="${value#"${value%%[![:space:]]*}"}"

      if [[ ( "$value" == \"*\" && "$value" == *\" ) || ( "$value" == \'*\' && "$value" == *\' ) ]]; then
        value="${value:1:${#value}-2}"
      fi

      [[ -n "$key" ]] && export "$key=$value"
    done < "$file_path"
  fi
}

load_env_file "$ROOT_DIR/.env.local"
load_env_file "$ROOT_DIR/.env.theme"
load_env_file "$ROOT_DIR/.env"

export BFF_ACCESS_LOG="${BFF_ACCESS_LOG:-false}"
if [[ "$BFF_ACCESS_LOG" == "true" ]]; then
  BFF_ACCESS_LOG_FLAG=""
else
  BFF_ACCESS_LOG_FLAG="--no-access-log"
fi
echo "[env] BFF_ACCESS_LOG=$BFF_ACCESS_LOG"

check_redis_ready

start_if_absent \
  "$START_SERVICES_PATTERN" \
  "bash $ROOT_DIR/scripts/start_stream_services_wrapper.sh" \
  "$LOG_DIR/start_services.log" \
  "stream services"

start_if_absent \
  "$THEME_SERVICE_PATTERN" \
  "$PYTHON_CMD -m uvicorn theme_service.app:app --host 0.0.0.0 --port 8002 --no-access-log" \
  "$LOG_DIR/theme_service_8002.log" \
  "theme_service:8002"

ensure_bff_running \
  "$BFF_WRAPPER_PATTERN" \
  "http://127.0.0.1:8003/health" \
  "BFF_PYTHON_CMD=$PYTHON_CMD BFF_ACCESS_LOG_FLAG='$BFF_ACCESS_LOG_FLAG' bash $ROOT_DIR/scripts/start_frontend_bff_wrapper.sh" \
  "$LOG_DIR/frontend_bff_8003.log"

if [[ "$WITH_FRONTEND" == "true" ]]; then
  if [[ -f "$ROOT_DIR/frontend/package.json" ]] && command -v npm >/dev/null 2>&1; then
    if pgrep -f "$FRONTEND_PATTERN" >/dev/null 2>&1; then
      echo "[skip] frontend vite already running"
    else
      echo "[start] frontend vite"
      (cd "$ROOT_DIR/frontend" && nohup npm run dev -- --host >"$LOG_DIR/frontend_vite.log" 2>&1 &)
    fi
  else
    echo "[warn] frontend not started (missing npm or frontend/package.json)"
  fi
fi

wait_proc_ok "$START_SERVICES_PATTERN" "stream services" 15
wait_proc_ok "$THEME_SERVICE_PATTERN" "theme_service:8002" 15
if [[ "$WITH_FRONTEND" == "true" ]]; then
  wait_proc_ok "$FRONTEND_PATTERN" "frontend vite" 10
fi

wait_http_ok "http://127.0.0.1:8002/health" "theme_service" 40
wait_http_ok "http://127.0.0.1:8003/health" "frontend_bff" 40
curl -fsS "http://127.0.0.1:8003/api/intel/feed?type=event_review&session=all&limit=5" >/dev/null
echo "[ok] intel event_review endpoint ready"

if ! watchdog_proc_alive "$START_SERVICES_PATTERN" "stream services" "$WATCHDOG_SECONDS"; then
  echo "[diag] tail start_services.log"
  tail -n 120 "$LOG_DIR/start_services.log" || true
  exit 1
fi

if ! watchdog_proc_alive "$THEME_SERVICE_PATTERN" "theme_service:8002" 15; then
  echo "[diag] tail theme_service_8002.log"
  tail -n 120 "$LOG_DIR/theme_service_8002.log" || true
  exit 1
fi

if [[ "$WITH_FRONTEND" == "true" ]]; then
  if ! watchdog_proc_alive "$FRONTEND_PATTERN" "frontend vite" 10; then
    echo "[diag] tail frontend_vite.log"
    tail -n 80 "$LOG_DIR/frontend_vite.log" || true
    exit 1
  fi
fi

cat <<EOF

Realtime stack is up.
Logs:
  $LOG_DIR/start_services.log
  $LOG_DIR/theme_service_8002.log
  $LOG_DIR/frontend_bff_8003.log
  $LOG_DIR/frontend_vite.log

Quick checks:
  curl -sS "http://127.0.0.1:8002/health"
  curl -sS "http://127.0.0.1:8003/health"
  curl -sS "http://127.0.0.1:8003/api/intel/feed?type=all&session=all&limit=5"
  curl -sS "http://127.0.0.1:8003/api/intel/feed?type=event_review&session=all&limit=20"

Stop commands:
  pkill -f "$START_SERVICES_PATTERN"
  pkill -f "$THEME_SERVICE_PATTERN"
  pkill -f "$BFF_WRAPPER_PATTERN"
  pkill -f "$BFF_PATTERN"
  pkill -f "$FRONTEND_PATTERN"
EOF

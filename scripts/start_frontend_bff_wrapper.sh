#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
PYTHON_CMD="${BFF_PYTHON_CMD:-$ROOT_DIR/.venv/bin/python}"
HOST="${BFF_HOST:-0.0.0.0}"
PORT="${BFF_PORT:-8003}"
ACCESS_LOG_FLAG="${BFF_ACCESS_LOG_FLAG:---no-access-log}"
RESTART_DELAY_SECONDS="${BFF_RESTART_DELAY_SECONDS:-2}"
MAX_RESTARTS="${BFF_MAX_RESTARTS:-0}" # 0 means unlimited

if [[ ! -x "$PYTHON_CMD" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
  else
    echo "[bff-wrapper] python not found"
    exit 127
  fi
fi

echo "[bff-wrapper] start pid=$$ at $(date '+%F %T')"
echo "[bff-wrapper] python=$PYTHON_CMD host=$HOST port=$PORT access_log_flag=$ACCESS_LOG_FLAG"

child_pid=""
stopping="false"
restart_count=0

term_handler() {
  local sig="$1"
  echo "[bff-wrapper] received signal $sig at $(date '+%F %T')"
  stopping="true"
  if [[ -n "$child_pid" ]] && kill -0 "$child_pid" >/dev/null 2>&1; then
    kill -TERM "$child_pid" >/dev/null 2>&1 || true
    wait "$child_pid" || true
  fi
  exit 0
}

trap 'term_handler TERM' TERM
trap 'term_handler INT' INT
trap 'term_handler HUP' HUP

while true; do
  (
    cd "$ROOT_DIR"
    exec "$PYTHON_CMD" -m uvicorn frontend_bff.app:app --host "$HOST" --port "$PORT" $ACCESS_LOG_FLAG
  ) &
  child_pid=$!
  echo "[bff-wrapper] child pid=$child_pid"

  set +e
  wait "$child_pid"
  rc=$?
  set -e

  if [[ "$stopping" == "true" ]]; then
    echo "[bff-wrapper] child exited during shutdown rc=$rc"
    exit 0
  fi

  if [[ $rc -eq 0 ]]; then
    echo "[bff-wrapper] child exited rc=0 unexpectedly, restarting in ${RESTART_DELAY_SECONDS}s"
  elif [[ $rc -ge 128 ]]; then
    sig=$((rc - 128))
    echo "[bff-wrapper] child exited by signal=$sig rc=$rc, restarting in ${RESTART_DELAY_SECONDS}s"
  else
    echo "[bff-wrapper] child exited rc=$rc, restarting in ${RESTART_DELAY_SECONDS}s"
  fi

  restart_count=$((restart_count + 1))
  if [[ "$MAX_RESTARTS" != "0" ]] && [[ $restart_count -ge $MAX_RESTARTS ]]; then
    echo "[bff-wrapper] max restarts reached ($MAX_RESTARTS), exiting"
    exit 1
  fi
  sleep "$RESTART_DELAY_SECONDS"
done


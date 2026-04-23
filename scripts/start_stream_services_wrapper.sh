#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
THEME_MATCHER_PYTHON="/opt/miniconda3/envs/theme_matcher_env/bin/python"
PYTHON_CMD="${STREAM_SERVICES_PYTHON:-}"

if [[ -z "$PYTHON_CMD" ]]; then
  if [[ -x "$THEME_MATCHER_PYTHON" ]]; then
    PYTHON_CMD="$THEME_MATCHER_PYTHON"
  elif [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
    PYTHON_CMD="$ROOT_DIR/.venv/bin/python"
  elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
  else
    echo "[wrapper] python not found"
    exit 127
  fi
fi

if [[ ! -x "$PYTHON_CMD" ]] && [[ "$PYTHON_CMD" != "python3" ]]; then
  echo "[wrapper] invalid STREAM_SERVICES_PYTHON: $PYTHON_CMD"
  exit 127
fi

echo "[wrapper] start stream services wrapper pid=$$ at $(date '+%F %T')"
echo "[wrapper] selected python: $PYTHON_CMD"
echo "[wrapper] cmd: $PYTHON_CMD -m database_service.streams.start_services"

term_handler() {
  local sig="$1"
  echo "[wrapper] received signal $sig at $(date '+%F %T')"
  if [[ -n "${child_pid:-}" ]] && kill -0 "$child_pid" >/dev/null 2>&1; then
    kill -TERM "$child_pid" >/dev/null 2>&1 || true
    wait "$child_pid" || true
  fi
  exit 0
}

trap 'term_handler TERM' TERM
trap 'term_handler INT' INT
trap 'term_handler HUP' HUP

(
  cd "$ROOT_DIR"
  exec "$PYTHON_CMD" -m database_service.streams.start_services
) &
child_pid=$!
echo "[wrapper] child pid=$child_pid"

set +e
wait "$child_pid"
rc=$?
set -e

if [[ $rc -ge 128 ]]; then
  sig=$((rc - 128))
  echo "[wrapper] child exited by signal=$sig rc=$rc at $(date '+%F %T')"
else
  echo "[wrapper] child exited rc=$rc at $(date '+%F %T')"
fi

exit "$rc"

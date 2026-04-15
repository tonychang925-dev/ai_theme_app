#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
PYTHON_CMD="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$PYTHON_CMD" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
  else
    echo "[wrapper] python not found"
    exit 127
  fi
fi

echo "[wrapper] start stream services wrapper pid=$$ at $(date '+%F %T')"
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

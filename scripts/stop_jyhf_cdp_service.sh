#!/usr/bin/env bash
set -euo pipefail

PORT="${JYHF_CDP_SERVICE_PORT:-8095}"
HOST="${JYHF_CDP_SERVICE_HOST:-127.0.0.1}"
PID_FILE="tmp/realtime/jyhf_cdp_service/service.pid"

curl -fsS -X POST "http://${HOST}:${PORT}/collector/stop" >/dev/null 2>&1 || true

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" || true)"
  if [[ -n "${PID:-}" ]] && kill -0 "$PID" >/dev/null 2>&1; then
    kill "$PID" || true
    sleep 1
    if kill -0 "$PID" >/dev/null 2>&1; then
      kill -TERM "$PID" || true
    fi
  fi
  rm -f "$PID_FILE"
else
  pkill -f "uvicorn services.jyhf_cdp_service.app:app" || true
fi

echo "jyhf_cdp_service stop requested on ${HOST}:${PORT}"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

mkdir -p logs tmp/realtime/jyhf_cdp_service
PORT="${JYHF_CDP_SERVICE_PORT:-8095}"
HOST="${JYHF_CDP_SERVICE_HOST:-127.0.0.1}"
LOG_FILE="logs/jyhf_cdp_service.log"
PID_FILE="tmp/realtime/jyhf_cdp_service/service.pid"
echo "$$" > "$PID_FILE"

exec "${PYTHON:-.venv/bin/python}" -m uvicorn services.jyhf_cdp_service.app:app \
  --host "$HOST" \
  --port "$PORT" \
  --workers 1 \
  >> "$LOG_FILE" 2>&1

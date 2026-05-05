#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
WEB_APP_PATTERN="uvicorn web_app_service.main:app --host 0.0.0.0 --port 8000"
SPS_PATTERN="uvicorn stock_processing_service.api_app:app --host 127.0.0.1 --port 8090"

WITH_FRONTEND=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-frontend)
      WITH_FRONTEND=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    *)
      echo "Unknown arg: $1"
      echo "Usage: ./scripts/stop_new_chain_stack.sh [--with-frontend] [--force]"
      exit 1
      ;;
  esac
done

ARGS=()
if [[ "$WITH_FRONTEND" == "true" ]]; then
  ARGS+=(--with-frontend)
fi
if [[ "$FORCE" == "true" ]]; then
  ARGS+=(--force)
fi
# stop new-chain surface first
pkill -f "node.*vite.*5173" >/dev/null 2>&1 || true
pkill -f "vite --host" >/dev/null 2>&1 || true

# stop old-chain services explicitly (cleanup)
pkill -f "theme_service.app:app.*8002" >/dev/null 2>&1 || true
pkill -f "frontend_bff.app:app.*8003" >/dev/null 2>&1 || true
pkill -f "start_frontend_bff_wrapper.sh" >/dev/null 2>&1 || true
pkill -f "database_service.streams.start_services" >/dev/null 2>&1 || true

if pgrep -f "$WEB_APP_PATTERN" >/dev/null 2>&1; then
  echo "[stop] web_app_service:8000"
  if [[ "$FORCE" == "true" ]]; then
    pkill -9 -f "$WEB_APP_PATTERN" || true
  else
    pkill -f "$WEB_APP_PATTERN" || true
  fi
else
  echo "[skip] web_app_service:8000 not running"
fi

if pgrep -f "$SPS_PATTERN" >/dev/null 2>&1; then
  echo "[stop] stock_processing_service:8090"
  if [[ "$FORCE" == "true" ]]; then
    pkill -9 -f "$SPS_PATTERN" || true
  else
    pkill -f "$SPS_PATTERN" || true
  fi
else
  echo "[skip] stock_processing_service:8090 not running"
fi

echo
echo "New-chain stack stopped."

#!/usr/bin/env bash
set -euo pipefail

PORT="${JYHF_CDP_SERVICE_PORT:-8095}"
pkill -f "uvicorn services.jyhf_cdp_service.app:app" || true
echo "jyhf_cdp_service stop requested on port ${PORT}"


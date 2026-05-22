#!/usr/bin/env bash
set -euo pipefail
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
export WEB_APP_READ_MODE=http
export STOCK_PROCESSING_READ_BASE_URL=http://127.0.0.1:8090
exec /Users/admin/Desktop/ai_theme_app/.venv/bin/python -m uvicorn web_app_service.main:app --host 0.0.0.0 --port 8000

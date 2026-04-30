#!/usr/bin/env bash
set -euo pipefail

[[ -x scripts/run_web_app_http_smoke.sh ]] || { echo "missing executable scripts/run_web_app_http_smoke.sh"; exit 1; }
[[ -f scripts/verify_web_app_http_smoke.py ]] || { echo "missing scripts/verify_web_app_http_smoke.py"; exit 1; }

grep -q "stock_processing_service.api_app:app" scripts/run_web_app_http_smoke.sh || { echo "missing sps app target"; exit 1; }
grep -q "web_app_service.main:app" scripts/run_web_app_http_smoke.sh || { echo "missing web app target"; exit 1; }
grep -q "api/v2/post_market_snapshot" scripts/run_web_app_http_smoke.sh || { echo "missing post_market endpoint"; exit 1; }
grep -q "api/v2/strong_watch" scripts/run_web_app_http_smoke.sh || { echo "missing strong_watch endpoint"; exit 1; }
grep -q "api/v2/w2s_candidates" scripts/run_web_app_http_smoke.sh || { echo "missing w2s endpoint"; exit 1; }

echo "smoke scripts contract check passed"

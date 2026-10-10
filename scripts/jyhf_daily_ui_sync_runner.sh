#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="/Users/admin/Desktop/ai_theme_app"
PYTHON="/opt/miniconda3/envs/theme_matcher_env/bin/python"
cd "$PROJECT_ROOT"
exec "$PYTHON" -m tools.jyhf_daily_sync_v1.runner --mode daily

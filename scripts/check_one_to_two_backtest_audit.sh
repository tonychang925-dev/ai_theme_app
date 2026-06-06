#!/usr/bin/env bash
set -euo pipefail

exec ./.venv/bin/python scripts/check_one_to_two_backtest_audit.py "$@"

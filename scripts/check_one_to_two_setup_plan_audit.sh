#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env.theme ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.theme
  set +a
fi

exec ./.venv/bin/python scripts/check_one_to_two_setup_plan_audit.py "$@"

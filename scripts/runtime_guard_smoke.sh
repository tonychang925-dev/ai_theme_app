#!/usr/bin/env bash

set -euo pipefail

URL="${RUNTIME_GUARD_SMOKE_URL:-http://127.0.0.1:8090/api/v1/debug/runtime_guard_smoke}"
payload="$(curl -fsS --max-time 10 "$URL")"
echo "$payload"

if command -v jq >/dev/null 2>&1; then
  ok="$(printf '%s' "$payload" | jq -r '.ok')"
  decision="$(printf '%s' "$payload" | jq -r '.decision')"
  reason="$(printf '%s' "$payload" | jq -r '.reason_code')"
  guard="$(printf '%s' "$payload" | jq -r '.guard_applied')"
  if [[ "$ok" != "true" || "$decision" != "HUMAN_REVIEW" || "$reason" != "weak_v1_direct_hit_review" || "$guard" != "true" ]]; then
    echo "[fail] runtime guard smoke failed" >&2
    exit 1
  fi
fi

echo "[ok] runtime guard smoke passed"

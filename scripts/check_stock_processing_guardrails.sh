#!/usr/bin/env bash
set -euo pipefail

ROOT="stock_processing_service"
FAIL=0

check_hits() {
  local scope="$1"
  local pattern="$2"
  local label="$3"
  if rg -n "$pattern" "$scope" --glob '!**/*.md' --glob '!**/tests/**' >/tmp/sps_guardrail_hits.txt; then
    echo "[FAIL] ${label}"
    cat /tmp/sps_guardrail_hits.txt
    FAIL=1
  fi
}

# Strict boundary checks in application/domain layers.
check_hits "$ROOT/application" "\._client\b|\._db\b|\bexecute_query\b|\basyncpg\b" "application layer contains forbidden gateway/sql symbols"
check_hits "$ROOT/domain" "\._client\b|\._db\b|\bexecute_query\b|\basyncpg\b" "domain layer contains forbidden gateway/sql symbols"

# Basic SQL literal checks across stock_processing_service (except legacy adapters/tests/docs).
if rg -n "\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b" "$ROOT" \
  --glob '!**/*.md' \
  --glob '!**/tests/**' \
  --glob '!**/scripts/**' \
  --glob '!**/db_*_gateway.py' >/tmp/sps_sql_hits.txt; then
  echo "[FAIL] stock_processing_service contains SQL literals"
  cat /tmp/sps_sql_hits.txt
  FAIL=1
fi

if [[ "$FAIL" -ne 0 ]]; then
  exit 1
fi

echo "[PASS] stock_processing_service guardrails"

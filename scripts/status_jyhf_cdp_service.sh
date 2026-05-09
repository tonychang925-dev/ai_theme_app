#!/usr/bin/env bash
set -euo pipefail

PORT="${JYHF_CDP_SERVICE_PORT:-8095}"
curl -fsS "http://127.0.0.1:${PORT}/health"
echo
curl -fsS "http://127.0.0.1:${PORT}/status"
echo


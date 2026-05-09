#!/usr/bin/env bash
set -euo pipefail

PORT="${JYHF_CDP_SERVICE_PORT:-8095}"
HOST="${JYHF_CDP_SERVICE_HOST:-127.0.0.1}"
curl -fsS "http://${HOST}:${PORT}/health"
echo
curl -fsS "http://${HOST}:${PORT}/status"
echo

#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="/Users/admin/Desktop/ai_theme_app"
BFF_HEALTH_URL="http://127.0.0.1:8003/health"
THEME_HEALTH_URL="http://127.0.0.1:8002/health"
BFF_FEED_URL="http://127.0.0.1:8003/api/intel/feed?type=all&session=all&limit=3"
BFF_REVIEW_URL="http://127.0.0.1:8003/api/intel/feed?type=event_review&session=all&limit=3"

START_SERVICES_PATTERN="database_service\\.streams\\.start_services"
THEME_SERVICE_PATTERN="theme_service\\.app:app.*8002"
BFF_WRAPPER_PATTERN="start_frontend_bff_wrapper\\.sh"
BFF_PATTERN="frontend_bff\\.app:app.*8003"
FRONTEND_PATTERN="vite --host|node .*vite .*--port 5173"

run_cmd_with_timeout() {
  local timeout_sec="$1"
  shift
  local tmp_out
  tmp_out="$(mktemp)"
  "$@" >"$tmp_out" 2>/dev/null &
  local cmd_pid=$!
  local elapsed=0

  while kill -0 "$cmd_pid" 2>/dev/null; do
    if [[ "$elapsed" -ge "$timeout_sec" ]]; then
      kill -9 "$cmd_pid" >/dev/null 2>&1 || true
      wait "$cmd_pid" >/dev/null 2>&1 || true
      rm -f "$tmp_out"
      return 124
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done

  wait "$cmd_pid"
  local rc=$?
  cat "$tmp_out"
  rm -f "$tmp_out"
  return "$rc"
}

print_proc() {
  local pattern="$1"
  local name="$2"
  if pgrep -f "$pattern" >/dev/null 2>&1; then
    echo "[up]   $name"
    pgrep -fal "$pattern" | sed 's/^/       /'
  elif [[ "$name" == "frontend_bff:8003" ]] && curl -fsS --max-time 2 "$BFF_HEALTH_URL" >/dev/null 2>&1; then
    echo "[up]   $name (health-check)"
  else
    echo "[down] $name"
  fi
}

print_http() {
  local url="$1"
  local name="$2"
  local attempts=3
  local i=1
  local err_file
  err_file="$(mktemp)"
  while [[ $i -le $attempts ]]; do
    if curl -fsS --max-time 2 "$url" >/dev/null 2>"$err_file"; then
      rm -f "$err_file"
      echo "[ok]   $name"
      return
    fi
    if [[ $i -lt $attempts ]]; then
      sleep 1
    fi
    i=$((i + 1))
  done
  local err_msg
  err_msg="$(tail -n 1 "$err_file" | tr -d '\r')"
  rm -f "$err_file"
  if [[ -n "$err_msg" ]]; then
    echo "[fail] $name ($err_msg)"
  else
    echo "[fail] $name"
  fi
}

print_stream_len() {
  local stream="$1"
  if command -v redis-cli >/dev/null 2>&1; then
    local len
    len="$(run_cmd_with_timeout 2 redis-cli xlen "$stream" || true)"
    if [[ -n "$len" ]]; then
      echo "       $stream = $len"
    else
      echo "       $stream = (unavailable)"
    fi
  else
    echo "       $stream = (redis-cli not found)"
  fi
}

echo "Realtime Stack Status"
echo "====================="
echo "Project: $ROOT_DIR"
echo

echo "[process]"
print_proc "$START_SERVICES_PATTERN" "stream services"
print_proc "$THEME_SERVICE_PATTERN" "theme_service:8002"
print_proc "$BFF_WRAPPER_PATTERN" "frontend_bff wrapper"
print_proc "$BFF_PATTERN" "frontend_bff:8003"
print_proc "$FRONTEND_PATTERN" "frontend vite"
echo

echo "[http]"
print_http "$THEME_HEALTH_URL" "theme_service /health"
print_http "$BFF_HEALTH_URL" "bff /health"
print_http "$BFF_FEED_URL" "bff /api/intel/feed?type=all"
print_http "$BFF_REVIEW_URL" "bff /api/intel/feed?type=event_review"
echo

echo "[redis stream length]"
print_stream_len "stream:news:raw"
print_stream_len "stream:events:structured"
print_stream_len "stream:event:feed"
print_stream_len "stream:events:pending"
echo

echo "[tip]"
echo "  start: ./scripts/run_realtime_stack.sh --with-frontend --restart"
echo "  stop : ./scripts/stop_realtime_stack.sh --with-frontend"

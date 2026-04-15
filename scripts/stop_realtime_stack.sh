#!/usr/bin/env bash

set -euo pipefail

WITH_FRONTEND=false
FORCE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-frontend)
      WITH_FRONTEND=true
      shift
      ;;
    --force)
      FORCE=true
      shift
      ;;
    *)
      echo "Unknown arg: $1"
      echo "Usage: ./scripts/stop_realtime_stack.sh [--with-frontend] [--force]"
      exit 1
      ;;
  esac
done

stop_pattern() {
  local pattern="$1"
  local name="$2"

  # 查找进程
  local pids
  if [[ "$name" == "frontend_bff:8003" ]]; then
    # 对于BFF，使用更宽松的匹配，排除当前脚本进程和父进程
    local current_pid=$$
    local parent_pid=$PPID
    pids=$(ps aux | grep -i "frontend_bff" | grep -i "8003" | grep -v grep | awk '{print $2}' | tr '\n' ' ' || echo "")
    # 过滤掉当前进程和父进程
    local filtered_pids=""
    for pid in $pids; do
      if [[ "$pid" != "$current_pid" && "$pid" != "$parent_pid" ]]; then
        filtered_pids="$filtered_pids $pid"
      fi
    done
    pids=$(echo "$filtered_pids" | xargs)
  else
    pids=$(pgrep -f "$pattern" 2>/dev/null || echo "")
  fi

  # 清理空白
  pids=$(echo "$pids" | xargs)

  if [[ -z "$pids" ]]; then
    echo "[skip] ${name} not running"
    return 0
  fi

  echo "[stop] ${name} (PIDs: $pids)"

  # 停止进程
  if [[ "$FORCE" == "true" ]]; then
    echo "  Using force kill (SIGKILL)"
    kill -9 $pids 2>/dev/null || true
  else
    echo "  Using graceful kill (SIGTERM)"
    kill $pids 2>/dev/null || true

    # 等待进程终止，最多5秒
    local wait_seconds=5
    local waited=0

    while [[ $waited -lt $wait_seconds ]]; do
      # 检查是否还有进程在运行
      local still_running=false
      for pid in $pids; do
        # 使用ps检查进程是否仍然存在
        if ps -p $pid >/dev/null 2>&1; then
          still_running=true
          break
        fi
      done

      if [[ "$still_running" == "false" ]]; then
        break
      fi

      sleep 1
      waited=$((waited + 1))
    done

    # 检查是否还有进程在运行，使用强制终止
    local processes_still_running=false
    for pid in $pids; do
      if ps -p $pid >/dev/null 2>&1; then
        processes_still_running=true
        break
      fi
    done

    if [[ "$processes_still_running" == "true" ]]; then
      echo "  Processes still running after ${wait_seconds}s, using SIGKILL"
      kill -9 $pids 2>/dev/null || true
      sleep 1
    fi
  fi

  # 最终检查 - 给进程一点时间完全终止
  sleep 1

  local final_remaining=0
  local still_running_pids=""
  for pid in $pids; do
    # 检查进程是否仍然存在
    if ps -p $pid >/dev/null 2>&1; then
      ((final_remaining++))
      still_running_pids="$still_running_pids $pid"
    fi
  done

  if [[ $final_remaining -gt 0 ]]; then
    echo "  Warning: ${final_remaining} process(es) still running (PIDs:${still_running_pids})"
    if [[ "$name" != "frontend_bff:8003" ]]; then
      return 1
    fi
  else
    echo "  Successfully stopped"
  fi

  # BFF额外兜底：按端口清理监听进程，避免--reload子进程残留占用8003
  if [[ "$name" == "frontend_bff:8003" ]] && command -v lsof >/dev/null 2>&1; then
    local port_pids
    port_pids="$(lsof -t -nP -iTCP:8003 -sTCP:LISTEN 2>/dev/null | xargs || true)"
    if [[ -n "$port_pids" ]]; then
      echo "  Port 8003 still occupied, terminating PIDs: $port_pids"
      if [[ "$FORCE" == "true" ]]; then
        kill -9 $port_pids 2>/dev/null || true
      else
        kill $port_pids 2>/dev/null || true
        sleep 1
        local remain_pids
        remain_pids="$(lsof -t -nP -iTCP:8003 -sTCP:LISTEN 2>/dev/null | xargs || true)"
        if [[ -n "$remain_pids" ]]; then
          kill -9 $remain_pids 2>/dev/null || true
        fi
      fi
    fi
  fi

  return 0
}

START_SERVICES_PATTERN="database_service\\.streams\\.start_services"
BFF_PATTERN="frontend_bff\\.app:app.*8003"
FRONTEND_PATTERN="node.*vite|vite.*5173|vite --host"

stop_pattern "$START_SERVICES_PATTERN" "stream services"

# Only stop BFF if WITH_FRONTEND is true (stopping entire stack)
if [[ "$WITH_FRONTEND" == "true" ]]; then
  stop_pattern "$BFF_PATTERN" "frontend_bff:8003"
  stop_pattern "$FRONTEND_PATTERN" "frontend vite"
fi

echo
echo "Stopped requested services."
echo "Check:"
echo "  pgrep -f \"$START_SERVICES_PATTERN\""
echo "  pgrep -f \"$BFF_PATTERN\""
if [[ "$WITH_FRONTEND" == "true" ]]; then
  echo "  pgrep -f \"$FRONTEND_PATTERN\""
fi

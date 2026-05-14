#!/bin/bash
# 启动 web_app + cloudflared 隧道（含自动重连）
# 用法: ./scripts/start_tunnel.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "[tunnel] starting web_app_service:8000..."
pkill -f "uvicorn web_app_service.main" 2>/dev/null || true
sleep 1

PYTHON_BIN="$ROOT/.venv/bin/python"
if ! $PYTHON_BIN -c "import passlib" 2>/dev/null; then
    echo "[tunnel] installing auth deps..."
    $PYTHON_BIN -m pip install -q passlib bcrypt==4.0.1 pyjwt
fi

PYTHONPATH="$ROOT" nohup $PYTHON_BIN -m uvicorn web_app_service.main:app --host 0.0.0.0 --port 8000 > /tmp/webapp_tunnel.log 2>&1 &
sleep 2

if curl -sf http://127.0.0.1:8000/healthz > /dev/null 2>&1; then
    echo "[tunnel] web_app_service healthy"
else
    echo "[tunnel] ERROR: web_app_service failed to start"
    tail -10 /tmp/webapp_tunnel.log
    exit 1
fi

echo "[tunnel] starting cloudflared (auto-restart on disconnect)..."
pkill -f cloudflared 2>/dev/null || true
sleep 1

# Auto-restart loop: cloudflared 断线自动重连
while true; do
    echo "[tunnel] cloudflared connecting..."
    cloudflared tunnel --url http://localhost:8000 2>&1 | while read line; do
        echo "$line"
        if echo "$line" | grep -q "trycloudflare.com"; then
            echo "$line" | grep -o "https://[^ ]*trycloudflare.com" > /tmp/current_tunnel_url.txt
            echo "[tunnel] >>> PUBLIC URL: $(cat /tmp/current_tunnel_url.txt)"
        fi
    done
    echo "[tunnel] cloudflared disconnected, restarting in 5s..."
    sleep 5
done

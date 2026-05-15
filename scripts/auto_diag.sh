#!/usr/bin/env bash
# 全自动诊断：启动 Electron(debug模式) → 等就绪 → CDP 触发 start → 监控状态变化 → 输出报告
set -euo pipefail

PROJECT="/Users/admin/Desktop/ai_theme_app"
DESKTOP="$PROJECT/desktop"
PYTHON="$PROJECT/.venv/bin/python"
CDP_PORT=9224

cleanup() {
  echo "[cleanup] 关闭 Electron..."
  kill $ELECTRON_PID 2>/dev/null || true
  sleep 2
}
trap cleanup EXIT

echo "========================================"
echo " 自动诊断：CDP 启动 + 前端状态追踪"
echo "========================================"

# 1. 杀掉残留
kill $(lsof -t -i TCP:8000 -s TCP:LISTEN 2>/dev/null) 2>/dev/null || true
kill $(lsof -t -i TCP:8095 -s TCP:LISTEN 2>/dev/null) 2>/dev/null || true
kill $(lsof -t -i TCP:$CDP_PORT -s TCP:LISTEN 2>/dev/null) 2>/dev/null || true
sleep 2

# 2. 编译 Electron
echo "[1/6] 编译 Electron..."
cd "$DESKTOP"
npx tsc -p tsconfig.json 2>&1 | tail -1

# 3. 启动 Electron（debug 模式）
echo "[2/6] 启动 Electron (CDP :$CDP_PORT)..."
npx electron dist-electron/main.js --remote-debugging-port=$CDP_PORT --remote-allow-origins=* &
ELECTRON_PID=$!
echo "  Electron PID=$ELECTRON_PID"

# 4. 等待 web_app 就绪
echo "[3/6] 等待 web_app :8000..."
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo "  web_app 就绪 (${i}s)"
    break
  fi
  sleep 1
done

# 5. 杀掉旧 CDP（如果残留）
kill $(lsof -t -i TCP:8095 -s TCP:LISTEN 2>/dev/null) 2>/dev/null || true
sleep 1

# 6. 通过 CDP 连接 Electron 渲染进程
echo "[4/6] 连接 CDP 获取渲染进程..."

# 等待 CDP 端口可用
for i in $(seq 1 20); do
  if curl -s "http://127.0.0.1:$CDP_PORT/json" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

TARGETS=$(curl -s "http://127.0.0.1:$CDP_PORT/json")
WS_URL=$(echo "$TARGETS" | python3 -c "
import json,sys
pages=json.load(sys.stdin)
for p in pages:
    if p.get('type')=='page' and 'localhost' in p.get('url',''):
        print(p.get('webSocketDebuggerUrl',''))
        break
")
if [ -z "$WS_URL" ]; then
  WS_URL=$(echo "$TARGETS" | python3 -c "
import json,sys
pages=json.load(sys.stdin)
for p in pages:
    if p.get('type')=='page':
        print(p.get('webSocketDebuggerUrl',''))
        break
")
fi
echo "  WS: ${WS_URL:0:60}..."

# CDP 辅助函数
cdp_eval() {
  local expr="$1"
  $PYTHON -c "
import json, time, websocket, sys
ws = websocket.create_connection('$WS_URL', timeout=10)
ws.send(json.dumps({'id':1,'method':'Runtime.enable'}))
time.sleep(0.3)
try:
    ws.settimeout(0.3)
    while True: ws.recv()
except: pass
ws.settimeout(10)
ws.send(json.dumps({'id':2,'method':'Runtime.evaluate','params':{'expression':r'''$expr''','returnByValue':True}}))
deadline=time.time()+10
while time.time()<deadline:
    try: msg=json.loads(ws.recv())
    except: continue
    if msg.get('id')==2:
        print(json.dumps(msg.get('result',{}).get('result',{}).get('value'),ensure_ascii=False))
        break
ws.close()
" 2>/dev/null
}

# 7. 触发 CDP 启动 + 持续监控
echo "[5/6] 触发 BFF start + 60s 持续监控状态..."

# 通过 BFF API 启动 CDP
START_RESULT=$(curl -s -X POST http://127.0.0.1:8000/api/v2/realtime/jyhf-cdp/start \
  -H "Content-Type: application/json" -d '{}')
echo "  启动结果: $(echo $START_RESULT | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'ok={d[\"ok\"]} owner={d[\"service_owner\"]}')" 2>/dev/null || echo 'parse_error')"

# 监控 60 秒
echo ""
echo "时间     | BFF_cr | BFF_cdc | CDP_cr | CDP_cdc | JYHF_9223 | 前端_title"
echo "---------|--------|---------|--------|---------|-----------|-----------"

for i in $(seq 1 40); do
  TS=$(date +%H:%M:%S)

  # BFF 状态
  BFF=$(curl -s http://127.0.0.1:8000/api/v2/realtime/jyhf-cdp/status 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'{d.get(\"collector_running\",\"?\")}|{d.get(\"cdp_connected\",\"?\")}')
" 2>/dev/null || echo "DOWN|DOWN")

  # CDP 8095 直连
  CDP=$(curl -s http://127.0.0.1:8095/status 2>/dev/null | python3 -c "
import json,sys
d=json.load(sys.stdin)
print(f'{d.get(\"collector_running\",\"?\")}|{d.get(\"cdp_connected\",\"?\")}|{d.get(\"collector_state\",\"?\")}')
" 2>/dev/null || echo "DOWN|DOWN|DOWN")

  # 9223 JYHF
  JYHF=$(curl -s http://127.0.0.1:9223/json 2>/dev/null | python3 -c "
import json,sys
print(f'pages={len(json.load(sys.stdin))}')
" 2>/dev/null || echo "DOWN")

  # 前端 document.title
  TITLE=$(cdp_eval "document.title" 2>/dev/null | tr -d '"' | cut -c1-40)

  echo "$TS | $BFF | $CDP | $JYHF | ${TITLE:-?}"

  # 检测到 cdp_connected=true 就退出
  if echo "$BFF" | grep -q "True|True"; then
    echo ""
    echo ">>> cdp_connected=true 达成！"
    break
  fi

  sleep 3
done

echo ""
echo "[6/6] 最终前端状态 (CDP抓取) ..."
cdp_eval "(async () => {
    try {
        const r = await fetch('/api/v2/realtime/jyhf-cdp/status');
        const d = await r.json();
        return JSON.stringify({
            collector_running: d.collector_running,
            cdp_connected: d.cdp_connected,
            app_running: d.app_running,
            service_owner: d.service_owner,
            service_running: d.service_running,
            current_tab: d.current_tab,
            last_capture_at: d.last_capture_at,
            last_error: d.last_error,
            capture_count: d.capture_count_total
        });
    } catch(e) { return 'FETCH_ERROR: ' + e.message; }
})()" 2>/dev/null

echo ""
echo "========================================"
echo " 诊断完成"
echo "========================================"

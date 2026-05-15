#!/usr/bin/env bash
# 全自动诊断 v2：启动 Electron → 等待登录 → 导航到采集页 → CDP 点击启动按钮 → 监控 5 分钟
set -euo pipefail

PROJECT="/Users/admin/Desktop/ai_theme_app"
PYTHON="$PROJECT/.venv/bin/python"
CDP_PORT=9224

cleanup() {
  echo "[cleanup]"
  kill $ELECTRON_PID 2>/dev/null || true
  sleep 2
}
trap cleanup EXIT

# Kill all
kill $(lsof -t -i TCP:8000 -s TCP:LISTEN 2>/dev/null) 2>/dev/null || true
kill $(lsof -t -i TCP:8095 -s TCP:LISTEN 2>/dev/null) 2>/dev/null || true
kill $(lsof -t -i TCP:$CDP_PORT -s TCP:LISTEN 2>/dev/null) 2>/dev/null || true
sleep 2

echo "=========================================="
echo " 自动诊断 v2: 模拟用户完整操作流程"
echo "=========================================="

# Compile
cd "$PROJECT/desktop"
npx tsc -p tsconfig.json 2>&1 | tail -1

# Start Electron with CDP
npx electron dist-electron/main.js --remote-debugging-port=$CDP_PORT --remote-allow-origins=* &
ELECTRON_PID=$!
echo "[1] Electron PID=$ELECTRON_PID"

# Wait for web_app
for i in $(seq 1 30); do
  if curl -s http://127.0.0.1:8000/healthz >/dev/null 2>&1; then
    echo "[2] web_app 就绪 (${i}s)"
    break
  fi
  sleep 1
done

# Wait for CDP port
for i in $(seq 1 20); do
  if curl -s "http://127.0.0.1:$CDP_PORT/json" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

TARGETS=$(curl -s "http://127.0.0.1:$CDP_PORT/json")
WS_URL=$(echo "$TARGETS" | $PYTHON -c "
import json,sys
for p in json.load(sys.stdin):
    if p.get('type')=='page' and 'localhost' in p.get('url',''):
        print(p.get('webSocketDebuggerUrl',''))
        break
")
echo "[3] CDP 已连接"

# CDP eval helper
cdp_eval() {
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
ws.send(json.dumps({'id':2,'method':'Runtime.evaluate','params':{'expression':r'''$1''','returnByValue':True}}))
deadline=time.time()+10
while time.time()<deadline:
    try: msg=json.loads(ws.recv())
    except: continue
    if msg.get('id')==2:
        v=msg.get('result',{}).get('result',{}).get('value')
        print(json.dumps(v,ensure_ascii=False) if v is not None else 'null')
        break
ws.close()
" 2>/dev/null
}

# Navigate to realtime collector page
echo "[4] 导航到实时采集控制台..."
cdp_eval "window.location.href = '/realtime-collector'" > /dev/null 2>&1 || true
sleep 4

# Reconnect CDP after navigation (page URL changed)
TARGETS=$(curl -s "http://127.0.0.1:$CDP_PORT/json")
WS_URL=$(echo "$TARGETS" | $PYTHON -c "
import json,sys
for p in json.load(sys.stdin):
    if p.get('type')=='page' and 'localhost' in p.get('url',''):
        print(p.get('webSocketDebuggerUrl',''))
        break
")
echo "  WS: ${WS_URL:0:60}..."

LOC=$(cdp_eval "window.location.href")
echo "  当前页面: $LOC"

# Click the start button via CDP
echo "[5] 点击启动按钮..."
BTN=$(cdp_eval "
(function(){
    var btns = document.querySelectorAll('button');
    for(var i=0; i<btns.length; i++){
        if(btns[i].textContent.indexOf('启动 JYHF DOM')>=0 && !btns[i].disabled){
            btns[i].click();
            return 'clicked';
        }
    }
    for(var i=0; i<btns.length; i++){
        if(btns[i].textContent.indexOf('启动 JYHF')>=0){
            return 'found but disabled';
        }
    }
    return 'button not found';
})()
")
echo "  按钮: $BTN"

# Monitor for 2 minutes
echo ""
echo "[6] 监控 120 秒..."
echo "时间     | BFF_cr | BFF_cdc | CDP_cr | CDP_cdc | 9223_pg | 前端_collector | 前端_cdp"
echo "---------|--------|---------|--------|---------|---------|----------------|----------"

last_cr=""
for i in $(seq 1 40); do
  TS=$(date +%H:%M:%S)

  BFF=$(curl -s http://127.0.0.1:8000/api/v2/realtime/jyhf-cdp/status 2>/dev/null | $PYTHON -c "
import json,sys
d=json.load(sys.stdin)
print(f'{d.get(\"collector_running\",\"?\")}|{d.get(\"cdp_connected\",\"?\")}')
" 2>/dev/null || echo "DOWN|DOWN")

  CDP=$(curl -s http://127.0.0.1:8095/status 2>/dev/null | $PYTHON -c "
import json,sys
d=json.load(sys.stdin)
print(f'{d.get(\"collector_running\",\"?\")}|{d.get(\"cdp_connected\",\"?\")}')
" 2>/dev/null || echo "DOWN|DOWN")

  JYHF=$(curl -s http://127.0.0.1:9223/json 2>/dev/null | $PYTHON -c "
import json,sys
print(f'pages={len(json.load(sys.stdin))}')
" 2>/dev/null || echo "DOWN")

  # Get frontend displayed state from DOM
  FE=$(cdp_eval "
(function(){
    var strongs = document.querySelectorAll('.collection-debug-status strong');
    var result = [];
    for(var i=0; i<strongs.length; i++){
        result.push(strongs[i].textContent.trim());
    }
    return result.slice(0,4).join('|');
})()
" 2>/dev/null | tr -d '"')

  BFF_CR=$(echo $BFF | cut -d'|' -f1)

  if [ "$BFF_CR" != "$last_cr" ]; then
    echo "$TS | $BFF | $CDP | $JYHF | $FE"
    last_cr="$BFF_CR"
  fi

  if echo "$BFF" | grep -q "True|True"; then
    echo ""
    echo ">>> cdp_connected=true 达成！时间: $TS"
    break
  fi

  sleep 3
done

echo ""
echo "=========================================="
echo " 诊断完成"
echo "=========================================="

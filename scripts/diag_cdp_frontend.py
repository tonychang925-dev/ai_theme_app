#!/usr/bin/env python3
"""Connect to Electron renderer via CDP and dump frontend React state.
Usage: ELECTRON_CDP_PORT=9224 python scripts/diag_cdp_frontend.py
"""
import json
import os
import sys
import time
import urllib.request

CDP_PORT = int(os.getenv("ELECTRON_CDP_PORT", "9224"))


def cdp_get(path: str) -> dict:
    url = f"http://127.0.0.1:{CDP_PORT}{path}"
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


def cdp_eval(ws_url: str, expression: str) -> str:
    """Execute JS in the renderer via CDP WebSocket."""
    import websocket
    ws = websocket.create_connection(ws_url, timeout=10)
    ws.send(json.dumps({"id": 1, "method": "Runtime.enable"}))
    time.sleep(0.3)
    # Drain enable messages
    try:
        ws.settimeout(0.3)
        while True:
            ws.recv()
    except Exception:
        pass
    ws.settimeout(10)
    ws.send(json.dumps({
        "id": 2, "method": "Runtime.evaluate",
        "params": {"expression": expression, "returnByValue": True}
    }))
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            continue
        if msg.get("id") == 2:
            result = msg.get("result", {}).get("result", {})
            ws.close()
            return json.dumps(result.get("value"), ensure_ascii=False)
    ws.close()
    return "timeout"


def main():
    print(f"连接 Electron CDP :{CDP_PORT} ...")
    try:
        targets = cdp_get("/json")
    except Exception as e:
        print(f"无法连接 CDP 端口 {CDP_PORT}: {e}")
        print("请用: npm run start:debug 启动 Electron")
        sys.exit(1)

    renderer = None
    for t in targets:
        if t.get("type") == "page" and "localhost" in t.get("url", ""):
            renderer = t
            break
    if not renderer:
        # Fallback: any page
        for t in targets:
            if t.get("type") == "page":
                renderer = t
                break

    if not renderer:
        print(f"未找到 renderer 页面。可用 targets: {json.dumps(targets, indent=2)}")
        sys.exit(1)

    ws_url = renderer.get("webSocketDebuggerUrl", "")
    print(f"找到页面: {renderer.get('title')} url={renderer.get('url')}")

    # 1. Check if we're on the realtime collector page
    location = cdp_eval(ws_url, "JSON.stringify({href: location.href, port: location.port})")
    print(f"\n当前页面: {location}")

    # 2. Dump CDP status API response
    api_raw = cdp_eval(ws_url, """
    (async () => {
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
                last_error: d.last_error
            });
        } catch(e) { return 'FETCH ERROR: ' + e.message; }
    })()
    """)
    print(f"\nAPI /jyhf-cdp/status: {api_raw}")

    # 3. Check if the diagnostic useEffect is running
    title = cdp_eval(ws_url, "document.title")
    print(f"\ndocument.title: {title}")

    # 4. Check for JS errors (last 3)
    js_errors = cdp_eval(ws_url, "JSON.stringify((window.__cdp_errors || []).slice(-3))")
    print(f"\n最近 JS 错误: {js_errors}")

    # 5. Hook console.error to capture future errors
    cdp_eval(ws_url, """
    window.__cdp_errors = window.__cdp_errors || [];
    const origError = console.error;
    console.error = function(...args) {
        window.__cdp_errors.push(args.map(String).join(' '));
        origError.apply(console, args);
    };
    'hooked'
    """)

    print("\n诊断完成。重新运行此脚本查看最新状态。")


if __name__ == "__main__":
    main()

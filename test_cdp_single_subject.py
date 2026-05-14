#!/usr/bin/env python3
"""
测试 CDP 抓取单个题材的子题材个股入选理由。

用法:
  python test_cdp_single_subject.py 9035331
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import websocket

PROJECT_ROOT = Path(__file__).resolve().parent
CDP_PORT = 9223
JYHF_APP = "/Applications/久赢恒丰.app"


def launch_app():
    """启动久赢恒丰 App with CDP."""
    # Check if already running
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{CDP_PORT}/json"],
            capture_output=True, text=True, timeout=5,
        )
        pages = json.loads(result.stdout)
        for p in pages:
            if "久赢恒丰" in p.get("title", ""):
                print("[OK] JYHF app already running")
                return
    except Exception:
        pass

    print("[START] Launching JYHF app...")
    subprocess.Popen(
        [f"{JYHF_APP}/Contents/MacOS/久赢恒丰",
         f"--remote-debugging-port={CDP_PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        time.sleep(2)
        try:
            result = subprocess.run(
                ["curl", "-s", f"http://localhost:{CDP_PORT}/json"],
                capture_output=True, text=True, timeout=5,
            )
            pages = json.loads(result.stdout)
            for p in pages:
                if "久赢恒丰" in p.get("title", ""):
                    print("[OK] App started")
                    time.sleep(5)
                    return
        except Exception:
            continue
    raise RuntimeError("App failed to start")


def connect_cdp():
    """Connect to JYHF app via CDP."""
    result = subprocess.run(
        ["curl", "-s", f"http://localhost:{CDP_PORT}/json"],
        capture_output=True, text=True,
    )
    pages = json.loads(result.stdout)
    target = None
    for p in pages:
        if "久赢恒丰" in p.get("title", ""):
            target = p
            break
    if not target:
        raise RuntimeError("No JYHF page found")

    ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10)
    msg_id = [0]

    def send(method, params=None, mid=None):
        msg_id[0] += 1
        m = {"id": mid or msg_id[0], "method": method, "params": params or {}}
        ws.send(json.dumps(m))

    def recv_result(timeout=8):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = json.loads(ws.recv())
            except (websocket.WebSocketTimeoutException, json.JSONDecodeError):
                continue
            except Exception:
                break
            if "result" in msg and "value" in msg.get("result", {}).get("result", {}):
                return msg["result"]["result"]["value"]
            if "result" in msg and "result" in msg["result"]:
                pass  # keep waiting
            time.sleep(0.1)
        return None

    def evaluate(js, timeout=10):
        msg_id[0] += 1
        mid = msg_id[0]
        send("Runtime.evaluate", {"expression": js, "returnByValue": True}, mid)
        time.sleep(0.5)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = json.loads(ws.recv())
            except:
                continue
            if msg.get("id") == mid:
                r = msg.get("result", {}).get("result", {})
                if "value" in r:
                    return r["value"]
                return None
        return None

    def navigate(path):
        js = (f"document.querySelector('#app').__vue_app__"
              f".config.globalProperties.$router.push('{path}')")
        evaluate(js)
        time.sleep(4)

    # Enable Runtime
    send("Runtime.enable")
    time.sleep(0.5)
    # Drain initial messages
    ws.settimeout(0.3)
    for _ in range(10):
        try:
            ws.recv()
        except:
            break
    ws.settimeout(10)

    return navigate, evaluate, ws


def main():
    subject_id = sys.argv[1] if len(sys.argv) > 1 else "9035331"
    print(f"[TEST] Extracting child stock reasons for subject {subject_id}")

    # Step 1: Launch app
    launch_app()

    # Step 2: Connect CDP
    navigate, evaluate, ws = connect_cdp()
    print("[CDP] Connected")

    # Step 3: Navigate to subject detail
    print(f"[NAV] /subject/detail/{subject_id}")
    navigate(f"/subject/detail/{subject_id}")

    # Step 4: Dump raw page text (前 3000 字符)
    raw_text = evaluate("document.body.innerText", timeout=15)
    if raw_text:
        print(f"\n=== RAW DOM TEXT (first 5000 chars) ===")
        print(raw_text[:5000])
        print(f"\n... (total {len(raw_text)} chars)")

        # Save to file for analysis
        dump_path = PROJECT_ROOT / f"dom_dump_{subject_id}.txt"
        with open(dump_path, "w", encoding="utf-8") as f:
            f.write(raw_text)
        print(f"\n[SAVE] Full DOM text saved to {dump_path}")
    else:
        print("[ERROR] Could not read page text")

    # Step 5: Try to extract children + stocks with structured approach
    print(f"\n=== STRUCTURED EXTRACTION ===")
    js_extract = """
    (function() {
        var text = document.body.innerText;
        var results = {children: [], raw_preview: text.substring(0, 500)};

        // Find child sections with stock codes
        // Pattern: child_name followed by stocks with 6-digit codes
        var lines = text.split('\\n');
        var currentChild = null;
        var stockList = [];

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (!line || line.length > 60) continue;

            // Detect child section headers
            var childMatch = line.match(/^(.{2,6})(\\s*\\(\\d+只?\\))?$/);
            var isChildHeader = false;

            // Check if next lines contain stock codes (6 digits)
            var lookahead = '';
            for (var j = i+1; j < Math.min(i+5, lines.length); j++) {
                lookahead += lines[j] + '\\n';
            }
            var hasStockCodes = /\\d{6}/.test(lookahead);

            if (hasStockCodes && childMatch && line.length >= 2 && line.length <= 20) {
                // Save previous child
                if (currentChild && stockList.length > 0) {
                    results.children.push({
                        child_name: currentChild,
                        stocks: stockList.slice()
                    });
                }
                currentChild = line.replace(/\\(.*\\)/, '').trim();
                stockList = [];
                continue;
            }

            // Detect stock entries (containing 6-digit code)
            var codeMatch = line.match(/(\\d{6})/);
            if (currentChild && codeMatch) {
                var code = codeMatch[1];
                var name = line.substring(0, line.indexOf(code)).trim();
                var reason = line.substring(line.indexOf(code) + 6).trim();
                // Clean up name/reason
                if (!name || name.length > 20) name = line.substring(0, 20).trim();
                if (reason && reason.length > 80) reason = reason.substring(0, 80);
                stockList.push({
                    stock_id: code,
                    stock_name: name,
                    reason: reason || ''
                });
            }
        }

        // Last child
        if (currentChild && stockList.length > 0) {
            results.children.push({
                child_name: currentChild,
                stocks: stockList.slice()
            });
        }

        return JSON.stringify(results);
    })()
    """
    result = evaluate(js_extract, timeout=15)
    if result:
        parsed = json.loads(result) if isinstance(result, str) else result
        print(f"Raw preview: {parsed.get('raw_preview', '')[:200]}")
        children = parsed.get('children', [])
        print(f"Children found: {len(children)}")
        for child in children:
            print(f"\n  [{child['child_name']}] {len(child['stocks'])} stocks:")
            for s in child['stocks']:
                print(f"    {s['stock_id']} {s['stock_name']}: {s['reason'][:100]}")

    ws.close()
    print("\n[DONE]")


if __name__ == "__main__":
    main()

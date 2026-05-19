#!/usr/bin/env python3
"""
CDP 诊断脚本：探测久赢恒丰 app 中 token 的存储位置。

连接 CDP 后遍历所有常见 JS 存储位置（localStorage, sessionStorage,
Vuex/Pinia store, cookies, window globals），输出找到的 token 信息。

用法:
  python cdp_extract_token_diag.py
  python cdp_extract_token_diag.py --port 9223 --save  # 提取并保存到 /tmp/jyhf_auth_token.json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import websocket

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

CDP_PORT = 9223
AUTH_FILE = Path("/tmp/jyhf_auth_token.json")


# ── Minimal CDP client (standalone, no dependency on jyhf_cdp_service) ──

class CDPClient:
    def __init__(self, port: int = CDP_PORT) -> None:
        self._port = port
        self._ws: websocket.WebSocket | None = None
        self._msg_id = 0

    def connect(self) -> None:
        import subprocess as sp
        result = sp.run(
            ["curl", "-s", f"http://localhost:{self._port}/json"],
            capture_output=True, text=True, timeout=5,
        )
        pages = json.loads(result.stdout or "[]")
        target = next((p for p in pages if "久赢恒丰" in str(p.get("title", ""))), None)
        if not target:
            raise RuntimeError(
                f"JYHF app not found on CDP port {self._port}. "
                f"Start it with: open -a 久赢恒丰 --args --remote-debugging-port={self._port}"
            )
        self._ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10)
        self._send("Runtime.enable")
        time.sleep(0.3)
        self._recv_all(0.5)
        print(f"[CDP] Connected to: {target.get('title', '?')}")

    def close(self) -> None:
        if self._ws:
            self._ws.close()
            self._ws = None

    def evaluate(self, expression: str, timeout: float = 10.0) -> str | None:
        if not self._ws:
            raise RuntimeError("Not connected")
        self._msg_id += 1
        mid = self._msg_id
        self._send("Runtime.evaluate", {"expression": expression, "returnByValue": True}, mid)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = json.loads(self._ws.recv())
            except (websocket.WebSocketTimeoutException, json.JSONDecodeError):
                continue
            if msg.get("id") != mid:
                continue
            result = msg.get("result", {}).get("result", {})
            if "value" in result:
                return str(result["value"])
            if result.get("type") == "undefined":
                return None
            if "exception" in msg.get("result", {}):
                err = msg["result"]["exception"].get("description", "?")
                print(f"  [JS ERROR] {err[:300]}")
                return None
            return None
        raise TimeoutError(f"evaluate timed out after {timeout}s")

    def _send(self, method: str, params: dict | None = None, mid: int | None = None) -> None:
        if not self._ws:
            return
        self._ws.send(json.dumps({"id": mid or 0, "method": method, "params": params or {}}))

    def _recv_all(self, timeout: float = 0.5) -> None:
        if not self._ws:
            return
        self._ws.settimeout(0.3)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                self._ws.recv()
            except Exception:
                break


# ── Diagnostic probes ────────────────────────────────────────

TOKEN_KEYWORDS = [
    "token", "Token", "TOKEN", "accessToken", "access_token",
    "auth", "Auth", "AUTH", "authorization", "Authorization",
    "bearer", "Bearer", "jwt", "JWT", "session", "Session",
]


def _contains_token_like(key: str, value: str) -> bool:
    """Check if a key/value pair looks like it contains a token."""
    key_lower = key.lower()
    for kw in TOKEN_KEYWORDS:
        if kw.lower() in key_lower:
            return True
    # Heuristic: long base64-looking string values
    if isinstance(value, str) and len(value) > 80 and re.match(r'^[A-Za-z0-9+/=_-]+$', value):
        return True
    return False


def probe_storages(cdp: CDPClient):
    """Probe all storage locations and print findings."""

    # Common JS expressions to probe
    probes: list[tuple[str, str, str]] = [
        # (label, js_expression, type)
        ("localStorage (all keys)", """
(function() {
    var result = {};
    try {
        for (var i = 0; i < localStorage.length; i++) {
            var key = localStorage.key(i);
            var val = localStorage.getItem(key);
            result[key] = val;
        }
    } catch(e) { result['__error__'] = e.message; }
    return JSON.stringify(result);
})()
""", "json"),

        ("sessionStorage (all keys)", """
(function() {
    var result = {};
    try {
        for (var i = 0; i < sessionStorage.length; i++) {
            var key = sessionStorage.key(i);
            var val = sessionStorage.getItem(key);
            result[key] = val;
        }
    } catch(e) { result['__error__'] = e.message; }
    return JSON.stringify(result);
})()
""", "json"),

        ("document.cookie", "document.cookie", "text"),

        # Vuex store state
        ("Vuex $store.state", """
(function() {
    try {
        var app = document.querySelector('#app');
        if (!app || !app.__vue_app__) return JSON.stringify({error: 'no vue app'});
        var store = app.__vue_app__.config.globalProperties.$store;
        if (!store) return JSON.stringify({error: 'no $store'});
        if (store.state) return JSON.stringify(store.state);
        return JSON.stringify({store_keys: Object.keys(store)});
    } catch(e) { return JSON.stringify({error: e.message}); }
})()
""", "json"),

        # Pinia stores
        ("Pinia stores", """
(function() {
    try {
        var app = document.querySelector('#app');
        if (!app || !app.__vue_app__) return JSON.stringify({error: 'no vue app'});
        var pinia = app.__vue_app__.config.globalProperties.$pinia;
        if (!pinia) return JSON.stringify({error: 'no $pinia'});
        var ids = pinia._s ? Object.keys(pinia._s) : [];
        var states = {};
        if (pinia._s) {
            for (var id in pinia._s) {
                states[id] = pinia._s[id].$state;
            }
        }
        return JSON.stringify({store_ids: ids, states: states});
    } catch(e) { return JSON.stringify({error: e.message}); }
})()
""", "json"),

        # window globals matching token patterns
        ("window globals (token-like names)", """
(function() {
    var results = {};
    var keywords = ['token','Token','TOKEN','accessToken','auth','Auth','AUTH',
                    'authorization','Authorization','bearer','Bearer','session','Session',
                    'jwt','JWT','user','User','login','Login'];
    for (var key in window) {
        try {
            var low = key.toLowerCase();
            var hit = false;
            for (var k = 0; k < keywords.length; k++) {
                if (low.indexOf(keywords[k].toLowerCase()) >= 0) { hit = true; break; }
            }
            if (!hit) continue;
            var val = window[key];
            if (typeof val === 'function' || typeof val === 'object') continue;
            results[key] = String(val).substring(0, 200);
        } catch(e) {}
    }
    return JSON.stringify(results);
})()
""", "json"),
    ]

    findings: list[dict] = []

    for label, js, typ in probes:
        print(f"\n{'='*60}")
        print(f"  Probing: {label}")
        print(f"{'='*60}")
        raw = cdp.evaluate(js)
        if raw is None:
            print(f"  → (undefined / null)")
            continue

        if typ == "json":
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"  → [RAW] {raw[:500]}")
                continue

            if not data:
                print(f"  → (empty)")
                continue

            # Highlight token-like entries
            found_any = False
            for key, val in data.items():
                val_str = str(val) if not isinstance(val, str) else val
                is_token = _contains_token_like(key, val_str)
                marker = " ★ TOKEN-LIKE" if is_token else ""
                truncated = val_str[:300] + ("..." if len(val_str) > 300 else "")
                print(f"  [{key}] = {truncated}{marker}")
                if is_token:
                    found_any = True
                    findings.append({"source": label, "key": key, "value": val_str})
            if not found_any:
                print(f"  → ({len(data)} keys, none look like tokens)")

        else:
            printed = raw[:500] + ("..." if len(raw) > 500 else "")
            print(f"  = {printed}")
            if _contains_token_like("cookie", raw):
                findings.append({"source": label, "key": "cookie", "value": raw})

    return findings


def probe_network_hook(cdp: CDPClient) -> dict | None:
    """Attempt to hook fetch/XMLHttpRequest to capture the Authorization header.

    This is a fallback: we inject a hook, trigger a page refresh/navigation,
    then read back any captured headers.
    """
    print(f"\n{'='*60}")
    print(f"  Probing: Network hook (fetch + XHR interceptor)")
    print(f"{'='*60}")

    js = """
(function() {
    // If we already have the hook, return captured tokens
    if (window.__cdp_token_hook__) {
        return JSON.stringify(window.__cdp_token_hook__);
    }

    window.__cdp_token_hook__ = {tokens: [], requests: []};

    // Hook fetch
    var origFetch = window.fetch;
    window.fetch = function() {
        var args = arguments;
        var headers = args[1] && args[1].headers ? args[1].headers : {};
        var auth = '';
        if (headers instanceof Headers) {
            auth = headers.get('Authorization') || headers.get('authorization') || '';
        } else if (typeof headers === 'object') {
            auth = headers['Authorization'] || headers['authorization'] || '';
        }
        if (auth && window.__cdp_token_hook__.tokens.indexOf(auth) < 0) {
            window.__cdp_token_hook__.tokens.push(auth);
        }
        var url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url ? args[0].url : '');
        window.__cdp_token_hook__.requests.push({url: url, hasAuth: !!auth});
        return origFetch.apply(this, args);
    };

    // Hook XMLHttpRequest.setRequestHeader
    var origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
    XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
        if (header.toLowerCase() === 'authorization' && value) {
            if (window.__cdp_token_hook__.tokens.indexOf(value) < 0) {
                window.__cdp_token_hook__.tokens.push(value);
            }
        }
        return origSetHeader.call(this, header, value);
    };

    return JSON.stringify({status: 'hooks_injected', note: 'navigate or wait for API call'});
})()
"""
    raw = cdp.evaluate(js)
    if raw:
        try:
            result = json.loads(raw)
            print(f"  Inject result: {json.dumps(result, indent=2)}")
        except json.JSONDecodeError:
            print(f"  Raw: {raw[:300]}")

    # Trigger a navigation to home to generate API calls
    print(f"  Triggering navigation to / to generate API requests...")
    cdp.evaluate("""
    (function() {
        try {
            var app = document.querySelector('#app');
            if (app && app.__vue_app__) {
                app.__vue_app__.config.globalProperties.$router.push('/');
            }
        } catch(e) {}
    })()
    """)
    time.sleep(3)

    # Read captured tokens
    raw2 = cdp.evaluate("JSON.stringify(window.__cdp_token_hook__ || {})")
    if raw2:
        try:
            captured = json.loads(raw2)
            tokens = captured.get("tokens", [])
            requests = captured.get("requests", [])
            print(f"  Captured {len(tokens)} token(s) from {len(requests)} requests")
            for t in tokens:
                print(f"  Token: {t[:60]}... (len={len(t)})")
            if tokens:
                return {"source": "network_hook", "key": "Authorization", "value": tokens[0]}
        except json.JSONDecodeError:
            pass
    return None


def probe_vue_router_guards(cdp: CDPClient) -> dict | None:
    """Try to read token from Vue app's axios instance or HTTP client config."""
    print(f"\n{'='*60}")
    print(f"  Probing: Vue app HTTP client / axios defaults")
    print(f"{'='*60}")

    js = """
(function() {
    var results = {};
    try {
        var app = document.querySelector('#app');
        if (!app || !app.__vue_app__) return JSON.stringify({error: 'no vue app'});

        var vm = app.__vue_app__;

        // Try to find axios instance via global properties
        var gp = vm.config.globalProperties;
        var gpKeys = Object.keys(gp).filter(function(k) {
            return typeof gp[k] !== 'function';
        });
        results.globalProperties = gpKeys;

        // Check for $http, $axios, $api
        for (var name of ['$http', '$axios', '$api', '$request', 'axios', 'http']) {
            try {
                var obj = gp[name];
                if (!obj) {
                    results[name] = null;
                    continue;
                }
                if (obj.defaults) {
                    results[name + '_defaults'] = {
                        baseURL: obj.defaults.baseURL,
                        headers: obj.defaults.headers
                    };
                }
                if (obj.interceptors) {
                    results[name + '_hasInterceptors'] = true;
                }
            } catch(e) {
                results[name + '_error'] = e.message;
            }
        }

        return JSON.stringify(results);
    } catch(e) { return JSON.stringify({error: e.message}); }
})()
"""
    raw = cdp.evaluate(js)
    if raw:
        try:
            data = json.loads(raw)
            print(f"  {json.dumps(data, indent=2, ensure_ascii=False)}")
        except json.JSONDecodeError:
            print(f"  {raw[:500]}")
    return None


def save_token(token: str, source: str) -> None:
    """Write token to the standard auth file location."""
    data = {
        "token": token,
        "timestamp": time.time(),
        "source": source,
        "method": "cdp_dom",
    }
    AUTH_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUTH_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    print(f"\n[SAVE] Token written to {AUTH_FILE}")


def main():
    parser = argparse.ArgumentParser(description="CDP diagnostic: find JYHF auth token")
    parser.add_argument("--port", type=int, default=CDP_PORT, help=f"CDP port (default: {CDP_PORT})")
    parser.add_argument("--save", action="store_true", help="Save first found token to auth file")
    parser.add_argument("--hook-only", action="store_true", help="Only run network hook (fastest)")
    args = parser.parse_args()

    cdp = CDPClient(port=args.port)

    try:
        cdp.connect()

        all_findings: list[dict] = []

        if args.hook_only:
            finding = probe_network_hook(cdp)
            if finding:
                all_findings.append(finding)
        else:
            # Phase 1: Static storage probes
            findings = probe_storages(cdp)
            all_findings.extend(findings)

            # Phase 2: Vue internals
            probe_vue_router_guards(cdp)

            # Phase 3: Network hook (most reliable fallback)
            finding = probe_network_hook(cdp)
            if finding:
                all_findings.append(finding)

        # Summary
        print(f"\n{'='*60}")
        print(f"  SUMMARY: Found {len(all_findings)} token-like value(s)")
        print(f"{'='*60}")

        if all_findings:
            for i, f in enumerate(all_findings):
                val = f["value"]
                print(f"  [{i+1}] source={f['source']}  key={f['key']}")
                print(f"      value={val[:80]}{'...' if len(val) > 80 else ''}  (len={len(val)})")
                print(f"      preview: {val[:40]}...{val[-20:] if len(val) > 60 else ''}")

            if args.save:
                best = all_findings[0]
                save_token(best["value"], best["source"])
        else:
            print("  No token found. Possible reasons:")
            print("  1. App is not logged in (需要先登录)")
            print("  2. Token is stored in a non-standard location")
            print("  3. Token hasn't been issued yet (navigate to trigger API call)")
            print("  Try: --hook-only mode and navigate in the app to trigger requests")

    finally:
        cdp.close()

    if all_findings and not args.save:
        print(f"\n[HINT] Run with --save to persist the first token to {AUTH_FILE}")


if __name__ == "__main__":
    main()

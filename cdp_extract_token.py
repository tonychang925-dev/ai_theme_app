#!/usr/bin/env python3
"""
CDP-based JYHF auth token extractor.

通过 CDP 从久赢恒丰 Electron 应用的 JS 运行时中直接提取 Authorization token，
替代 mitmweb 代理方案。无需启动额外代理进程。

提取策略（按优先级）:
  1. localStorage 中匹配 token/auth 关键字的 key
  2. sessionStorage 中匹配的 key
  3. Vue $auth plugin 属性
  4. Vuex/Pinia store state 中的 token 字段
  5. 网络拦截（猴子补丁 fetch/XHR 捕获 Authorization 头）— 主要手段

用法:
  # 作为独立脚本
  python cdp_extract_token.py

  # 作为模块导入
  from cdp_extract_token import extract_token, ensure_token

  # 命令行参数
  python cdp_extract_token.py --port 9223 --output /tmp/jyhf_auth_token.json
  python cdp_extract_token.py --wait 30  # 等待最多30秒直到获取到token
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import websocket

# ── Constants ─────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_CDP_PORT = 9223
DEFAULT_AUTH_FILE = Path("/tmp/jyhf_auth_token.json")
JYHF_APP_PATH = "/Applications/久赢恒丰.app"

# localStorage / sessionStorage keys likely to hold the auth token
TOKEN_KEY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^token$", r"^accessToken$", r"^access_token$", r"^auth$",
        r"^authorization$", r"^authToken$", r"^auth_token$",
        r"^bearer$", r"^jwt$", r"^session$", r"^sessionToken$",
        r"credentials", r"loginToken", r"userToken",
        r"^idToken$", r"^id_token$",
    ]
]

# ── CDP Client (standalone, no dependency on jyhf_cdp_service) ──

class TokenCDPClient:
    """Minimal CDP client for token extraction."""

    def __init__(self, port: int = DEFAULT_CDP_PORT) -> None:
        self._port = port
        self._ws: Optional[websocket.WebSocket] = None
        self._msg_id = 0

    def connect(self) -> bool:
        """Connect to JYHF app's CDP endpoint. Returns True on success."""
        try:
            result = subprocess.run(
                ["curl", "-s", f"http://localhost:{self._port}/json"],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            return False

        try:
            pages = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            return False

        target = next((p for p in pages if "久赢恒丰" in str(p.get("title", ""))), None)
        if not target:
            return False

        self._ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10)
        self._send("Runtime.enable")
        time.sleep(0.3)
        self._recv_all(0.5)
        return True

    def close(self) -> None:
        if self._ws:
            self._ws.close()
            self._ws = None

    def evaluate(self, expression: str, timeout: float = 8.0) -> Any:
        """Evaluate JS in the renderer and return the parsed result."""
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
            except Exception:
                break
            if msg.get("id") != mid:
                continue
            result = msg.get("result", {}).get("result", {})
            if "value" in result:
                return result["value"]
            if result.get("type") == "undefined":
                return None
            exc = msg.get("result", {}).get("exceptionDetails", {})
            if exc:
                return None
            return None
        return None

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


# ── App lifecycle ─────────────────────────────────────────────

def is_app_running(port: int = DEFAULT_CDP_PORT) -> bool:
    """Check if JYHF app is running with CDP enabled."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{port}/json"],
            capture_output=True, text=True, timeout=5,
        )
        pages = json.loads(result.stdout or "[]")
        return any("久赢恒丰" in str(p.get("title", "")) for p in pages)
    except Exception:
        return False


def ensure_app_running(port: int = DEFAULT_CDP_PORT) -> bool:
    """Ensure JYHF app is running with CDP. Launch if needed. Returns True if ready."""
    if is_app_running(port):
        return True

    print(f"[START] Launching JYHF app with CDP on port {port}...")
    subprocess.Popen(
        [f"{JYHF_APP_PATH}/Contents/MacOS/久赢恒丰", f"--remote-debugging-port={port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )

    for _ in range(20):
        time.sleep(2)
        if is_app_running(port):
            time.sleep(2)  # Settle
            print("[OK] JYHF app started with CDP")
            return True
    return False


# ── Token extraction strategies ───────────────────────────────

def _extract_from_storage(cdp: TokenCDPClient) -> Optional[str]:
    """Strategy 1: Scan localStorage for token-like keys."""
    raw = cdp.evaluate("""
    (function() {
        var results = {};
        try {
            for (var i = 0; i < localStorage.length; i++) {
                var key = localStorage.key(i);
                results[key] = localStorage.getItem(key);
            }
        } catch(e) {}
        return JSON.stringify(results);
    })()
    """)
    if not raw:
        return None
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    if not isinstance(items, dict):
        return None
    return _match_token_in_dict(items, "localStorage")


def _extract_from_session_storage(cdp: TokenCDPClient) -> Optional[str]:
    """Strategy 2: Scan sessionStorage for token-like keys."""
    raw = cdp.evaluate("""
    (function() {
        var results = {};
        try {
            for (var i = 0; i < sessionStorage.length; i++) {
                var key = sessionStorage.key(i);
                results[key] = sessionStorage.getItem(key);
            }
        } catch(e) {}
        return JSON.stringify(results);
    })()
    """)
    if not raw:
        return None
    try:
        items = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    if not isinstance(items, dict):
        return None
    return _match_token_in_dict(items, "sessionStorage")


def _extract_from_vuex(cdp: TokenCDPClient) -> Optional[str]:
    """Strategy 3: Walk Vuex/Pinia store state for token fields."""
    raw = cdp.evaluate("""
    (function() {
        var results = {};
        try {
            var app = document.querySelector('#app');
            if (app && app.__vue_app__) {

                // Vuex
                var store = app.__vue_app__.config.globalProperties.$store;
                if (store && store.state) {
                    results.vuex = store.state;
                }

                // Pinia
                var pinia = app.__vue_app__.config.globalProperties.$pinia;
                if (pinia && pinia._s) {
                    var states = {};
                    for (var id in pinia._s) {
                        states[id] = pinia._s[id].$state;
                    }
                    results.pinia = states;
                }

                // Other globalProperties that might hold config
                var gp = app.__vue_app__.config.globalProperties;
                for (var name of ['$http','$axios','$api','$request','$config']) {
                    try {
                        var obj = gp[name];
                        if (obj && obj.defaults && obj.defaults.headers) {
                            results[name + '_defaults'] = obj.defaults.headers;
                        }
                    } catch(e) {}
                }
            }
        } catch(e) { results.error = e.message; }
        return JSON.stringify(results);
    })()
    """)
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    # Recursively search for token-like values
    return _search_token_in_obj(data, "vuex/pinia")


def _extract_from_network_hook(cdp: TokenCDPClient) -> Optional[str]:
    """Strategy 4 (fallback): Hook fetch/XHR to capture Authorization header."""
    # Inject hooks
    cdp.evaluate("""
    (function() {
        if (window.__cdp_token_hook_active__) return;
        window.__cdp_token_hook_active__ = true;
        window.__cdp_captured_tokens__ = [];

        var origFetch = window.fetch;
        window.fetch = function() {
            var headers = arguments[1] && arguments[1].headers;
            if (headers) {
                var auth = '';
                if (typeof headers.get === 'function') {
                    auth = headers.get('Authorization') || headers.get('authorization') || '';
                } else {
                    auth = headers['Authorization'] || headers['authorization'] || '';
                }
                if (auth && window.__cdp_captured_tokens__.indexOf(auth) < 0) {
                    window.__cdp_captured_tokens__.push(auth);
                }
            }
            return origFetch.apply(this, arguments);
        };

        var origSetHeader = XMLHttpRequest.prototype.setRequestHeader;
        XMLHttpRequest.prototype.setRequestHeader = function(header, value) {
            if (header.toLowerCase() === 'authorization' && value) {
                if (window.__cdp_captured_tokens__.indexOf(value) < 0) {
                    window.__cdp_captured_tokens__.push(value);
                }
            }
            return origSetHeader.call(this, header, value);
        };
    })()
    """)

    # Trigger navigation to generate API requests
    cdp.evaluate("""
    (function() {
        try {
            var app = document.querySelector('#app');
            if (app && app.__vue_app__) {
                app.__vue_app__.config.globalProperties.$router.push('/');
            } else {
                window.location.hash = '#/';
            }
        } catch(e) {}
    })()
    """)
    time.sleep(3)

    # Read captured tokens
    raw = cdp.evaluate("JSON.stringify(window.__cdp_captured_tokens__ || [])")
    if raw:
        try:
            tokens = json.loads(raw) if isinstance(raw, str) else raw
            if tokens and isinstance(tokens, list) and len(tokens) > 0:
                return str(tokens[0])
        except json.JSONDecodeError:
            pass
    return None


# ── Token matching helpers ───────────────────────────────────

def _match_token_in_dict(items: dict, source: str) -> Optional[str]:
    """Find a token-like value in a dict of key->value pairs."""
    # First pass: match by key name
    for key, val in items.items():
        if not isinstance(val, str) or not val:
            continue
        for pattern in TOKEN_KEY_PATTERNS:
            if pattern.search(key):
                print(f"[FOUND] {source}: {key} = {val[:40]}... (len={len(val)})")
                return val
    # Second pass: match by value pattern (long alphanumeric/base64 string)
    for key, val in items.items():
        if not isinstance(val, str) or len(val) < 40:
            continue
        # Bearer token pattern
        if val.startswith("Bearer ") or val.startswith("bearer "):
            print(f"[FOUND] {source}: {key} (Bearer token, len={len(val)})")
            return val
        # JWT pattern (3 dot-separated base64url segments)
        if val.count(".") == 2 and re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$', val):
            print(f"[FOUND] {source}: {key} (JWT, len={len(val)})")
            return val
        # Long hex or base64 token
        if len(val) >= 80 and re.match(r'^[A-Za-z0-9+/=_-]{80,}$', val):
            print(f"[FOUND] {source}: {key} (long token, len={len(val)})")
            return val
    return None


def _search_token_in_obj(obj: Any, path: str = "", depth: int = 0) -> Optional[str]:
    """Recursively search an object/dict for token-like values."""
    if depth > 5:
        return None
    if isinstance(obj, dict):
        # Check keys first
        result = _match_token_in_dict(obj, path)
        if result:
            return result
        # Recurse into nested objects
        for key, val in obj.items():
            result = _search_token_in_obj(val, f"{path}.{key}", depth + 1)
            if result:
                return result
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            result = _search_token_in_obj(val, f"{path}[{i}]", depth + 1)
            if result:
                return result
    return None


# ── Main extraction logic ────────────────────────────────────

def extract_token(
    port: int = DEFAULT_CDP_PORT,
    *,
    ensure_app: bool = False,
    use_network_hook: bool = True,
) -> Optional[str]:
    """Extract JYHF auth token via CDP.

    Args:
        port: CDP debug port
        ensure_app: If True, launch JYHF app if not running
        use_network_hook: If True, fall back to fetch/XHR interception

    Returns:
        The token string, or None if extraction failed.
    """
    if not is_app_running(port):
        if ensure_app:
            if not ensure_app_running(port):
                print("[ERROR] Could not start JYHF app", file=sys.stderr)
                return None
        else:
            print(
                f"[ERROR] JYHF app not running on CDP port {port}. "
                f"Start with: open -a 久赢恒丰 --args --remote-debugging-port={port}",
                file=sys.stderr,
            )
            return None

    cdp = TokenCDPClient(port=port)
    try:
        if not cdp.connect():
            print("[ERROR] Could not connect CDP to JYHF app", file=sys.stderr)
            return None

        # Strategy 1: localStorage
        token = _extract_from_storage(cdp)
        if token:
            return token

        # Strategy 2: sessionStorage
        token = _extract_from_session_storage(cdp)
        if token:
            return token

        # Strategy 3: Vuex/Pinia
        token = _extract_from_vuex(cdp)
        if token:
            return token

        # Strategy 4: Network hook (fallback)
        if use_network_hook:
            token = _extract_from_network_hook(cdp)
            if token:
                return token

        return None
    finally:
        cdp.close()


def save_token(token: str, output_path: Path = DEFAULT_AUTH_FILE) -> None:
    """Write token to the standard auth file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "token": token,
        "timestamp": time.time(),
        "datetime": datetime.now().isoformat(),
        "method": "cdp_dom",
    }
    output_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def ensure_token(
    port: int = DEFAULT_CDP_PORT,
    output_path: Path = DEFAULT_AUTH_FILE,
    *,
    ensure_app: bool = False,
    wait_seconds: int = 0,
) -> Optional[str]:
    """Extract and save the JYHF auth token.

    Args:
        port: CDP debug port
        output_path: Where to save the token JSON
        ensure_app: Launch app if not running
        wait_seconds: If > 0, retry for up to this many seconds

    Returns:
        The token string, or None.
    """
    deadline = time.time() + wait_seconds if wait_seconds > 0 else 0

    while True:
        token = extract_token(port=port, ensure_app=ensure_app)
        if token:
            save_token(token, output_path)
            print(f"[OK] Token saved to {output_path}")
            return token

        if deadline and time.time() < deadline:
            print(f"[WAIT] Token not ready, retrying in 3s...")
            time.sleep(3)
        else:
            break

    return None


# ── CLI ───────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="CDP-based JYHF auth token extractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cdp_extract_token.py                    # One-shot extraction from running app
  python cdp_extract_token.py --ensure-app       # Auto-launch app if needed
  python cdp_extract_token.py --wait 60          # Wait up to 60s for token (useful at boot)
  python cdp_extract_token.py --output /tmp/my_token.json
  python cdp_extract_token.py --no-hook          # Skip network hook fallback
        """.strip(),
    )
    parser.add_argument("--port", type=int, default=DEFAULT_CDP_PORT)
    parser.add_argument("--output", type=Path, default=DEFAULT_AUTH_FILE)
    parser.add_argument("--ensure-app", action="store_true", help="Launch JYHF app if not running")
    parser.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                        help="Retry for up to N seconds until token is found")
    parser.add_argument("--no-hook", action="store_true", help="Skip network hook fallback")
    args = parser.parse_args()

    token = ensure_token(
        port=args.port,
        output_path=args.output,
        ensure_app=args.ensure_app,
        wait_seconds=args.wait,
    )
    if not args.no_hook:
        # ensure_token uses network hook by default
        pass

    if token:
        print(f"TOKEN: {token[:40]}...{token[-20:] if len(token) > 60 else ''}")
        sys.exit(0)
    else:
        print("[FAIL] Could not extract token", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

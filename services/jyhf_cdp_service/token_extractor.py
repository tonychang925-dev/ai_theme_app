"""
CDP-based JYHF auth token extraction.

从久赢恒丰 Electron 应用的 JS 运行时中提取 Authorization token。
诊断结论（2026-05-19）：token 是 JWT 类型，不在 localStorage/sessionStorage/
Vuex/Pinia/cookie 中，仅存于 JS 内存，通过 HTTP 拦截可捕获。

提取策略（按优先级）:
  1. 网络拦截（fetch/XHR hooks + 导航触发 API 请求）— 主要手段
  2. localStorage / sessionStorage 扫描 — 快速探路（以备后续版本变更）
  3. Vue globalProperties.$auth 探测
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.jyhf_cdp_service.cdp_client import CDPClient

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_PATH = Path("/tmp/jyhf_auth_token.json")

# localStorage / sessionStorage keys likely to hold the auth token
_TOKEN_KEY_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"^token$", r"^accessToken$", r"^access_token$", r"^auth$",
        r"^authorization$", r"^authToken$", r"^auth_token$",
        r"^bearer$", r"^jwt$", r"^session$", r"^sessionToken$",
        r"credentials", r"loginToken", r"userToken",
        r"^idToken$", r"^id_token$",
    ]
]


class TokenExtractor:
    """Extract JYHF auth token from the app's JS runtime via CDP."""

    def __init__(self, token_path: Path = DEFAULT_TOKEN_PATH) -> None:
        self._token_path = token_path
        self._last_extracted: str | None = None
        self._last_extract_time: float = 0.0
        self._hooks_injected: bool = False

    @property
    def last_token(self) -> str | None:
        return self._last_extracted

    @property
    def last_extract_time(self) -> float:
        return self._last_extract_time

    # ── public API ──────────────────────────────────────────────

    def extract(self, cdp: CDPClient, *, use_network_hook: bool = True) -> str | None:
        """Run extraction strategies. If use_network_hook=True, injects hooks
        and triggers a navigation to capture the token from HTTP requests."""

        # Fast path: check static storage first (no page changes)
        token = self._from_storage(cdp, "localStorage")
        if token:
            self._persist(token, "localStorage")
            return token

        token = self._from_storage(cdp, "sessionStorage")
        if token:
            self._persist(token, "sessionStorage")
            return token

        # Try $auth global property (Vue plugin)
        token = self._from_auth_plugin(cdp)
        if token:
            self._persist(token, "$auth")
            return token

        # Try Vuex/Pinia
        token = self._from_vue_stores(cdp)
        if token:
            self._persist(token, "vuex/pinia")
            return token

        # Main strategy: network hook (injects fetch/XHR interceptors,
        # triggers navigation to generate API calls, reads captured headers)
        if use_network_hook:
            token = self._from_network_hook(cdp)
            if token:
                self._persist(token, "network_hook")
                return token

        return None

    def inject_hooks(self, cdp: CDPClient) -> None:
        """Inject fetch/XHR hooks without triggering navigation.

        Call this BEFORE navigation (e.g., before extractor.prepare())
        so that the normal page navigations during event capture also
        trigger token capture.
        """
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
        self._hooks_injected = True

    def read_captured_tokens(self, cdp: CDPClient) -> str | None:
        """Read any tokens captured by injected hooks since last inject_hooks().

        Call this AFTER navigation/API calls have happened (e.g., after
        extractor.read() completes).
        """
        raw = cdp.evaluate("JSON.stringify(window.__cdp_captured_tokens__ || [])")
        if not raw:
            return None
        tokens = self._safe_json(raw)
        if isinstance(tokens, list) and tokens:
            token = str(tokens[0])
            self._persist(token, "network_hook")
            return token
        return None

    # ── strategy implementations ──────────────────────────────

    def _from_storage(self, cdp: CDPClient, storage_name: str) -> str | None:
        raw = cdp.evaluate(f"""
        (function() {{
            var results = {{}};
            try {{
                for (var i = 0; i < {storage_name}.length; i++) {{
                    var key = {storage_name}.key(i);
                    results[key] = {storage_name}.getItem(key);
                }}
            }} catch(e) {{}}
            return JSON.stringify(results);
        }})()
        """)
        if not raw:
            return None
        items = self._safe_json(raw)
        if not isinstance(items, dict):
            return None
        return self._match_in_dict(items, storage_name)

    def _from_auth_plugin(self, cdp: CDPClient) -> str | None:
        """Probe $auth global property (Vue plugin for authentication)."""
        raw = cdp.evaluate("""
        (function() {
            var results = {};
            try {
                var app = document.querySelector('#app');
                if (!app || !app.__vue_app__) return JSON.stringify({error: 'no_app'});
                var auth = app.__vue_app__.config.globalProperties.$auth;
                if (!auth) return JSON.stringify({error: 'no_$auth'});
                // Try common auth plugin patterns
                if (auth.token) results.token = auth.token;
                if (auth.accessToken) results.accessToken = auth.accessToken;
                if (auth.access_token) results.access_token = auth.access_token;
                if (auth.getToken && typeof auth.getToken === 'function') {
                    try { results.getToken_result = auth.getToken(); } catch(e) {}
                }
                if (auth.$state) results.$state = auth.$state;
                // Dump all own properties (non-function)
                var keys = Object.keys(auth);
                for (var i = 0; i < keys.length; i++) {
                    var k = keys[i];
                    var v = auth[k];
                    if (typeof v !== 'function') {
                        results['_prop_' + k] = typeof v === 'object' ? JSON.stringify(v) : String(v);
                    }
                }
            } catch(e) { results.error = e.message; }
            return JSON.stringify(results);
        })()
        """)
        if not raw:
            return None
        data = self._safe_json(raw)
        if not isinstance(data, dict):
            return None
        return self._match_in_dict(data, "$auth")

    def _from_vue_stores(self, cdp: CDPClient) -> str | None:
        raw = cdp.evaluate("""
        (function() {
            var results = {};
            try {
                var app = document.querySelector('#app');
                if (!app || !app.__vue_app__) return JSON.stringify({error: 'no_app'});

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

                // Axios / http defaults
                var gp = app.__vue_app__.config.globalProperties;
                var httpNames = ['$http','$axios','$api','$request','$config'];
                for (var n = 0; n < httpNames.length; n++) {
                    try {
                        var obj = gp[httpNames[n]];
                        if (obj && obj.defaults && obj.defaults.headers) {
                            results[httpNames[n] + '_defaults'] = obj.defaults.headers;
                        }
                    } catch(e) {}
                }
            } catch(e) { results.error = e.message; }
            return JSON.stringify(results);
        })()
        """)
        if not raw:
            return None
        data = self._safe_json(raw)
        if not isinstance(data, dict):
            return None
        return self._search_recursive(data, "vue")

    def _from_network_hook(self, cdp: CDPClient) -> str | None:
        """Inject hooks + trigger navigation + wait + read captured tokens.

        This is a self-contained one-shot: it does everything needed.
        For the CDP service lifecycle, prefer inject_hooks()/read_captured_tokens()
        to avoid double-navigation.
        """
        self.inject_hooks(cdp)

        # Trigger navigation to home to generate API requests
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
        time.sleep(2)

        return self.read_captured_tokens(cdp)

    # ── helpers ───────────────────────────────────────────────

    @staticmethod
    def _safe_json(raw: str) -> object:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

    def _match_in_dict(self, items: dict, source: str) -> str | None:
        # Pass 1: key name match
        for key, val in items.items():
            if not isinstance(val, str) or not val:
                continue
            for pattern in _TOKEN_KEY_PATTERNS:
                if pattern.search(key):
                    logger.info("token found in %s key=%s len=%s", source, key, len(val))
                    return val
        # Pass 2: JWT pattern
        for key, val in items.items():
            if not isinstance(val, str) or len(val) < 40:
                continue
            if val.startswith("Bearer ") or val.startswith("bearer "):
                logger.info("token found in %s key=%s (Bearer)", source, key)
                return val
            if val.count(".") == 2 and re.match(r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$', val):
                logger.info("token found in %s key=%s (JWT)", source, key)
                return val
            if len(val) >= 80 and re.match(r'^[A-Za-z0-9+/=_-]{80,}$', val):
                logger.info("token found in %s key=%s (long-token)", source, key)
                return val
        return None

    def _search_recursive(self, obj: object, path: str = "", depth: int = 0) -> str | None:
        if depth > 5:
            return None
        if isinstance(obj, dict):
            result = self._match_in_dict(obj, path)
            if result:
                return result
            for key, val in obj.items():
                result = self._search_recursive(val, f"{path}.{key}", depth + 1)
                if result:
                    return result
        elif isinstance(obj, list):
            for i, val in enumerate(obj):
                result = self._search_recursive(val, f"{path}[{i}]", depth + 1)
                if result:
                    return result
        return None

    def _persist(self, token: str, source: str) -> None:
        self._last_extracted = token
        self._last_extract_time = time.time()
        data = {
            "token": token,
            "timestamp": self._last_extract_time,
            "datetime": datetime.now(timezone.utc).isoformat(),
            "source": source,
            "method": "cdp_dom",
        }
        try:
            self._token_path.parent.mkdir(parents=True, exist_ok=True)
            self._token_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            logger.info("token persisted to %s (source=%s)", self._token_path, source)
        except Exception as exc:
            logger.warning("failed to write token to %s: %s", self._token_path, exc)


# ── default instance ─────────────────────────────────────────

_default_extractor: TokenExtractor | None = None


def get_extractor() -> TokenExtractor:
    global _default_extractor
    if _default_extractor is None:
        _default_extractor = TokenExtractor()
    return _default_extractor

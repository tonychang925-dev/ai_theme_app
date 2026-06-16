"""CLS 财联社电报 CDP 采集器 — 通过 Chrome DevTools Protocol 获取 Next.js 渲染后的 DOM。

架构:
  Chrome (headless, --remote-debugging-port=9223)
    └─ CDPClient (websocket)
         ├─ 创建标签页
         ├─ 导航到 cls.cn/telegraph
         ├─ 等待 Next.js 客户端渲染
         ├─ JS 提取 DOM innerText → 解析电报条目
         └─ 关闭标签页

用法:
  collector = ClsCdpCollector(cdp_port=9223)
  df = collector.fetch()  # 返回 pandas DataFrame，与 AkshareClsCollector 兼容
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date
from typing import Any

import pandas as pd
import requests
import websocket

logger = logging.getLogger(__name__)

# ── 配置 ──

CLS_URL = "https://www.cls.cn/telegraph"
KUXUN_URL = "https://kuaixun.eastmoney.com/"
DEFAULT_CDP_PORT = int(os.environ.get("CLS_CDP_PORT", "9224"))
PAGE_LOAD_TIMEOUT = 30.0
RENDER_WAIT_TIMEOUT = 15.0
MAX_ITEMS = 60

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
}

# ── JS 提取脚本 ──────────────────────────────────────────────────────────

CLS_EXTRACTION_JS = """
(function() {
    var items = [];
    var body = document.body.innerText;
    if (!body || body.length < 20) return JSON.stringify({items: [], source: 'empty'});

    var dateMatch = body.match(/(\\d{4})\\.(\\d{1,2})\\.(\\d{1,2})/);
    var tradeDate = dateMatch ? dateMatch[1] + '-' + dateMatch[2].padStart(2,'0') + '-' + dateMatch[3].padStart(2,'0') : '';

    var startIdx = dateMatch ? dateMatch.index : 0;
    var section = body.substring(startIdx);

    var pattern = /(\\d{2}:\\d{2}:\\d{2})【(.+?)】财联社(\\d{1,2})月(\\d{1,2})日电[，,]?([\\s\\S]*?)(?=\\n\\d{2}:\\d{2}:\\d{2}【|$)/g;

    var match;
    while ((match = pattern.exec(section)) !== null) {
        var content = (match[5] || '').trim();
        content = content.replace(/[\\n\\r]+阅\\s*[\\d.]+[W万]?\\s*$/gm, '');
        content = content.replace(/[\\n\\r]+评论\\s*\\(\\d+\\)\\s*$/gm, '');
        content = content.replace(/[\\n\\r]+分享\\s*\\(\\d+\\)\\s*$/gm, '');
        content = content.replace(/[\\n\\r]+查看原文\\s*$/g, '');
        content = content.replace(/\\n[^\\n]{1,20}$/g, '');
        content = content.replace(/\\.\\.\\.展开\\s*$/g, '');
        content = content.replace(/\\n{2,}/g, '\\n').replace(/\\n/g, ' ').trim();
        if (content.length < 3) continue;
        items.push({
            time: match[1],
            title: match[2].trim(),
            month: match[3],
            day: match[4],
            content: content
        });
        if (items.length >= 200) break;
    }
    return JSON.stringify({items: items, count: items.length, source: 'cls_cdp', trade_date: tradeDate});
})()
"""

KUXUN_EXTRACTION_JS = """
(function() {
    var items = [];
    var body = document.body.innerText;
    if (!body || body.length < 20) return JSON.stringify({items: [], source: 'empty'});

    var dateMatch = body.match(/(\\d{4})\\.(\\d{1,2})\\.(\\d{1,2})/);
    var tradeDate = dateMatch ? dateMatch[1] + '-' + dateMatch[2].padStart(2,'0') + '-' + dateMatch[3].padStart(2,'0') : '';

    var startIdx = dateMatch ? dateMatch.index : 0;
    var section = body.substring(startIdx);

    var pattern = /【(.+?)】([\\s\\S]*?)(?=\\n【|\\n\\d{2}:\\d{2}|$)/g;
    var match;
    while ((match = pattern.exec(section)) !== null) {
        var title = match[1].trim();
        var content = (match[2] || '').trim();
        content = content.replace(/^[\\d.]+%\\s*$/gm, '');
        content = content.replace(/\\n{2,}/g, '\\n').trim();
        if (title.length < 2) continue;
        items.push({ title: title, content: content || title });
        if (items.length >= 200) break;
    }

    var timeMatch = section.match(/(\\d{2}:\\d{2}:\\d{2})/);
    var latestTime = timeMatch ? timeMatch[1] : '';

    return JSON.stringify({items: items, count: items.length, source: 'eastmoney_kuaixun', trade_date: tradeDate, latest_time: latestTime});
})()
"""


# ── CDP 客户端 ────────────────────────────────────────────────────────────

class _CDPClient:
    """精简版 Chrome DevTools Protocol 客户端。"""

    def __init__(self, port: int = DEFAULT_CDP_PORT):
        self._port = port
        self._ws: websocket.WebSocket | None = None
        self._msg_id = 0

    # ── 连接管理 ──

    def check_available(self) -> bool:
        """检查 Chrome CDP 是否可用。"""
        try:
            resp = requests.get(
                f"http://localhost:{self._port}/json/version",
                timeout=3,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def create_page(self) -> tuple[str, str]:
        """创建新标签页，返回 (targetId, webSocketDebuggerUrl)。"""
        resp = requests.put(
            f"http://localhost:{self._port}/json/new?about:blank",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        tid = data.get("id", "")
        ws_url = data.get("webSocketDebuggerUrl", "")
        if not tid or not ws_url:
            raise RuntimeError(f"create page failed: {data}")
        return tid, ws_url

    def close_page(self, target_id: str) -> None:
        try:
            requests.get(
                f"http://localhost:{self._port}/json/close/{target_id}",
                timeout=10,
            )
        except Exception:
            pass

    def connect_ws(self, ws_url: str) -> None:
        self._ws = websocket.create_connection(ws_url, timeout=10)
        self._send("Runtime.enable")
        self._send("Page.enable")
        self._send("Network.enable")
        time.sleep(0.3)

    def disconnect(self) -> None:
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None

    # ── 页面操作 ──

    def navigate(self, url: str) -> None:
        self._send("Page.navigate", {"url": url})
        deadline = time.time() + PAGE_LOAD_TIMEOUT
        while time.time() < deadline:
            try:
                ready = self.evaluate("document.readyState", timeout=2.0)
                if ready == "complete":
                    time.sleep(2.0)
                    return
            except Exception:
                pass
            time.sleep(1.0)
        raise TimeoutError(f"Page load timed out after {PAGE_LOAD_TIMEOUT}s")

    def wait_for_content(self, min_length: int = 500) -> bool:
        """等待页面渲染出足够的内容。"""
        deadline = time.time() + RENDER_WAIT_TIMEOUT
        while time.time() < deadline:
            try:
                length = self.evaluate(
                    "document.body ? document.body.innerText.length : 0",
                    timeout=2.0,
                )
                if isinstance(length, (int, float)) and length >= min_length:
                    return True
            except Exception:
                pass
            time.sleep(1.0)
        return False

    def extract(self) -> dict[str, Any]:
        """执行 JS 提取，返回解析后的 dict。"""
        raw = self.evaluate(EXTRACTION_JS, timeout=10.0)
        if not raw:
            return {"items": [], "count": 0, "source": "cls_cdp", "trade_date": ""}
        return json.loads(raw) if isinstance(raw, str) else (raw or {})

    def evaluate(self, expression: str, timeout: float = 8.0) -> Any:
        if not self._ws:
            raise RuntimeError("CDP not connected")
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
            result = msg.get("result", {})
            if "exceptionDetails" in result:
                logger.debug("JS exception: %s", result["exceptionDetails"].get("text", ""))
                return None
            obj = result.get("result", {})
            if "value" in obj:
                return obj["value"]
            return None
        raise TimeoutError(f"evaluate timed out after {timeout}s")

    def _send(self, method: str, params: dict | None = None, mid: int | None = None) -> None:
        if not self._ws:
            raise RuntimeError("CDP not connected")
        self._ws.send(json.dumps({"id": mid or 0, "method": method, "params": params or {}}))


# ── 缓存/去重配置 ──

CACHE_MAX_AGE_SECONDS = 120    # 缓存最长有效期，超期强制重新提取
DEDUP_MAX_SIZE = 1000           # 去重窗口大小（最近 N 条）

# ── CLS CDP 采集器 ────────────────────────────────────────────────────────

import hashlib
from collections import OrderedDict


class ClsCdpCollector:
    """CLS 电报 CDP 采集器 — 与 AkshareClsCollector 兼容的 DataFrame 接口。

    特性:
      - 缓存命中: 页面指纹缓存，120s 内不重复导航
      - 去重提取: 基于 (发布时间, 规范化标题) 哈希，窗口 1000 条
      - limit 参数: 支持 10/50/100 条可选

    用法:
        collector = ClsCdpCollector(cdp_port=9223)
        df = collector.fetch_df(limit=30)
    """

    def __init__(self, cdp_port: int = DEFAULT_CDP_PORT, *,
                 url: str = CLS_URL,
                 extraction_js: str = CLS_EXTRACTION_JS,
                 source_name: str = "cls_cdp",
                 cache_max_age: float = CACHE_MAX_AGE_SECONDS,
                 content_min_length: int = 500):
        self._cdp_port = cdp_port
        self._url = url
        self._extraction_js = extraction_js
        self._source_name = source_name
        self._cache_max_age = cache_max_age
        self._content_min_length = content_min_length
        self._cache_at: float = 0.0
        self._cache_fingerprint: str = ""
        self._cache_items: list[dict] = []
        self._seen_hashes: OrderedDict[str, None] = OrderedDict()
        self._stats = {"cache_hits": 0, "fresh_fetches": 0, "duplicates_skipped": 0}

    @property
    def source_name(self) -> str:
        return self._source_name

    def stats(self) -> dict:
        """返回采集统计信息。"""
        return dict(self._stats)

    # ── 公共接口 ──────────────────────────────────────────────────────

    def fetch_df(self, limit: int = MAX_ITEMS) -> pd.DataFrame:
        """返回 DataFrame（兼容 AkshareClsCollector.fetch() 返回值）。"""
        items = self.fetch_items(limit=limit)
        if not items:
            return pd.DataFrame()

        trade_date = self._resolve_trade_date(items)
        rows = [
            {
                "标题": it.get("title", ""),
                "内容": it.get("content", ""),
                "发布日期": trade_date,
                "发布时间": it.get("time", ""),
                "市场": "A股",
                "URL": self._url,
            }
            for it in items
        ]
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(by=["发布时间"], ascending=False).reset_index(drop=True)
        return df

    def fetch_items(self, limit: int = MAX_ITEMS) -> list[dict]:
        """执行 CDP 采集，返回原始 dict 列表。

        流程: 缓存命中(指纹+TTL) → 新提取 → 去重 → 截断 limit
        """
        cdp = _CDPClient(self._cdp_port)

        if not cdp.check_available():
            logger.warning("Chrome CDP not available on port %s, skipping CLS", self._cdp_port)
            return []

        limit = max(1, min(int(limit), 200))
        target_id = None
        try:
            # ── 阶段 1: 缓存检查 ──
            cache_age_s = time.time() - self._cache_at
            if (
                self._cache_fingerprint
                and cache_age_s < self._cache_max_age
            ):
                target_id, ws_url = cdp.create_page()
                cdp.connect_ws(ws_url)
                cdp.navigate(self._url)
                if not cdp.wait_for_content(min_length=self._content_min_length):
                    logger.warning("%s page render timeout (cache check)", self._source_name)
                    return []

                fingerprint = self._compute_fingerprint(cdp)
                if fingerprint == self._cache_fingerprint:
                    self._stats["cache_hits"] += 1
                    logger.info(
                        "%s → cache hit  fingerprint=%s  age=%.0fs  items=%d  "
                        "hits=%d fetches=%d skipped=%d",
                        self._source_name,
                        fingerprint[:8],
                        cache_age_s,
                        len(self._cache_items),
                        self._stats["cache_hits"],
                        self._stats["fresh_fetches"],
                        self._stats["duplicates_skipped"],
                    )
                    items = list(self._cache_items)
                else:
                    items = self._fresh_fetch(cdp, fingerprint, limit=None)
            else:
                # TTL 过期或首次采集
                target_id, ws_url = cdp.create_page()
                cdp.connect_ws(ws_url)
                cdp.navigate(self._url)
                if not cdp.wait_for_content(min_length=self._content_min_length):
                    logger.warning("%s page render timeout", self._source_name)
                    return []
                fingerprint = self._compute_fingerprint(cdp)
                items = self._fresh_fetch(cdp, fingerprint, limit=None)

            # ── 阶段 2: 去重 ──
            deduped = []
            for item in items:
                key = self._make_dedup_key(item)
                if key not in self._seen_hashes:
                    self._seen_hashes[key] = None
                    deduped.append(item)

            while len(self._seen_hashes) > DEDUP_MAX_SIZE:
                self._seen_hashes.popitem(last=False)

            skipped = len(items) - len(deduped)
            if skipped:
                self._stats["duplicates_skipped"] += skipped

            # ── 阶段 3: 截断 ──
            return deduped[:limit]

        except Exception as exc:
            logger.warning("CLS CDP collection failed: %s", exc)
            return []
        finally:
            if target_id:
                cdp.close_page(target_id)
            cdp.disconnect()

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _fresh_fetch(
        self, cdp: _CDPClient, fingerprint: str, limit: int | None
    ) -> list[dict]:
        """执行完整 JS 提取并更新缓存。"""
        self._stats["fresh_fetches"] += 1
        raw = cdp.evaluate(self._extraction_js, timeout=10.0)
        if not raw:
            return []
        result = json.loads(raw) if isinstance(raw, str) else (raw or {})
        items = result.get("items", [])
        self._cache_at = time.time()
        self._cache_fingerprint = fingerprint or ""
        self._cache_items = list(items)
        logger.info(
            "%s → fresh    fingerprint=%s  items=%d  trade_date=%s  "
            "hits=%d fetches=%d skipped=%d",
            self._source_name,
            fingerprint[:8] if fingerprint else "none",
            len(items),
            result.get("trade_date", ""),
            self._stats["cache_hits"],
            self._stats["fresh_fetches"],
            self._stats["duplicates_skipped"],
        )
        return items

    @staticmethod
    def _compute_fingerprint(cdp: _CDPClient) -> str:
        """页面指纹 — 前 2000 字符 + top-3 电报标题。"""
        try:
            js = """
            (function() {
                var text = document.body ? document.body.innerText : '';
                var prefix = text.substring(0, 2000);
                var titles = [];
                var re = /\\d{2}:\\d{2}:\\d{2}【(.+?)】/g;
                var m;
                while ((m = re.exec(text)) !== null && titles.length < 3) {
                    titles.push(m[1]);
                }
                return prefix + '|' + titles.join('|');
            })()
            """
            raw = cdp.evaluate(js, timeout=5.0)
            return hashlib.sha256(str(raw or "").encode("utf-8")).hexdigest()
        except Exception:
            return ""

    @staticmethod
    def _make_dedup_key(item: dict) -> str:
        """去重键: (时间, 规范化标题) — 去掉空白和特殊字符。"""
        title = (item.get("title") or "").strip()
        # 规范化: 去掉多余空格/特殊 Unicode 空白
        import unicodedata
        title = unicodedata.normalize("NFKC", title)
        title = " ".join(title.split())
        payload = f'{item.get("time","")}|{title}'
        return hashlib.md5(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _resolve_trade_date(items: list[dict]) -> str:
        today = date.today()
        if not items:
            return today.isoformat()
        first = items[0]
        try:
            month = int(first.get("month") or 0)
            day = int(first.get("day") or 0)
            if 1 <= month <= 12 and 1 <= day <= 31:
                return f"{today.year}-{month:02d}-{day:02d}"
        except (ValueError, TypeError):
            pass
        return today.isoformat()

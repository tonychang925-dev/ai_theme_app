#!/usr/bin/env python3
"""CLS 财联社电报采集器 — 通过 Chrome CDP 获取 Next.js 渲染后的 DOM 内容。

依赖: websocket-client, requests
用法:
  python scripts/cls_cdp_collector.py [--cdp-port 9223] [--max-items 30]

架构:
  Chrome (CDP 9223) ← websocket → CDPClient → DOM extract → telegraph items
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import time
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests
import websocket

logger = logging.getLogger("cls_cdp")

# ── CDP 基础设施 ──────────────────────────────────────────────────────────

class CDPClient:
    """通用 Chrome DevTools Protocol 客户端 — 复用自 jyhf_cdp_service 的精简版。"""

    def __init__(self, cdp_port: int = 9223):
        self._port = cdp_port
        self._ws: websocket.WebSocket | None = None
        self._msg_id = 0
        self._target_id: str | None = None

    # ── 浏览器级操作 ──────────────────────────────────────────────────

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

    def close_page(self, target_id: str | None = None) -> None:
        tid = target_id or self._target_id
        if tid:
            try:
                requests.get(
                    f"http://localhost:{self._port}/json/close/{tid}",
                    timeout=10,
                )
            except Exception:
                pass

    def connect_page_ws(self, ws_url: str) -> None:
        """直接通过 WebSocket URL 连接到页面。"""
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

    # ── 页面操作 ──────────────────────────────────────────────────────

    def navigate(self, url: str, timeout: float = 30.0) -> None:
        """导航到 URL 并等待页面加载完成。"""
        # 使用 CDP Page.navigate 触发加载
        self._send("Page.navigate", {"url": url})
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                ready = self.evaluate("document.readyState", timeout=2.0)
                if ready == "complete":
                    # 额外等待 JS 渲染
                    time.sleep(2.0)
                    return
            except Exception:
                pass
            time.sleep(1.0)
        raise TimeoutError(f"Page load timed out after {timeout}s")

    def wait_for_selector(self, selector: str, timeout: float = 30.0) -> bool:
        """等待某个 CSS 选择器出现。"""
        expr = f"!!document.querySelector({json.dumps(selector)})"
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                if self.evaluate(expr, timeout=2.0):
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def evaluate(self, expression: str, timeout: float = 8.0) -> Any:
        """在页面执行 JavaScript 并返回结果。"""
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
                exc = result["exceptionDetails"].get("text", "JS exception")
                logger.warning("JS exception: %s", exc)
                return None
            obj = result.get("result", {})
            if "value" in obj:
                return obj["value"]
            if obj.get("type") == "undefined":
                return None
            return None
        raise TimeoutError(f"evaluate timed out after {timeout}s")

    def page_text(self) -> str:
        """获取页面可见文本。"""
        text = self.evaluate("document.body.innerText", timeout=5.0)
        return str(text) if text else ""

    # ── 内部方法 ──────────────────────────────────────────────────────

    def _send(self, method: str, params: dict | None = None, mid: int | None = None) -> None:
        if not self._ws:
            raise RuntimeError("CDP not connected")
        self._ws.send(json.dumps({"id": mid or 0, "method": method, "params": params or {}}))




# ── CLS 电报提取器 ────────────────────────────────────────────────────────

CLS_URL = "https://www.cls.cn/telegraph"

EXTRACTION_JS = """
(function() {
    var items = [];
    var body = document.body.innerText;
    if (!body || body.length < 20) return JSON.stringify({items: [], source: 'empty'});

    // CLS Next.js 渲染后 innerText (2026-05-31 实测):
    //   2026.05.31 星期日 11:33:04
    //   桌面通知 声音提醒 ... (control bar)
    //   日期
    //   11:08:10【title】财联社5月31日电，content...
    //   tag_name
    //   阅XX.XW
    //   评论(N)
    //   分享(N)

    // 提取交易日期 (YYYY.MM.DD)
    var dateMatch = body.match(/(\\d{4})\\.(\\d{1,2})\\.(\\d{1,2})/);
    var tradeDate = dateMatch ? dateMatch[1] + '-' + dateMatch[2].padStart(2,'0') + '-' + dateMatch[3].padStart(2,'0') : '';

    // 从日期头开始截取
    var startIdx = dateMatch ? dateMatch.index : 0;
    var section = body.substring(startIdx);

    // 匹配电报: HH:MM:SS【title】财联社M月D日电[，,]content...
    var pattern = /(\\d{2}:\\d{2}:\\d{2})【(.+?)】财联社(\\d{1,2})月(\\d{1,2})日电[，,]?([\\s\\S]*?)(?=\\n\\d{2}:\\d{2}:\\d{2}【|$)/g;

    var match;
    while ((match = pattern.exec(section)) !== null) {
        var content = (match[5] || '').trim();

        // 清理尾部非内容行: 阅/评论/分享/查看原文
        content = content.replace(/[\\n\\r]+阅\\s*[\\d.]+[W万]?\\s*$/gm, '');
        content = content.replace(/[\\n\\r]+评论\\s*\\(\\d+\\)\\s*$/gm, '');
        content = content.replace(/[\\n\\r]+分享\\s*\\(\\d+\\)\\s*$/gm, '');
        content = content.replace(/[\\n\\r]+查看原文\\s*$/g, '');

        // 清理展开标记
        content = content.replace(/\\.\\.\\.展开\\s*$/g, '');
        // 清理末尾单行标签名 (如 "中东冲突", "网约车")
        content = content.replace(/\\n[^\\n]{1,20}$/g, '');
        // 合并多余空行，将 innerText 换行转空格
        content = content.replace(/\\n{2,}/g, '\\n').replace(/\\n/g, ' ').trim();

        if (content.length < 3) continue;

        items.push({
            time: match[1].substring(0, 5),
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


class ClsTelegraphCollector:
    """CLS 电报 CDP 采集器。"""

    def __init__(self, cdp_port: int = 9223):
        self._cdp = CDPClient(cdp_port)

    def collect(self, max_items: int = 30) -> dict[str, Any]:
        """执行一次采集循环。

        Returns:
            {"items": [...], "count": N, "trade_date": "2026-05-31",
             "source": "cls_cdp", "error": None}
        """
        result: dict[str, Any] = {
            "items": [],
            "count": 0,
            "trade_date": "",
            "source": "cls_cdp",
            "error": None,
        }

        target_id = None
        try:
            # 1. 创建新标签页，直接拿 wsURL
            target_id, ws_url = self._cdp.create_page()
            self._cdp.connect_page_ws(ws_url)

            # 2. 导航到 CLS 电报页
            logger.info("navigating to %s", CLS_URL)
            self._cdp.navigate(CLS_URL, timeout=30.0)

            # 3. 等待 Next.js 渲染完成 — 等待电报条目出现
            #    CLS Next.js 加载后，DOM 中会出现带"财联社电报"的文本
            logger.info("waiting for Next.js render...")
            ready = self._cdp.wait_for_selector(
                "[class*='telegraph'], [class*='Telegraph'], [class*='roll']",
                timeout=15.0,
            )
            if not ready:
                # fallback: 直接检查 innerText 是否有内容
                body_text = self._cdp.page_text()
                if len(body_text) < 100:
                    result["error"] = "page render timeout — innerText too short"
                    logger.warning("page_text len=%d", len(body_text))
                    return result

            # 4. 额外等待确保数据接口返回并渲染
            time.sleep(3.0)

            # 5. 检查 page_text
            body_text = self._cdp.page_text()
            logger.info("page_text len=%d preview=%s", len(body_text), body_text[:180])

            # 6. 执行 JS 提取
            raw_json = self._cdp.evaluate(EXTRACTION_JS, timeout=10.0)
            if not raw_json:
                result["error"] = "extraction returned None"
                return result

            parsed = json.loads(raw_json) if isinstance(raw_json, str) else raw_json
            items = parsed.get("items", [])

            # 7. 限制数量
            items = items[:max_items]

            # 8. 组装返回
            trade_date = self._resolve_trade_date(items)
            sorted_items = sorted(items, key=lambda x: x.get("time", ""), reverse=True)

            result["items"] = sorted_items
            result["count"] = len(sorted_items)
            result["trade_date"] = trade_date
            logger.info("collected %d telegraph items from CLS", len(sorted_items))
            return result

        except Exception as exc:
            logger.exception("CLS collection failed")
            result["error"] = str(exc)
            return result
        finally:
            if target_id:
                try:
                    self._cdp.close_page(target_id)
                except Exception:
                    pass
                try:
                    self._cdp.disconnect()
                except Exception:
                    pass

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


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="CLS Telegraph CDP Collector")
    ap.add_argument("--cdp-port", type=int, default=9223)
    ap.add_argument("--max-items", type=int, default=30)
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    collector = ClsTelegraphCollector(cdp_port=args.cdp_port)
    result = collector.collect(max_items=args.max_items)

    if result["error"]:
        logger.error("collection failed: %s", result["error"])
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    logger.info(
        "done: count=%d trade_date=%s",
        result["count"],
        result["trade_date"],
    )


if __name__ == "__main__":
    main()

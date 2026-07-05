#!/usr/bin/env python3
"""
JYHF Notification Popup Collector — standalone, minimal.

Connects to the JYHF Electron app via CDP, injects a persistent Vue Router
hook to capture push notifications, and polls for accumulated notifications.
Writes unmasked event data directly to ``subject_history_staging`` so the
stock_processing_service intel feed picks it up and the frontend displays it.

Usage::

    python scripts/run_jyhf_popup_collector.py
    python scripts/run_jyhf_popup_collector.py --interval 15  # poll every 15s
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import signal
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path
from urllib.parse import unquote

import asyncpg
import websocket

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

CDP_PORT = 9223
DEFAULT_INTERVAL = 20

logger = logging.getLogger("jyhf_popup")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ── CDP helpers ──────────────────────────────────────────────

def _cdp_connect() -> websocket.WebSocket | None:
    """Connect to JYHF app's CDP endpoint. Returns None if app not found."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{CDP_PORT}/json"],
            capture_output=True, text=True, timeout=5,
        )
        pages = json.loads(result.stdout or "[]")
    except Exception:
        return None
    target = next((p for p in pages if "久赢恒丰" in str(p.get("title", ""))), None)
    if not target:
        return None
    return websocket.create_connection(target["webSocketDebuggerUrl"], timeout=10)


def _cdp_evaluate(ws: websocket.WebSocket, expression: str, timeout: float = 8.0) -> object:
    """Evaluate JS in the renderer, return the result value."""
    mid = int(time.time() * 1000) % 100000
    ws.send(json.dumps({
        "id": mid, "method": "Runtime.evaluate",
        "params": {"expression": expression, "returnByValue": True, "awaitPromise": True},
    }))
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msg = json.loads(ws.recv())
        except Exception:
            continue
        if msg.get("id") == mid:
            result = msg.get("result", {}).get("result", {})
            return result.get("value") if "value" in result else None
    return None


# ── DB helpers ────────────────────────────────────────────────

async def _get_db():
    return await asyncpg.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
        database=os.getenv("PG_DATABASE", "stock_data_test"),
        user=os.getenv("PG_USERNAME", "postgres"),
        password=os.getenv("PG_PASSWORD", ""),
    )


async def write_popup_to_db(raw: dict) -> bool:
    """Write one captured notification to subject_history_staging."""
    subject_name = str(raw.get("subject_name") or "").strip()
    subject_id = str(raw.get("subject_id") or "").strip()
    content = str(raw.get("content") or "").strip()

    if not subject_name or not content:
        return False

    driver_title = ""
    driver_desc = ""
    news_source = ""

    dm = re.search(r"【驱动事件[：:](.*?)】", content)
    if dm:
        driver_title = dm.group(1).strip()

    sm = re.search(r"（新闻来源[：:](.*?)）", content)
    if sm:
        news_source = sm.group(1).strip()

    desc_start = content.find("】") + 1
    desc_end = content.find("（新闻来源：")
    if desc_end < 0:
        desc_end = len(content)
    if 0 < desc_start < desc_end:
        driver_desc = content[desc_start:desc_end].strip()
    elif desc_start > 0:
        driver_desc = content[desc_start:].strip()

    desc = f"【驱动事件：{driver_title}】\n{driver_desc}"
    if news_source:
        desc += f"\n（新闻来源：{news_source}）"

    td = date.today()
    try:
        conn = await _get_db()
        await conn.execute(
            "INSERT INTO subject_history_staging "
            "(subject_key,subject_name,rank_date,description,heat,heat_name,pct_chg,his_pct_chg,source_type,ingest_batch_id) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
            subject_id, subject_name, td, desc,
            3, "热", 0.0, 0.0,
            "jyhf_cdp", f"popup_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        )
        await conn.close()
        logger.info("DB write ok: %s (id=%s) — %s", subject_name, subject_id, driver_title[:50])
        return True
    except Exception as exc:
        logger.error("DB write failed: %s", exc)
        return False


# ── CDP capture ───────────────────────────────────────────────

_INJECT_FLAG = "__cdp_popup_hooks_v2__"
_NOTIF_STORE = "__cdp_popup_notifications__"


def ensure_hooks(ws: websocket.WebSocket) -> bool:
    """Inject persistent hooks. Returns True if freshly injected."""
    flag = _cdp_evaluate(ws, f"window.{_INJECT_FLAG}", timeout=2.0)
    if flag is True:
        return False

    result = _cdp_evaluate(ws, """
    (function() {
        if (window.__cdp_popup_hooks_v2__) return 'already';
        window.__cdp_popup_hooks_v2__ = true;
        window.__cdp_popup_notifications__ = [];

        // ── Vue Router hook ──
        try {
            var app = document.querySelector('#app');
            if (app && app.__vue_app__) {
                var router = app.__vue_app__.config.globalProperties.$router;
                if (router) {
                    router.beforeEach(function(to, from, next) {
                        var fp = to.fullPath || to.path || '';
                        if (fp.indexOf('/notification') >= 0) {
                            var q = to.query || {};
                            window.__cdp_popup_notifications__.push({
                                source: 'router',
                                route: q.route || '',
                                subject_id: q.extraId || '',
                                subject_name: decodeURIComponent(q.extraName || ''),
                                title: decodeURIComponent(q.title || ''),
                                content: decodeURIComponent(q.content || ''),
                                captured_at: new Date().toISOString()
                            });
                        }
                        next();
                    });
                }
            }
        } catch(e) {}

        // ── hashchange backup ──
        window.addEventListener('hashchange', function() {
            var hash = window.location.hash || '';
            var idx = hash.indexOf('/notification?');
            if (idx < 0) return;
            var qs = hash.substring(idx + '/notification?'.length);
            var params = {};
            var pairs = qs.split('&');
            for (var i = 0; i < pairs.length; i++) {
                var eq = pairs[i].indexOf('=');
                if (eq < 0) continue;
                try { params[pairs[i].substring(0,eq)] = decodeURIComponent(pairs[i].substring(eq+1)); }
                catch(e2) {}
            }
            if (params.extraId || params.extraName) {
                window.__cdp_popup_notifications__.push({
                    source: 'hashchange',
                    route: params.route || '',
                    subject_id: params.extraId || '',
                    subject_name: params.extraName || '',
                    title: params.title || '',
                    content: params.content || '',
                    captured_at: new Date().toISOString()
                });
            }
        });

        // ── Also check current route for existing popup ──
        var hash = window.location.hash || '';
        if (hash.indexOf('/notification?') >= 0) {
            var qi = hash.indexOf('?');
            var qs2 = hash.substring(qi + 1);
            var p2 = {};
            var ps = qs2.split('&');
            for (var j = 0; j < ps.length; j++) {
                var e2 = ps[j].indexOf('=');
                if (e2 < 0) continue;
                try { p2[ps[j].substring(0,e2)] = decodeURIComponent(ps[j].substring(e2+1)); }
                catch(e3) {}
            }
            if (p2.extraId || p2.extraName) {
                window.__cdp_popup_notifications__.push({
                    source: 'preexisting',
                    route: p2.route || '',
                    subject_id: p2.extraId || '',
                    subject_name: p2.extraName || '',
                    title: p2.title || '',
                    content: p2.content || '',
                    captured_at: new Date().toISOString()
                });
            }
        }

        return 'injected';
    })()
    """, timeout=8.0)
    logger.info("Hooks injected: %s", result)
    return True


def drain_notifications(ws: websocket.WebSocket) -> list[dict]:
    """Read and clear accumulated notifications from JS memory."""
    raw = _cdp_evaluate(ws, f"""
    (function() {{
        var arr = window.{_NOTIF_STORE} || [];
        window.{_NOTIF_STORE} = [];
        return JSON.stringify(arr);
    }})()
    """, timeout=3.0)
    if not raw:
        return []
    try:
        return json.loads(raw) if isinstance(raw, str) else (raw or [])
    except json.JSONDecodeError:
        return []


# ── Main loop ─────────────────────────────────────────────────

async def run(interval: int = DEFAULT_INTERVAL) -> None:
    """Main polling loop."""
    running = True

    def _stop(signum, frame):
        nonlocal running
        running = False
        logger.info("shutting down...")

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    logger.info("started interval=%ss CDP port=%s", interval, CDP_PORT)

    while running:
        ws = None
        try:
            ws = _cdp_connect()
            if ws is None:
                logger.warning("app not found on CDP port %s, retry in %ss", CDP_PORT, interval)
                await asyncio.sleep(interval)
                continue

            # Enable Runtime
            ws.send(json.dumps({"id": 0, "method": "Runtime.enable", "params": {}}))
            time.sleep(0.3)
            ws.settimeout(0.3)
            for _ in range(10):
                try: ws.recv()
                except: break

            # Inject hooks (idempotent)
            ensure_hooks(ws)

            # Drain accumulated notifications
            notifs = drain_notifications(ws)
            if notifs:
                logger.info("drained %s notifications", len(notifs))
                for n in notifs:
                    await write_popup_to_db(n)
            else:
                logger.debug("no new notifications")

        except Exception as exc:
            logger.error("cycle error: %s", exc)
        finally:
            if ws:
                try: ws.close()
                except: pass

        await asyncio.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="JYHF popup collector")
    parser.add_argument("--interval", type=int, default=DEFAULT_INTERVAL,
                        help=f"Poll interval in seconds (default {DEFAULT_INTERVAL})")
    args = parser.parse_args()
    asyncio.run(run(interval=args.interval))


if __name__ == "__main__":
    main()

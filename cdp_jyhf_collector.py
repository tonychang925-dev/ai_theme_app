#!/usr/bin/env python3
"""
CDP-based JYHF Data Collector

通过 Chrome DevTools Protocol 连接久赢恒丰 Electron 应用，
自动导航页面提取题材排行/轮动数据，可直接写入数据库；
JSONL 导出仅作为可选排查/回滚产物。

用法:
  python cdp_jyhf_collector.py --date 2026-05-06
  python cdp_jyhf_collector.py --date 2026-05-06 --import-db
  python cdp_jyhf_collector.py --date 2026-05-06 --export-jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import websocket

from database_service.scripts.import_jyhf_history_incremental import (
    ensure_event_theme_columns,
    ensure_jyhf_theme_master_rows,
    ensure_tables as ensure_jyhf_history_tables,
    get_postgres_config,
    sync_records as sync_jyhf_history_records,
)

PROJECT_ROOT = Path(__file__).resolve().parent
HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"
DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "daily"
MANIFEST_DIR = PROJECT_ROOT / "theme_data_complete" / "_manifests"

JYHF_APP_PATH = "/Applications/久赢恒丰.app"
CDP_PORT = 9223


# ── CDP Client ──────────────────────────────────────────────

class CDPClient:
    """Minimal CDP client for JYHF Electron app."""

    def __init__(self, port: int = CDP_PORT) -> None:
        self._port = port
        self._ws: Optional[websocket.WebSocket] = None
        self._msg_id = 0

    def connect(self) -> None:
        """Connect to JYHF app's CDP endpoint."""
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{self._port}/json"],
            capture_output=True, text=True,
        )
        pages = json.loads(result.stdout)
        target = None
        for p in pages:
            if "久赢恒丰" in p.get("title", ""):
                target = p
                break
        if not target:
            raise RuntimeError("JYHF app not found. Start it with: "
                               f'open -a "久赢恒丰" --args --remote-debugging-port={self._port}')

        self._ws = websocket.create_connection(
            target["webSocketDebuggerUrl"],
            timeout=10,
        )
        # Enable Runtime domain
        self._send("Runtime.enable")
        time.sleep(0.3)
        self._recv_all(0.5)

    def close(self) -> None:
        if self._ws:
            self._ws.close()
            self._ws = None

    def evaluate(self, expression: str, timeout: float = 8.0) -> Any:
        """Evaluate JavaScript in the renderer and return the result."""
        if not self._ws:
            raise RuntimeError("Not connected")
        self._msg_id += 1
        mid = self._msg_id
        self._send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
        }, mid)
        time.sleep(0.3)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msg = json.loads(self._ws.recv())
            except (websocket.WebSocketTimeoutException, json.JSONDecodeError):
                continue
            except Exception:
                break
            if msg.get("id") == mid:
                result = msg.get("result", {}).get("result", {})
                if "value" in result:
                    return result["value"]
                if result.get("type") == "undefined":
                    return None
                if "exception" in msg.get("result", {}):
                    err = msg["result"]["exception"].get("description", "?")
                    raise RuntimeError(f"JS exception: {err[:300]}")
                return None
        raise TimeoutError(f"evaluate timed out after {timeout}s")

    def navigate(self, path: str) -> None:
        """Navigate to a route in the app."""
        self.evaluate(
            f"document.querySelector('#app').__vue_app__"
            f".config.globalProperties.$router.push('{path}')"
        )
        time.sleep(4)  # Wait for page load

    def _send(self, method: str, params: dict | None = None, mid: int | None = None) -> None:
        msg = {"id": mid or 0, "method": method, "params": params or {}}
        self._ws.send(json.dumps(msg))

    def _recv_all(self, timeout: float = 1.0) -> list[dict]:
        msgs = []
        self._ws.settimeout(0.3)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                msgs.append(json.loads(self._ws.recv()))
            except (websocket.WebSocketTimeoutException, json.JSONDecodeError):
                continue
            except Exception:
                break
        return msgs


# ── App Launcher ────────────────────────────────────────────

def ensure_app_running() -> bool:
    """Ensure JYHF Electron app is running with CDP enabled."""
    try:
        result = subprocess.run(
            ["curl", "-s", f"http://localhost:{CDP_PORT}/json"],
            capture_output=True, text=True, timeout=5,
        )
        pages = json.loads(result.stdout)
        for p in pages:
            if "久赢恒丰" in p.get("title", ""):
                print(f"[OK] JYHF app already running (CDP port {CDP_PORT})")
                return True
    except Exception:
        pass

    print(f"[START] Launching JYHF app with CDP on port {CDP_PORT}...")
    subprocess.Popen(
        [f"{JYHF_APP_PATH}/Contents/MacOS/久赢恒丰",
         f"--remote-debugging-port={CDP_PORT}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # Wait for app to start
    for _ in range(20):
        time.sleep(2)
        try:
            result = subprocess.run(
                ["curl", "-s", f"http://localhost:{CDP_PORT}/json"],
                capture_output=True, text=True, timeout=5,
            )
            pages = json.loads(result.stdout)
            for p in pages:
                if "久赢恒丰" in p.get("title", ""):
                    print(f"[OK] JYHF app started successfully")
                    time.sleep(3)  # Wait for full initialization
                    return True
        except Exception:
            continue
    raise RuntimeError("Failed to start JYHF app")


# ── Data Extractors ─────────────────────────────────────────

def extract_subject_ranking(cdp: CDPClient) -> list[dict]:
    """Extract subject ranking data from 题材挖掘榜 (excavate page).

    DOM format (vxe-table component):
      row: "rank\\n\\t\\nsubject_name\\n\\t\\nN次\\n\\t\\n+pct%"
      Header: "排名\\n\\t\\n题材名称\\n\\t\\n入选次数(十日)\\n\\t\\n当日涨幅"

    Returns list of dicts with keys:
    subject_name, pct_chg, appearance_count_10d, rank
    """
    print("[EXTRACT] Subject ranking from /subject/excavate ...")
    cdp.navigate("/subject/excavate")

    data = cdp.evaluate("""
    (function() {
        var text = document.body.innerText;
        // Find the ranking table: locate "排名" header
        var startIdx = text.indexOf('排名\\n\\t\\n题材名称');
        if (startIdx === -1) return JSON.stringify([]);

        // Get text from the header to ~2000 chars after
        var section = text.substring(startIdx, startIdx + 4000);

        // Split by triple-newline (row separator)
        var rows = section.split('\\n\\n\\n');
        var results = [];

        for (var i = 1; i < rows.length; i++) {  // skip header
            // Each row: "rank\\n\\t\\nname\\n\\t\\ncountStr\\n\\t\\npctStr"
            var parts = rows[i].split('\\n\\t\\n');
            if (parts.length < 4) continue;

            var rank = parseInt(parts[0].trim());
            var name = parts[1].trim();
            var countStr = parts[2].trim();
            var pctStr = parts[3].trim();

            if (isNaN(rank) || !name) continue;

            results.push({
                rank: rank,
                subject_name: name,
                appearance_count_10d: parseInt(countStr.replace('次','')) || 0,
                pct_chg: parseFloat(pctStr.replace('%','').replace('+','')) || 0
            });

            if (results.length >= 50) break;
        }
        return JSON.stringify(results);
    })()
    """)
    items = json.loads(data) if isinstance(data, str) else (data or [])
    print(f"  -> Extracted {len(items)} subject rankings")
    if items:
        for r in items[:3]:
            print(f"     #{r['rank']} {r['subject_name']}: {r['pct_chg']}% ({r['appearance_count_10d']}次)")
    return items


def extract_daily_subjects(cdp: CDPClient, target_date: str) -> list[dict]:
    """Extract daily subject appearances from 题材轮动 (periodic page).

    The page has clickable dates in a left panel, and a VXE table showing
    subjects for the clicked date. We click the target date to make it
    visible, then parse the table data.

    Returns list of dicts with keys:
    rank_date, subject_name, appearance_count
    """
    print(f"[EXTRACT] Daily subjects from /subject/periodic for {target_date} ...")
    cdp.navigate("/subject/periodic")

    parts = target_date.split("-")
    date_formatted = f"{parts[1]}月{parts[2]}日"

    # Step 1: Click the target date to make it active in the table
    data = cdp.evaluate(f"""
    (function() {{
        var allElements = document.querySelectorAll('*');
        var dateEl = null;
        for (var i = 0; i < allElements.length; i++) {{
            var el = allElements[i];
            if (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3) {{
                if (el.textContent.trim() === '{date_formatted}') {{
                    dateEl = el;
                    break;
                }}
            }}
        }}
        if (dateEl) {{
            dateEl.click();
            return 'clicked_{date_formatted}';
        }}
        return 'element_not_found';
    }})()
    """)
    print(f"  -> Click: {data}")
    time.sleep(2)  # Wait for table to update

    # Step 2: Read VXE table rows directly
    # Each TR.vxe-body--row = one date's data, in newest-to-oldest order
    data = cdp.evaluate(f"""
    (function() {{
        // Get the date list to find the row index
        var text = document.body.innerText;
        var dateRegex = /\\d{{2}}月\\d{{2}}日/g;
        var dates = [];
        var m;
        while ((m = dateRegex.exec(text)) !== null) {{
            dates.push(m[0]);
        }}
        var dateIdx = dates.indexOf('{date_formatted}');
        if (dateIdx === -1) return JSON.stringify({{error: 'date not found', dates: dates.slice(0, 5)}});

        // Read data rows: each TR.vxe-body--row is one date
        var rows = document.querySelectorAll('tr.vxe-body--row');
        if (rows.length === 0) return JSON.stringify({{error: 'no vxe-body--row found'}});

        // The rows are in newest-to-oldest order, matching the date list
        if (dateIdx >= rows.length) return JSON.stringify({{error: 'row idx out of range', dateIdx: dateIdx, rows: rows.length}});

        var rowText = rows[dateIdx].innerText.trim();

        // Parse: "subject1\\ncount1\\n\\t\\nsubject2\\ncount2..."
        var entries = rowText.split('\\n\\t\\n');
        var results = [];
        for (var i = 0; i < entries.length; i++) {{
            var parts = entries[i].split('\\n');
            if (parts.length >= 2) {{
                var name = parts[0].trim();
                var count = parseInt(parts[1]) || 0;
                if (name && count > 0 && name.length > 1) {{
                    results.push({{
                        rank_date: '{target_date}',
                        subject_name: name,
                        appearance_count: count
                    }});
                }}
            }}
        }}
        return JSON.stringify({{results: results, dateIdx: dateIdx, totalRows: rows.length}});
    }})()
    """)
    result = json.loads(data) if isinstance(data, str) else (data or {})
    if isinstance(result, dict) and "error" in result:
        print(f"  -> WARNING: {result['error']}")
        return []

    items = result.get("results", [])
    date_idx = result.get("dateIdx", -1)
    total_rows = result.get("totalRows", 0)
    print(f"  -> Date index {date_idx} in {total_rows} rows")

    print(f"  -> Extracted {len(items)} daily subject entries for {target_date}")
    if items:
        for r in items[:5]:
            print(f"     {r['subject_name']}: {r['appearance_count']}")
    return items


def extract_driver_events(cdp: CDPClient, subject_map: dict[str, str]) -> list[dict]:
    """Extract driver events from the '新事件' (New Events) tab on home page.

    The 新事件 tab shows a chronological feed of events for the current day.
    Each event has: time, subject_name, pct_chg, driver_title, driver_desc, news_source.

    Returns list of dicts with keys:
    subject_name, subject_key, driver_title, driver_desc, news_source, event_time, pct_chg
    """
    print("[EXTRACT] Driver events from 新事件 tab ...")
    # Navigate to home
    cdp.navigate("/")

    # Click the "新事件" tab
    cdp.evaluate("""
    (function() {
        var all = document.querySelectorAll('*');
        for (var i = 0; i < all.length; i++) {
            if (all[i].textContent.trim() === '新事件' && all[i].children.length === 0) {
                all[i].click();
                return 'clicked';
            }
        }
        return 'not found';
    })()
    """)
    time.sleep(2)

    data = cdp.evaluate("""
    (function() {
        var text = document.body.innerText;
        var searchIdx = text.indexOf('搜索');
        var dateIdx = text.indexOf('2026-', searchIdx);
        if (dateIdx === -1) return JSON.stringify({error: 'no event feed found'});

        var feedText = text.substring(dateIdx);
        var lines = feedText.split('\\n');
        var currentEvent = null;
        var results = [];

        // Extract the feed date
        var feedDate = '';
        for (var j = 0; j < Math.min(lines.length, 5); j++) {
            if (lines[j].includes('2026-') && (lines[j].includes('星期') || lines[j].includes('周'))) {
                feedDate = lines[j].trim();
                break;
            }
        }

        for (var i = 0; i < lines.length; i++) {
            var line = lines[i].trim();
            if (!line) continue;

            // Time pattern: HH:MM
            if (/^\\d{2}:\\d{2}$/.test(line)) {
                if (currentEvent && currentEvent.subject_name) {
                    results.push(currentEvent);
                }
                currentEvent = {time: line};
            } else if (currentEvent && !currentEvent.subject_name && line.length > 1 &&
                       !line.includes('%') && !line.includes('驱动') &&
                       !line.includes('2026') && !line.includes('星期')) {
                currentEvent.subject_name = line;
            } else if (currentEvent && currentEvent.subject_name && !currentEvent.pct &&
                       line.match(/^[+-]?\\d+\\.?\\d*%$/)) {
                currentEvent.pct = line;
            } else if (currentEvent && currentEvent.subject_name &&
                       line.startsWith('【驱动事件：')) {
                currentEvent.driver_title = line.replace('【驱动事件：', '').replace('】', '');
            } else if (currentEvent && currentEvent.driver_title && !currentEvent.driver_desc &&
                       line.length > 20 && !line.startsWith('【') && !line.includes('新闻来源')) {
                currentEvent.driver_desc = line;
            } else if (currentEvent && currentEvent.driver_title &&
                       line.startsWith('（新闻来源：')) {
                currentEvent.news_source = line.replace('（新闻来源：', '').replace('）', '');
            }
        }
        if (currentEvent && currentEvent.subject_name) results.push(currentEvent);

        return JSON.stringify({events: results, feed_date: feedDate});
    })()
    """)
    result = json.loads(data) if isinstance(data, str) else (data or {})
    events = result.get("events", [])
    feed_date = result.get("feed_date", "")

    print(f"  -> Feed date: {feed_date}, {len(events)} events")

    # Map subject names to keys
    enriched = []
    for e in events:
        name = e.get("subject_name", "")
        sk = subject_map.get(name, "")
        if not sk:
            for sname, ssid in subject_map.items():
                if name in sname or sname in name:
                    sk = ssid
                    break
        enriched.append({
            "subject_name": name,
            "subject_key": sk or name,
            "driver_title": e.get("driver_title", ""),
            "driver_desc": e.get("driver_desc", ""),
            "news_source": e.get("news_source", ""),
            "event_time": e.get("time", ""),
            "pct_chg": float((e.get("pct") or "0%").replace("%", "").replace("+", "")) if e.get("pct") else 0,
            "feed_date": feed_date,
        })

    for ev in enriched[:3]:
        print(f"     {ev['event_time']} {ev['subject_name']}: {ev['driver_title'][:60]}")
    return enriched


def extract_child_stock_reasons(cdp: CDPClient, subject_id: str) -> list[dict]:
    """Extract children hierarchy with per-stock reasons from subject detail page.

    Navigates to /subject/detail/:id and parses the children sections.
    Each child (参股/合作/...) contains stocks with 入选理由 (e.g., "持股第7").

    Returns list of dicts with keys:
      subject_key, child_name, child_full_name, stock_id, stock_name, reason, sort_order
    """
    print(f"  [CHILD-STOCK] Subject {subject_id} ...")
    cdp.navigate(f"/subject/detail/{subject_id}")

    data = cdp.evaluate(f"""
    (function() {{
        var text = document.body.innerText;
        var results = [];
        var parentSubjectId = '{subject_id}';

        // Find children sections: JYHF app displays children as sections
        // Pattern: "child_name (N只)" then stock list with reasons
        // Look for known child types: 参股, 合作, 供应商, 竞争对手, etc.
        var childTypes = ['参股', '合作', '供应商', '客户', '竞争对手', '合作伙伴', '关联方', '子公司', '母公司'];

        // Split text by common child section headers
        var lines = text.split('\\n');
        var currentChild = null;
        var inStockSection = false;
        var stockEntries = [];

        for (var i = 0; i < lines.length; i++) {{
            var line = lines[i].trim();
            if (!line) continue;

            // Check if this line starts a new child section
            var foundChild = false;
            for (var c = 0; c < childTypes.length; c++) {{
                if (line.startsWith(childTypes[c]) && line.length < 30) {{
                    // Save previous child's stocks
                    if (currentChild && stockEntries.length > 0) {{
                        for (var s = 0; s < stockEntries.length; s++) {{
                            results.push({{
                                subject_key: parentSubjectId,
                                child_name: currentChild,
                                child_full_name: parentSubjectId + '-' + currentChild,
                                stock_id: stockEntries[s].stock_id || '',
                                stock_name: stockEntries[s].stock_name || '',
                                reason: stockEntries[s].reason || '',
                                sort_order: s + 1
                            }});
                        }}
                    }}
                    // Start new child
                    currentChild = childTypes[c];
                    stockEntries = [];
                    inStockSection = true;
                    foundChild = true;
                    break;
                }}
            }}
            if (foundChild) continue;

            // Parse stock entry lines: typically "stock_name stock_id reason" or "stock_name reason"
            if (inStockSection && currentChild) {{
                // Stock code pattern: 6 digits
                var stockIdMatch = line.match(/(\\d{{6}})/);
                var reasonMatch = line.match(/[（(]([^）)]+)[）)]/);

                if (stockIdMatch || (line.length > 4 && line.length < 80)) {{
                    var entry = {{
                        stock_id: stockIdMatch ? stockIdMatch[1] : '',
                        stock_name: '',
                        reason: reasonMatch ? reasonMatch[1] : ''
                    }};

                    // Stock name is the part before the stock ID or the whole line if no ID
                    if (stockIdMatch) {{
                        var beforeId = line.substring(0, line.indexOf(stockIdMatch[1])).trim();
                        entry.stock_name = beforeId || line.substring(0, 20).trim();
                    }} else {{
                        // No stock ID found - might be name only
                        entry.stock_name = line.substring(0, 30).trim();
                    }}

                    // If no reason in parentheses, use the rest of the line
                    if (!entry.reason && stockIdMatch) {{
                        var afterId = line.substring(line.indexOf(stockIdMatch[1]) + 6).trim();
                        if (afterId && afterId.length > 1 && afterId.length < 60) {{
                            entry.reason = afterId;
                        }}
                    }}

                    stockEntries.push(entry);
                }}
            }}
        }}

        // Save last child's stocks
        if (currentChild && stockEntries.length > 0) {{
            for (var s = 0; s < stockEntries.length; s++) {{
                results.push({{
                    subject_key: parentSubjectId,
                    child_name: currentChild,
                    child_full_name: parentSubjectId + '-' + currentChild,
                    stock_id: stockEntries[s].stock_id || '',
                    stock_name: stockEntries[s].stock_name || '',
                    reason: stockEntries[s].reason || '',
                    sort_order: s + 1
                }});
            }}
        }}

        return JSON.stringify({{results: results, raw_text_preview: text.substring(0, 500)}});
    }})()
    """)
    result = json.loads(data) if isinstance(data, str) else (data or {})
    items = result.get("results", []) if isinstance(result, dict) else []
    raw_preview = result.get("raw_text_preview", "") if isinstance(result, dict) else ""
    print(f"  -> Extracted {len(items)} child-stock reasons (preview: {raw_preview[:120]})")
    for item in items[:5]:
        print(f"     [{item['child_name']}] {item['stock_id']} {item['stock_name']}: {item['reason'][:80]}")
    return items


def extract_subject_detail(cdp: CDPClient, subject_id: str) -> dict | None:
    """Extract subject detail data including pct_chg and stock list.

    Navigates to /subject/detail/:id page and parses the displayed data.
    """
    print(f"  [DETAIL] Subject {subject_id} ...")
    cdp.navigate(f"/subject/detail/{subject_id}")

    data = cdp.evaluate(f"""
    (function() {{
        var body = document.body.innerText;
        // Extract percentage change: look for "+X.XX%" or "-X.XX%" near subject name
        var pctMatch = body.match(/([+-]?\\d+\\.?\\d*)%/);
        var pctChg = pctMatch ? parseFloat(pctMatch[1]) : 0;

        // Try to find the subject name at the top of the detail
        var lines = body.split('\\n');
        var subjectName = '';
        for (var i = 0; i < Math.min(lines.length, 50); i++) {{
            var l = lines[i].trim();
            if (l.length > 2 && l.length < 30 && !l.includes('久赢') && !l.includes('行情') && !l.includes('题材') && !l.includes('返回') && !l.includes('甄选')) {{
                subjectName = l;
                break;
            }}
        }}

        return JSON.stringify({{
            subject_id: '{subject_id}',
            subject_name: subjectName,
            pct_chg: pctChg
        }});
    }})()
    """)
    detail = json.loads(data) if isinstance(data, str) else data
    return detail


# ── Data Export ─────────────────────────────────────────────

def save_to_jsonl(rows: list[dict], file_path: Path) -> int:
    """Save rows as JSONL file, one JSON object per line."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(rows)


def save_manifest(batch_id: str, subject_count: int, file_count: int) -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "batch_id": batch_id,
        "timestamp": datetime.now().isoformat(),
        "subject_count": subject_count,
        "file_count": file_count,
        "source": "cdp_jyhf_collector",
    }
    path = MANIFEST_DIR / f"{batch_id}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"[MANIFEST] {path}")


async def import_rows_to_db(rows: list[dict], batch_id: str) -> tuple[int, int, int]:
    """Persist collected JYHF daily rows without writing JSONL intermediates."""
    if not rows:
        return 0, 0, 0
    from database_service.managers.postgres_manager import PostgresDatabaseManager

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_jyhf_history_tables(manager)
        await ensure_event_theme_columns(manager)
        subject_keys = sorted(
            {
                str(row.get("subject_key") or row.get("subjectId") or "").strip()
                for row in rows
                if str(row.get("subject_key") or row.get("subjectId") or "").strip()
            }
        )
        await ensure_jyhf_theme_master_rows(manager, subject_keys)
        history_count, rank_count, subject_keys = await sync_jyhf_history_records(
            manager,
            rows,
            batch_id,
            mode="append",
        )
        return history_count, rank_count, len(subject_keys)
    finally:
        await manager.disconnect()


async def get_existing_db_counts(target_date: str) -> dict[str, int]:
    """Return existing JYHF daily rows for a trade date, checking DB only."""
    from database_service.managers.postgres_manager import PostgresDatabaseManager

    trade_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        async with manager.pool.acquire() as conn:
            rank_exists = await conn.fetchval("SELECT to_regclass('public.subject_rank_daily') IS NOT NULL")
            history_exists = await conn.fetchval("SELECT to_regclass('public.subject_history_staging') IS NOT NULL")
            rank_count = 0
            history_count = 0
            if rank_exists:
                rank_count = int(
                    await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM subject_rank_daily
                        WHERE rank_date = $1::date
                          AND source_system = 'jyhf'
                        """,
                        trade_date,
                    )
                    or 0
                )
            if history_exists:
                history_count = int(
                    await conn.fetchval(
                        """
                        SELECT COUNT(*)
                        FROM subject_history_staging
                        WHERE rank_date = $1::date
                          AND source_type IN ('jyhf_history', 'jyhf_rank_daily')
                        """,
                        trade_date,
                    )
                    or 0
                )
            return {"rank_rows": rank_count, "history_rows": history_count}
    finally:
        await manager.disconnect()


# ── Main ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="CDP-based JYHF data collector")
    parser.add_argument("--date", required=True, help="Target trade date (YYYY-MM-DD)")
    parser.add_argument("--import-db", action="store_true", help="Import collected data into DB")
    parser.add_argument("--export-jsonl", action="store_true", help="Also export collected rows to legacy JSONL files")
    parser.add_argument("--force", action="store_true", help="Re-collect even when DB already has rows for --date")
    parser.add_argument("--skip-launch", action="store_true", help="Skip app launch (assume already running)")
    args = parser.parse_args()
    if not args.import_db and not args.export_jsonl:
        args.import_db = True

    target_date = args.date
    batch_id = f"cdp_jyhf_{target_date.replace('-', '')}"

    if args.import_db and not args.force:
        existing_counts = asyncio.run(get_existing_db_counts(target_date))
        if existing_counts["rank_rows"] > 0 or existing_counts["history_rows"] > 0:
            print(
                f"[SKIP] DB already has JYHF data for {target_date}: "
                f"rank_rows={existing_counts['rank_rows']} "
                f"history_rows={existing_counts['history_rows']}. "
                "Use --force to re-collect."
            )
            return

    # Step 1: Ensure app is running
    if not args.skip_launch:
        ensure_app_running()

    # Step 2: Connect via CDP
    cdp = CDPClient()
    try:
        cdp.connect()
        print(f"[CDP] Connected to JYHF app")

        # Step 3: Extract subject ranking data
        rankings = extract_subject_ranking(cdp)

        # Step 4: Extract daily subject appearances
        daily = extract_daily_subjects(cdp, target_date)

        # Step 5: Build subject_id mapping from known subject list
        # Load subject list from existing data
        list_file = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl"
        subject_map: dict[str, str] = {}  # name -> subject_id
        if list_file.exists():
            with open(list_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line.strip())
                        sid = str(obj.get("subjectId", ""))
                        name = str(obj.get("name", ""))
                        if sid and name:
                            subject_map[name] = sid
                    except json.JSONDecodeError:
                        continue
            print(f"[MAP] Loaded {len(subject_map)} subject name->id mappings")

        # Step 5.5: Extract driver events (only for current day / most recent)
        driver_events = extract_driver_events(cdp, subject_map)
        # Build a lookup: subject_name -> driver description
        driver_map: dict[str, str] = {}
        for ev in driver_events:
            name = ev["subject_name"]
            desc = ev["driver_desc"] or ev["driver_title"]
            if name and desc and name not in driver_map:
                driver_map[name] = f"【驱动事件：{ev['driver_title']}】{desc}"

        # Step 6: Transform rankings into subject_rank_daily format (enriched with driver events)
        rank_rows = []
        for item in rankings:
            name = item["subject_name"]
            sid = subject_map.get(name, "")
            if not sid:
                # Try partial match
                for sname, ssid in subject_map.items():
                    if name in sname or sname in name:
                        sid = ssid
                        break
            # Use driver event description if available, otherwise fallback
            desc = driver_map.get(name, "")
            if not desc:
                # Try partial name match
                for dname, ddesc in driver_map.items():
                    if name in dname or dname in name:
                        desc = ddesc
                        break
            if not desc:
                desc = f"入选次数(十日): {item['appearance_count_10d']}次"

            rank_rows.append({
                "subject_key": sid or name,
                "subject_name": name,
                "rank_date": target_date,
                "pct_chg": item["pct_chg"],
                "heat": item["appearance_count_10d"],
                "heat_name": "热" if item["appearance_count_10d"] >= 2 else "温",
                "description": desc,
                "source_type": "jyhf_rank_daily",
                "source_system": "jyhf",
                "batch_id": batch_id,
            })

        # Step 7: Transform daily data into subject_history_staging format
        history_rows = []
        for item in daily:
            name = item["subject_name"]
            sid = subject_map.get(name, "")
            if not sid:
                for sname, ssid in subject_map.items():
                    if name in sname or sname in name:
                        sid = ssid
                        break
            history_rows.append({
                "subject_key": sid or name,
                "subject_name": name,
                "rank_date": target_date,
                "description": f"入选 {item['appearance_count']} 次",
                "heat": item["appearance_count"],
                "heat_name": "热" if item["appearance_count"] >= 3 else "温",
                "pct_chg": 0,  # Will be updated from ranking data
                "his_pct_chg": 0,
                "source_type": "jyhf_history",
                "source_system": "jyhf",
                "batch_id": batch_id,
            })

        # Put rank rows last so subject_rank_daily keeps the richer pct/driver data
        # when the same subject/date is also present in history rows.
        collected_rows = history_rows + rank_rows

        # Step 8: Persist directly to DB when requested; JSONL is optional.
        imported_history_rows = 0
        imported_rank_rows = 0
        imported_subjects = 0
        if args.import_db and collected_rows:
            print("\n[IMPORT] Writing collected rows directly to database...")
            imported_history_rows, imported_rank_rows, imported_subjects = asyncio.run(
                import_rows_to_db(collected_rows, batch_id)
            )
            print(
                f"[IMPORT] DB write complete: subjects={imported_subjects} "
                f"history_rows={imported_history_rows} rank_rows={imported_rank_rows}"
            )

        # Step 9: Optional legacy JSONL export for diagnostics/backfill.
        file_count = 0
        if args.export_jsonl and rank_rows:
            today_rank = DAILY_DIR / f"combined_{target_date.replace('-', '')}_daily.jsonl"
            count = save_to_jsonl(rank_rows, today_rank)
            print(f"[SAVE] {count} rank rows -> {today_rank}")
            file_count += 1

        # Save per-subject history files
        if args.export_jsonl and history_rows:
            from collections import defaultdict
            by_subject: dict[str, list] = defaultdict(list)
            for row in history_rows:
                sk = row["subject_key"]
                if sk and sk.isdigit():
                    by_subject[sk].append(row)

            for sk, rows in by_subject.items():
                # Append to existing history file
                hist_path = HISTORY_DIR / f"{sk}_history.jsonl"
                existing = []
                if hist_path.exists():
                    with open(hist_path, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                existing.append(json.loads(line.strip()))
                            except json.JSONDecodeError:
                                continue
                # Merge: only add new entries (not duplicates by rank_date + description)
                existing_keys = {
                    (e.get("rank_date", ""), e.get("description", ""))
                    for e in existing
                }
                new_rows = [
                    r for r in rows
                    if (r["rank_date"], r["description"]) not in existing_keys
                ]
                if new_rows:
                    all_rows = existing + new_rows
                    save_to_jsonl(all_rows, hist_path)
                    file_count += 1
            print(f"[SAVE] History rows for {len(by_subject)} subjects, {file_count} files updated")

        # Step 10: Save manifest only when an artifact was produced.
        if args.export_jsonl:
            save_manifest(batch_id, len(collected_rows), file_count)

    finally:
        cdp.close()

    print(f"\n[DONE] Collection complete for {target_date}")
    print(f"  Rank rows: {len(rank_rows)}")
    print(f"  History rows: {len(history_rows)}")
    print(f"  Files updated: {file_count}")
    print(f"  Batch ID: {batch_id}")


if __name__ == "__main__":
    main()

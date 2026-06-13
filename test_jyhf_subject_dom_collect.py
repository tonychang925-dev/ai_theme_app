#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from cdp_jyhf_collector import CDPClient, ensure_app_running


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tmp" / "jyhf_subject_dom_test"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test for one JYHF subject DOM collection")
    parser.add_argument("--subject-id", required=True, help="JYHF subject id")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory to write snapshots and report",
    )
    parser.add_argument(
        "--tabs",
        default="题材介绍,题材排名,题材图谱",
        help="Comma-separated tab labels to try to click in order",
    )
    parser.add_argument(
        "--route",
        default=None,
        help="Override subject route. Default: /subject/detail/{subject-id}",
    )
    return parser.parse_args()


def _js_click_text(text: str) -> str:
    safe_text = json.dumps(text, ensure_ascii=False)
    return f"""
    (function() {{
        var targetText = {safe_text};
        var candidates = Array.from(document.querySelectorAll('span,div,a,button,label'));
        var exact = [];
        var fuzzy = [];
        for (var i = 0; i < candidates.length; i++) {{
            var el = candidates[i];
            if (!el || !el.offsetParent) continue;
            var txt = (el.textContent || '').trim().replace(/\\s+/g, ' ');
            if (!txt) continue;
            if (txt === targetText) {{
                exact.push(el);
                continue;
            }}
            if (txt.indexOf(targetText) >= 0 && txt.length <= Math.max(24, targetText.length + 6)) {{
                fuzzy.push(el);
            }}
        }}
        function pick(list) {{
            if (!list.length) return null;
            list.sort(function(a, b) {{
                return ((a.textContent || '').trim().length - (b.textContent || '').trim().length);
            }});
            return list[0];
        }}
        var best = pick(exact) || pick(fuzzy);
        if (best && typeof best.click === 'function') {{
            best.click();
            return 'clicked:' + (best.textContent || '').trim().slice(0, 80);
        }}
        return 'not_found';
    }})()
    """


def _js_collect_candidates(limit: int = 80) -> str:
    return f"""
    (function() {{
        var items = [];
        var seen = new Set();
        var all = Array.from(document.querySelectorAll('*'));
        for (var i = 0; i < all.length; i++) {{
            var el = all[i];
            if (!el || !el.offsetParent) continue;
            var txt = (el.textContent || '').trim().replace(/\\s+/g, ' ');
            if (!txt || txt.length > 24) continue;
            if (txt.length < 2) continue;
            if (seen.has(txt)) continue;
            seen.add(txt);
            items.push(txt);
            if (items.length >= {int(limit)}) break;
        }}
        return JSON.stringify(items);
    }})()
    """


def _js_capture_body(limit: int = 12000) -> str:
    return f"""
    (function() {{
        var title = document.title || '';
        var hash = window.location.hash || '';
        var href = window.location.href || '';
        var text = document.body ? (document.body.innerText || '') : '';
        var html = document.body ? (document.body.innerHTML || '') : '';
        var tabs = Array.from(document.querySelectorAll('*'))
            .map(function(el) {{ return (el.textContent || '').trim(); }})
            .filter(function(t) {{ return t && t.length <= 24; }});
        return JSON.stringify({{
            title: title,
            hash: hash,
            href: href,
            body_text: text.substring(0, {int(limit)}),
            body_html: html.substring(0, {int(limit)}),
            visible_labels: Array.from(new Set(tabs)).slice(0, 80)
        }});
    }})()
    """


def _poll_for_text(cdp: CDPClient, keywords: list[str], timeout_s: float = 10.0) -> str:
    deadline = time.time() + timeout_s
    last = ""
    while time.time() < deadline:
        try:
            body = cdp.evaluate("document.body ? document.body.innerText : ''", timeout=2.0) or ""
            last = str(body)
            if any(k in last for k in keywords):
                return last
        except Exception:
            pass
        time.sleep(0.4)
    return last


def _capture_snapshot(cdp: CDPClient, subject_id: str, label: str, out_dir: Path) -> dict:
    raw = cdp.evaluate(_js_capture_body(), timeout=8.0)
    payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
    payload["subject_id"] = subject_id
    payload["label"] = label
    payload["captured_at"] = datetime.now().isoformat(timespec="seconds")

    out_path = out_dir / f"{subject_id}_{label}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    args = parse_args()
    subject_id = str(args.subject_id).strip()
    if not subject_id:
        print("[ERROR] missing subject-id")
        return 1

    route = args.route or f"/subject/detail/{subject_id}"
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[START] subject_id={subject_id}")
    print(f"[START] route={route}")
    ensure_app_running()

    cdp = CDPClient()
    try:
        cdp.connect()
        print("[OK] CDP connected")

        cdp.navigate(route)
        time.sleep(2.5)

        initial = _capture_snapshot(cdp, subject_id, "initial", out_dir)
        print(f"[INFO] initial title={initial.get('title', '')!r}")
        print(f"[INFO] initial visible_labels={len(initial.get('visible_labels') or [])}")

        candidates = json.loads(cdp.evaluate(_js_collect_candidates(), timeout=8.0) or "[]")
        candidate_path = out_dir / f"{subject_id}_candidates.json"
        candidate_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[SAVE] candidates -> {candidate_path}")

        tabs = [t.strip() for t in str(args.tabs).split(",") if t.strip()]
        results: list[dict] = []
        for tab in tabs:
            click_result = cdp.evaluate(_js_click_text(tab), timeout=8.0)
            print(f"[TAB] {tab} -> {click_result}")
            time.sleep(1.2)
            body = _poll_for_text(cdp, [tab, "详情", "历史", "图谱", "股票"], timeout_s=8.0)
            snapshot = _capture_snapshot(cdp, subject_id, tab, out_dir)
            snapshot["body_text_hit"] = any(k in body for k in [tab, "详情", "历史", "图谱", "股票"])
            results.append(
                {
                    "tab": tab,
                    "click_result": str(click_result),
                    "snapshot_file": str(out_dir / f"{subject_id}_{tab}.json"),
                    "body_hit": snapshot["body_text_hit"],
                    "visible_labels": snapshot.get("visible_labels", []),
                }
            )

        report = {
            "subject_id": subject_id,
            "route": route,
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "output_dir": str(out_dir),
            "initial_snapshot": str(out_dir / f"{subject_id}_initial.json"),
            "tabs": results,
        }
        report_path = out_dir / f"{subject_id}_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[SAVE] report -> {report_path}")
        print("[DONE] smoke test finished")
        return 0
    finally:
        try:
            cdp.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from cdp_jyhf_collector import CDPClient, ensure_app_running


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "tmp" / "jyhf_subject_dom_collect"
STANDARD_DETAILS_DIR = PROJECT_ROOT / "theme_data_complete" / "details"
STANDARD_HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect one JYHF subject from DOM")
    parser.add_argument("--subject-id", required=True, help="JYHF subject id")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="Directory to write snapshots and parsed files",
    )
    parser.add_argument(
        "--write-standard",
        action="store_true",
        help="Also write files into theme_data_complete/details and history",
    )
    parser.add_argument(
        "--route",
        default=None,
        help="Override route. Default: /subject/detail/{subject-id}",
    )
    return parser.parse_args()


def _clean_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return lines


def _safe_subject_name_from_title(title: str) -> str:
    m = re.search(r"题材掘金\s+(.+?)详情", title or "")
    return m.group(1).strip() if m else ""


def _today_from_text(text: str) -> str:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text or "")
    if m:
        return m.group(1)
    return datetime.now().strftime("%Y-%m-%d")


def _synthetic_rank_id(subject_id: str, rank_date: str, event_time: str, subject_name: str, driver_title: str) -> int:
    raw = "|".join([subject_id, rank_date, event_time, subject_name, driver_title])
    digest = int(hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16], 16)
    return int(rank_date.replace("-", "")) * 1_000_000_000 + digest % 1_000_000_000


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


def _js_capture_snapshot(limit: int = 16000) -> str:
    return f"""
    (function() {{
        var title = document.title || '';
        var hash = window.location.hash || '';
        var href = window.location.href || '';
        var text = document.body ? (document.body.innerText || '') : '';
        var html = document.body ? (document.body.innerHTML || '') : '';
        var labels = Array.from(document.querySelectorAll('*'))
            .map(function(el) {{ return (el.textContent || '').trim(); }})
            .filter(function(t) {{ return t && t.length <= 24; }});
        return JSON.stringify({{
            title: title,
            hash: hash,
            href: href,
            body_text: text.substring(0, {int(limit)}),
            body_html: html.substring(0, {int(limit)}),
            visible_labels: Array.from(new Set(labels)).slice(0, 100)
        }});
    }})()
    """


def _click_and_wait(cdp: CDPClient, label: str, wait_s: float = 1.2) -> str:
    try:
        result = cdp.evaluate(_js_click_text(label), timeout=8.0)
    except Exception as exc:
        return f"error:{exc}"
    time.sleep(wait_s)
    return str(result)


def _capture_snapshot(cdp: CDPClient, subject_id: str, label: str, out_dir: Path) -> dict[str, Any]:
    raw = cdp.evaluate(_js_capture_snapshot(), timeout=10.0)
    payload = json.loads(raw) if isinstance(raw, str) else (raw or {})
    payload["subject_id"] = subject_id
    payload["label"] = label
    payload["captured_at"] = datetime.now().isoformat(timespec="seconds")
    out_path = out_dir / f"{subject_id}_{label}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def _find_section(text: str, start_markers: list[str], end_markers: list[str]) -> str:
    start_idx = -1
    for marker in start_markers:
        idx = text.find(marker)
        if idx >= 0 and (start_idx < 0 or idx < start_idx):
            start_idx = idx
    if start_idx < 0:
        start_idx = 0
    end_idx = len(text)
    for marker in end_markers:
        idx = text.find(marker, start_idx + 1)
        if idx >= 0:
            end_idx = min(end_idx, idx)
    return text[start_idx:end_idx]


def _is_pct_line(text: str) -> bool:
    return bool(re.fullmatch(r"[+-]?\d+(?:\.\d+)?%", str(text or "").strip()))


def _parse_relation_items(
    snapshot: dict[str, Any],
    subject_id: str,
    source_type: str,
) -> list[dict[str, Any]]:
    text = str(snapshot.get("body_text") or "")
    lines = _clean_lines(text)
    rows: list[dict[str, Any]] = []
    current_section = ""
    current_rank = 0
    skip_lines = {
        "题材掘金",
        "题材轮动",
        "题材排名",
        "题材图谱",
        "题材介绍",
        "按涨幅",
        "上一天",
        "下一天",
        "一键展开",
        "软件局限性说明",
        "日线",
        "周线",
        "月线",
        "搜索",
        "返回",
        "全部A股",
        "市场走势",
        "自选股",
        "全部题材",
        "全部",
    }
    start_index = 0
    for marker in ("题材排名", "题材图谱", "题材介绍", "按涨幅", "一键展开"):
        for idx, line in enumerate(lines):
            if line == marker:
                start_index = max(start_index, idx)
                break
    lines = lines[start_index:]
    for i, line in enumerate(lines):
        if line in {"情绪", "行业"}:
            current_section = line
            continue
        if line in skip_lines:
            continue
        if not re.search(r"[\u4e00-\u9fff]", line):
            continue
        if _is_pct_line(line):
            continue
        if i + 1 >= len(lines) or not _is_pct_line(lines[i + 1]):
            continue
        name = line
        pct_text = lines[i + 1]
        reason = ""
        if i + 2 < len(lines):
            next_line = lines[i + 2]
            if (
                next_line
                and next_line not in skip_lines
                and next_line not in {"情绪", "行业"}
                and not _is_pct_line(next_line)
            ):
                reason = next_line
        current_rank += 1
        rows.append(
            {
                "subjectId": int(subject_id) if str(subject_id).isdigit() else subject_id,
                "subject_key": str(subject_id),
                "rank": current_rank,
                "subjectName": name,
                "category": current_section,
                "reason": reason,
                "pctChg": float(pct_text.replace("%", "").replace("+", "").strip() or 0),
                "pct_chg": float(pct_text.replace("%", "").replace("+", "").strip() or 0),
                "source_type": source_type,
                "source_system": "jyhf",
                "captured_at": snapshot.get("captured_at"),
            }
        )
    return rows


def parse_detail_record(snapshot: dict[str, Any], subject_id: str) -> dict[str, Any]:
    title = str(snapshot.get("title") or "")
    body_text = str(snapshot.get("body_text") or "")
    body_html = str(snapshot.get("body_html") or "")
    subject_name = _safe_subject_name_from_title(title) or str(subject_id)
    detail_text = _find_section(
        body_text,
        start_markers=[f"题材掘金 {subject_name}详情", "题材掘金"],
        end_markers=["全部题材动态", "情报", "日线周线月线", "软件局限性说明"],
    ).strip()
    reason = ""
    lines = _clean_lines(detail_text)
    for line in lines:
        if line.startswith(subject_name) and len(line) <= 100:
            reason = line
            break
        if "（" in line and "）" in line and len(line) <= 100:
            reason = line
            break

    return {
        "ancestors": None,
        "bizKey": str(subject_id),
        "createBy": None,
        "createTime": snapshot.get("captured_at"),
        "detail": detail_text or body_text,
        "detail_html": body_html,
        "firstLetter": None,
        "imgUrl": "",
        "importance": None,
        "level": None,
        "limitUpTimes": None,
        "name": subject_name,
        "parentId": None,
        "pctChg": None,
        "reason": reason,
        "remark": "dom_collected",
        "sort": None,
        "status": "1",
        "subjectId": int(subject_id) if str(subject_id).isdigit() else subject_id,
        "subject_key": str(subject_id),
        "type": 1,
        "updateBy": None,
        "updateTime": snapshot.get("captured_at"),
        "source_type": "jyhf_dom_detail",
    }


def parse_ranking_rows(snapshot: dict[str, Any], subject_id: str) -> list[dict[str, Any]]:
    return _parse_relation_items(snapshot, subject_id, "jyhf_dom_rank")


def parse_history_rows(snapshot: dict[str, Any], subject_id: str) -> list[dict[str, Any]]:
    relation_rows = _parse_relation_items(snapshot, subject_id, "jyhf_dom_history")
    feed_date = _today_from_text(str(snapshot.get("body_text") or ""))
    rank_date = f"{feed_date} 00:00:00" if re.fullmatch(r"\d{4}-\d{2}-\d{2}", feed_date) else feed_date
    rows: list[dict[str, Any]] = []
    for idx, item in enumerate(relation_rows, start=1):
        subject_name = str(item.get("subjectName") or "").strip()
        if not subject_name:
            continue
        pct_val = float(item.get("pctChg") or 0)
        description = str(item.get("reason") or "").strip()
        if description:
            description = f"【驱动事件：{subject_name}】\n\n{description}"
        else:
            description = f"【驱动事件：{subject_name}】"
        rows.append(
            {
                "ancestors": "0",
                "bizKey": None,
                "createBy": None,
                "createTime": snapshot.get("captured_at"),
                "description": description,
                "firstSubjectId": None,
                "firstSubjectName": None,
                "heat": 1,
                "heatName": item.get("category") or "热",
                "hisPctChg": pct_val,
                "imgUrl": "",
                "pctChg": pct_val,
                "rankDate": rank_date,
                "red": 0,
                "secondSubjectId": None,
                "secondSubjectName": None,
                "sort": idx,
                "subjectId": int(subject_id) if str(subject_id).isdigit() else subject_id,
                "subjectName": subject_name,
                "subjectRankId": _synthetic_rank_id(
                    subject_id,
                    feed_date if re.fullmatch(r"\d{4}-\d{2}-\d{2}", feed_date) else datetime.now().strftime("%Y-%m-%d"),
                    str(item.get("category") or ""),
                    subject_name,
                    str(item.get("reason") or ""),
                ),
                "type": 3,
                "updateBy": None,
                "updateTime": snapshot.get("captured_at"),
                "source_type": "jyhf_dom_history",
                "source_system": "jyhf",
                "event_time": None,
                "subject_key": str(subject_id),
            }
        )
    return rows


def extract_tree_nodes(snapshot: dict[str, Any], subject_id: str) -> list[dict[str, Any]]:
    rows = _parse_relation_items(snapshot, subject_id, "jyhf_dom_tree")
    nodes: list[dict[str, Any]] = []
    for idx, item in enumerate(rows, start=1):
        nodes.append(
            {
                "name": item.get("subjectName"),
                "level": 1 if idx == 1 else 2,
                "reason": item.get("reason") or "",
                "pct_chg": f"{item.get('pctChg'):+.2f}%",
                "has_children": idx == 1,
                "is_stock": idx > 1,
                "category": item.get("category") or "",
                "parent_name": rows[0]["subjectName"] if rows and idx > 1 else "",
                "parent_chain": [rows[0]["subjectName"]] if rows and idx > 1 else [],
            }
        )
    return nodes


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    subject_id = str(args.subject_id).strip()
    out_root = Path(args.output_dir)
    subject_dir = out_root / subject_id
    subject_dir.mkdir(parents=True, exist_ok=True)

    route = args.route or f"/subject/detail/{subject_id}"
    print(f"[START] subject_id={subject_id}")
    print(f"[START] route={route}")
    ensure_app_running()

    cdp = CDPClient()
    try:
        cdp.connect()
        print("[OK] CDP connected")
        cdp.navigate(route)
        time.sleep(2.5)

        initial = _capture_snapshot(cdp, subject_id, "initial", subject_dir)
        print(f"[INFO] hash={initial.get('hash')!r} title={initial.get('title')!r}")

        detail_click = _click_and_wait(cdp, "题材介绍", wait_s=1.2)
        print(f"[TAB] 题材介绍 -> {detail_click}")
        time.sleep(0.8)
        detail_snapshot = _capture_snapshot(cdp, subject_id, "detail", subject_dir)

        ranking_click = _click_and_wait(cdp, "题材排名", wait_s=1.2)
        print(f"[TAB] 题材排名 -> {ranking_click}")
        time.sleep(0.8)
        ranking_snapshot = _capture_snapshot(cdp, subject_id, "ranking", subject_dir)

        graph_click = _click_and_wait(cdp, "题材图谱", wait_s=1.2)
        print(f"[TAB] 题材图谱 -> {graph_click}")
        time.sleep(0.8)
        graph_snapshot = _capture_snapshot(cdp, subject_id, "graph", subject_dir)
        detail_record = parse_detail_record(detail_snapshot if detail_snapshot else initial, subject_id)
        ranking_rows = parse_ranking_rows(ranking_snapshot if ranking_snapshot else initial, subject_id)
        history_rows = parse_history_rows(ranking_snapshot if ranking_snapshot else initial, subject_id)
        graph_nodes = extract_tree_nodes(graph_snapshot if graph_snapshot else initial, subject_id)
        graph_snapshot_path = subject_dir / f"{subject_id}_graph_snapshot.json"
        graph_snapshot_path.write_text(
            json.dumps(graph_snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        graph_payload = {
            "subject_id": subject_id,
            "subject_name": detail_record.get("name"),
            "clicked": graph_click,
            "snapshot": graph_snapshot,
            "nodes": graph_nodes,
        }
        (subject_dir / f"{subject_id}_graph.json").write_text(
            json.dumps(graph_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Write parsed outputs.
        write_jsonl(subject_dir / f"{subject_id}_details.jsonl", [detail_record])
        write_jsonl(subject_dir / f"{subject_id}_history.jsonl", history_rows)
        write_jsonl(subject_dir / f"{subject_id}_ranking.jsonl", ranking_rows)
        (subject_dir / f"{subject_id}_manifest.json").write_text(
            json.dumps(
                {
                    "subject_id": subject_id,
                    "route": route,
                    "captured_at": datetime.now().isoformat(timespec="seconds"),
                    "files": {
                        "details": f"{subject_id}_details.jsonl",
                        "history": f"{subject_id}_history.jsonl",
                        "ranking": f"{subject_id}_ranking.jsonl",
                        "graph": f"{subject_id}_graph.json",
                        "graph_snapshot": f"{subject_id}_graph_snapshot.json",
                        "initial_snapshot": f"{subject_id}_initial.json",
                    },
                    "counts": {
                        "detail_rows": 1,
                        "history_rows": len(history_rows),
                        "ranking_rows": len(ranking_rows),
                        "graph_nodes": len(graph_nodes),
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if args.write_standard:
            write_jsonl(STANDARD_DETAILS_DIR / f"{subject_id}_details.jsonl", [detail_record])
            if history_rows:
                write_jsonl(STANDARD_HISTORY_DIR / f"{subject_id}_history.jsonl", history_rows)
            print("[WRITE] standard theme_data_complete/details & history updated")

        print(f"[DONE] output={subject_dir}")
        print(f"[DONE] detail_rows=1 history_rows={len(history_rows)} ranking_rows={len(ranking_rows)} graph_nodes={len(graph_nodes)}")
        return 0
    finally:
        try:
            cdp.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

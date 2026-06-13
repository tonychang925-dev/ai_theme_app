#!/usr/bin/env python3
"""
Scan missing JYHF data for DOM-based backfill.

Current scope:
  - history
  - details

What this script does:
  1. Reads the local subject list as the source of truth.
  2. Scans local `theme_data_complete/history` and `theme_data_complete/details`.
  3. Computes missing subject queues and latest local watermarks.
  4. Writes queue files under `theme_data_complete/_state/`.

What this script does not do:
  - It does not call the legacy API backfill path.
  - It does not attempt to collect `lists` or `stock_details`.
  - It does not implement the DOM extractor itself.

The goal is to produce a clean backlog for the DOM collector that will
handle subject detail / subject history capture.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parent
DATA_ROOT = PROJECT_ROOT / "theme_data_complete"
LIST_DIR = DATA_ROOT / "lists"
DETAIL_DIR = DATA_ROOT / "details"
HISTORY_DIR = DATA_ROOT / "history"
STATE_DIR = DATA_ROOT / "_state"

REPORT_PATH = STATE_DIR / "missing_data_report.json"
ALL_SUBJECTS_PATH = STATE_DIR / "all_subjects.txt"
MISSING_HISTORY_PATH = STATE_DIR / "missing_history_subjects.txt"
MISSING_DETAILS_PATH = STATE_DIR / "missing_details_subjects.txt"
MISSING_HISTORY_WATERMARK_PATH = STATE_DIR / "history_latest_watermark.txt"
MISSING_DETAILS_WATERMARK_PATH = STATE_DIR / "details_latest_watermark.txt"


def _read_jsonl_subject_ids(paths: Iterable[Path]) -> set[str]:
    subjects: set[str] = set()
    for path in paths:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            sid = obj.get("subjectId") or obj.get("subject_id") or obj.get("id") or obj.get("bizKey")
            if sid not in (None, ""):
                subjects.add(str(sid).strip())
    return {s for s in subjects if s}


def _load_subjects_from_lists() -> set[str]:
    if not LIST_DIR.exists():
        return set()
    preferred = LIST_DIR / "full_theme_list.sync.jsonl"
    if preferred.exists():
        return _read_jsonl_subject_ids([preferred])
    return _read_jsonl_subject_ids(sorted(LIST_DIR.glob("*.jsonl")))


def _history_subjects() -> set[str]:
    if not HISTORY_DIR.exists():
        return set()
    return {p.stem.replace("_history", "") for p in HISTORY_DIR.glob("*_history.jsonl")}


def _detail_subjects() -> set[str]:
    if not DETAIL_DIR.exists():
        return set()
    return {p.stem.replace("_details", "") for p in DETAIL_DIR.glob("*_details.jsonl")}


def _to_dt(value: Any) -> datetime | None:
    if value in (None, "", "null"):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.split("Z")[0], fmt)
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _latest_history_watermark() -> str | None:
    latest: datetime | None = None
    for path in HISTORY_DIR.glob("*_history.jsonl"):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            dt = _to_dt(obj.get("rankDate")) or _to_dt(obj.get("updateTime")) or _to_dt(obj.get("createTime"))
            if dt and (latest is None or dt > latest):
                latest = dt
    return latest.isoformat(sep=" ") if latest else None


def _latest_detail_watermark() -> str | None:
    latest: datetime | None = None
    for path in DETAIL_DIR.glob("*_details.jsonl"):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue
            dt = _to_dt(obj.get("updateTime")) or _to_dt(obj.get("createTime"))
            if dt and (latest is None or dt > latest):
                latest = dt
    return latest.isoformat(sep=" ") if latest else None


def _write_lines(path: Path, rows: Iterable[str]) -> int:
    items = sorted({str(x).strip() for x in rows if str(x).strip()})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(items) + ("\n" if items else ""), encoding="utf-8")
    return len(items)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan missing JYHF details/history for DOM backfill")
    parser.add_argument("--report-only", action="store_true", help="Only print the report, do not write queue files")
    parser.add_argument("--subject", action="append", help="Optional subject filter; can be repeated")
    parser.add_argument("--limit", type=int, default=0, help="Limit the output queues to N subjects")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    list_subjects = _load_subjects_from_lists()
    if args.subject:
        wanted = {str(x).strip() for x in args.subject if str(x).strip()}
        list_subjects &= wanted
    if args.limit and args.limit > 0:
        list_subjects = set(sorted(list_subjects)[: args.limit])

    history_subjects = _history_subjects()
    detail_subjects = _detail_subjects()

    missing_history = sorted(list_subjects - history_subjects)
    missing_details = sorted(list_subjects - detail_subjects)

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(),
        "source_subject_count": len(list_subjects),
        "history_subject_count": len(history_subjects),
        "detail_subject_count": len(detail_subjects),
        "missing_history_count": len(missing_history),
        "missing_details_count": len(missing_details),
        "missing_history_sample": missing_history[:50],
        "missing_details_sample": missing_details[:50],
        "history_latest_watermark": _latest_history_watermark(),
        "details_latest_watermark": _latest_detail_watermark(),
        "scope": ["history", "details"],
        "lists_skipped": True,
        "stock_details_skipped": True,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not args.report_only:
        _write_lines(ALL_SUBJECTS_PATH, list_subjects)
        _write_lines(MISSING_HISTORY_PATH, missing_history)
        _write_lines(MISSING_DETAILS_PATH, missing_details)
        if report["history_latest_watermark"]:
            MISSING_HISTORY_WATERMARK_PATH.write_text(
                str(report["history_latest_watermark"]) + "\n",
                encoding="utf-8",
            )
        if report["details_latest_watermark"]:
            MISSING_DETAILS_WATERMARK_PATH.write_text(
                str(report["details_latest_watermark"]) + "\n",
                encoding="utf-8",
            )
        print(f"[OK] {REPORT_PATH}")
        print(f"[OK] {ALL_SUBJECTS_PATH}")
        print(f"[OK] {MISSING_HISTORY_PATH}")
        print(f"[OK] {MISSING_DETAILS_PATH}")
        print(f"[OK] {MISSING_HISTORY_WATERMARK_PATH}")
        print(f"[OK] {MISSING_DETAILS_WATERMARK_PATH}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

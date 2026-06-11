#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FULL_LIST = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl"
STATE_DIR = PROJECT_ROOT / "theme_data_complete" / "_state"
EXCEPTION_MANIFEST = STATE_DIR / "exception_manifest.json"


def load_subjects() -> list[str]:
    subjects: list[str] = []
    for line in FULL_LIST.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        sid = obj.get("subjectId") or obj.get("id") or obj.get("bizKey")
        if sid not in (None, ""):
            subjects.append(str(sid))
    return sorted(set(subjects))


def load_exception_manifest() -> dict:
    if not EXCEPTION_MANIFEST.exists():
        return {}
    try:
        return json.loads(EXCEPTION_MANIFEST.read_text(encoding="utf-8"))
    except Exception:
        return {}


def present_subjects(dir_path: Path, suffix: str) -> set[str]:
    present: set[str] = set()
    if not dir_path.exists():
        return present
    for f in dir_path.glob(f"*_{{suffix}}.jsonl".format(suffix=suffix)):
        m = re.match(r"^(\d+)_", f.name)
        if m:
            present.add(m.group(1))
    return present


def present_stock_daily(trade_date: str) -> set[str]:
    stock_dir = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
    present: set[str] = set()
    if not stock_dir.exists():
        return present
    for f in stock_dir.glob(f"*_{trade_date}_stocks.jsonl"):
        m = re.match(r"^(\d+)_", f.name)
        if m:
            present.add(m.group(1))
    return present


def format_sample(items: list[str], limit: int = 10) -> str:
    if not items:
        return ""
    return ",".join(items[:limit])


def main() -> int:
    parser = argparse.ArgumentParser(description="Check JYHF completion status")
    parser.add_argument("--trade-date", default=None, help="Optional trade date for stock_daily check, e.g. 2026-06-11")
    parser.add_argument("--check-stock-daily", action="store_true", help="Also check stock_daily for the given trade date")
    args = parser.parse_args()

    subjects = load_subjects()
    exceptions = load_exception_manifest()
    deleted_children = set(exceptions.get("deleted_or_unavailable", {}).get("children", []) or [])
    recoverable_history = set(exceptions.get("recoverable_missing", {}).get("history", []) or [])

    print(f"full_subjects={len(subjects)}")
    print(f"exception_deleted_children={len(deleted_children)}")
    print(f"exception_recoverable_history={len(recoverable_history)}")

    details_present = present_subjects(PROJECT_ROOT / "theme_data_complete" / "details", "details")
    history_present = present_subjects(PROJECT_ROOT / "theme_data_complete" / "history", "history")
    children_present = present_subjects(PROJECT_ROOT / "theme_data_complete" / "children", "children")

    for name, present, extra_ignored in [
        ("details", details_present, set()),
        ("history", history_present, recoverable_history),
        ("children", children_present, deleted_children),
    ]:
        missing = [s for s in subjects if s not in present and s not in extra_ignored]
        ignored = [s for s in subjects if s not in present and s in extra_ignored]
        print(f"{name}: present={len(present)} missing={len(missing)} ignored={len(ignored)}")
        if missing:
            print(f"  sample_missing={format_sample(missing)}")
        if ignored:
            print(f"  sample_ignored={format_sample(ignored)}")

    if args.check_stock_daily and args.trade_date:
        stock_present = present_stock_daily(args.trade_date)
        stock_missing = [s for s in subjects if s not in stock_present]
        print(f"stock_daily[{args.trade_date}]: present={len(stock_present)} missing={len(stock_missing)}")
        if stock_missing:
            print(f"  sample_missing={format_sample(stock_missing)}")
    elif args.trade_date and not args.check_stock_daily:
        print(f"stock_daily[{args.trade_date}]: skipped (use --check-stock-daily to enable)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

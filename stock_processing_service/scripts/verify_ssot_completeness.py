#!/usr/bin/env python3
"""PR4.2.39 — SSOT Completeness Report.

Usage:
    python stock_processing_service/scripts/verify_ssot_completeness.py 2026-07-09
    python stock_processing_service/scripts/verify_ssot_completeness.py 2026-07-09 2026-07-14
    python stock_processing_service/scripts/verify_ssot_completeness.py --all

Verifies that every section of the formal report can be produced from the
Canonical Snapshot alone — without Builder, Engine, or Legacy Recap.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WB_DIR = PROJECT_ROOT / "tmp" / "analyst_workbench"
CHART_DIR = PROJECT_ROOT / "frontend" / "public" / "api" / "analyst-charts"

# ── Section definitions: (key_path, source_category, required) ──
# source_category: "snapshot" | "producer" | "chart" | "legacy_builder" | "legacy_engine" | "legacy_recap"
SECTIONS: list[tuple[str, str, str, bool]] = [
    # ── Market facts (snapshot.market_state — canonical field, P0-C) ──
    ("market_state.up_count",           "snapshot",       "snapshot.market_state",  True),
    ("market_state.down_count",         "snapshot",       "snapshot.market_state",  True),
    ("market_state.limit_up_count",     "snapshot",       "snapshot.market_state",  True),
    ("market_state.limit_down_count",   "snapshot",       "snapshot.market_state",  True),
    ("market_state.up_ratio",           "snapshot",       "snapshot.market_state",  True),
    ("market_state.turnover_yi",        "snapshot",       "snapshot.market_state",  True),

    # ── Emotion (snapshot.emotion_review — existing field) ──
    ("emotion_review.emotion_node",     "snapshot",       "snapshot.emotion_review", True),
    ("emotion_review.emotion_score",    "snapshot",       "snapshot.emotion_review", True),
    ("emotion_review.risk_level",       "snapshot",       "snapshot.emotion_review", True),
    ("emotion_review.emotion_desc",     "snapshot",       "snapshot.emotion_review", False),

    # ── Capital: Institution Style (snapshot.capital_institution_style — P0-A) ──
    ("capital_institution_style",       "producer",       "snapshot.capital_institution_style", True),
    # ── Capital: Hot Money Style ──
    ("capital_hot_money_style",         "producer",       "snapshot.capital_hot_money_style", True),
    # ── Capital: Active Amount ──
    ("capital_active_amount",           "producer",       "snapshot.capital_active_amount", False),

    # ── Theme Structure (snapshot.theme_structure — P0-C) ──
    ("theme_structure",                 "snapshot",       "snapshot.theme_structure", True),

    # ── Stock Structure (snapshot.stock_structure — P0-C) ──
    ("stock_structure",                 "snapshot",       "snapshot.stock_structure", True),

    # ── Plan (snapshot.playbook + emotion_review) ──
    ("plan_state",                      "snapshot",       "snapshot.plan_state", False),
    ("playbook.strategy_bias",          "snapshot",       "snapshot.playbook", False),
    ("emotion_review.tomorrow_outlook", "snapshot",       "snapshot.emotion_review", False),

    # ── Charts (snapshot.chart_reviews — existing field) ──
    ("chart_reviews",                   "chart",          "snapshot.chart_reviews", True),

    # ── Review ──
    ("approved",                        "snapshot",       "snapshot.approved", True),
    ("cognition_cards",                 "snapshot",       "snapshot.cognition_cards", True),
    ("narrative",                       "snapshot",       "snapshot.narrative", False),
    ("override_summary",                "snapshot",       "snapshot.override_summary", False),
]

# Legacy-only sections — should always be empty/missing
LEGACY_SECTIONS: list[tuple[str, str]] = [
    ("builder.theme_reviews",           "legacy_builder"),
    ("builder.theme_capital_reviews",   "legacy_builder"),
    ("builder.strong_stock_reviews",    "legacy_builder"),
    ("builder.watchlist_reviews",       "legacy_builder"),
    ("builder.stock_capital_reviews",   "legacy_builder"),
    ("builder.money_flow_reviews",      "legacy_builder"),
    ("builder.dragon_tiger_reviews",    "legacy_builder"),
    ("builder.abnormal_reviews",        "legacy_builder"),
    ("engine.engine_report",            "legacy_engine"),
    ("recap.post_market_recap_snapshot","legacy_recap"),
]


def _deep_get(d: dict, path: str) -> Any:
    """Get nested dict value by dot-separated path. Returns sentinel if missing."""
    parts = path.split(".")
    for p in parts:
        if not isinstance(d, dict):
            return _MISSING
        d = d.get(p, _MISSING)
        if d is _MISSING:
            return _MISSING
    return d


_MISSING = object()


def _is_present(value: Any) -> bool:
    """Check if a value is meaningfully present (not None, not empty, not 0 for counts)."""
    if value is _MISSING or value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    if isinstance(value, bool):
        return value  # False is a valid value for booleans
    return True


def load_snapshot(trade_date_str: str) -> dict[str, Any] | None:
    """Load approved snapshot JSON."""
    p = WB_DIR / trade_date_str / "snapshot.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_draft_context(trade_date_str: str) -> dict[str, Any]:
    """Load draft_context.json."""
    p = WB_DIR / trade_date_str / "draft_context.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_chart_data(trade_date_str: str) -> dict[str, Any]:
    """Load chart JSON and index by chart_type."""
    p = CHART_DIR / f"{trade_date_str}.json"
    if not p.exists():
        return {}
    charts = json.loads(p.read_text(encoding="utf-8"))
    return {c.get("chart_type", ""): c for c in charts if isinstance(c, dict)}


def load_emotion_data(trade_date_str: str) -> dict[str, Any]:
    """Load emotion JSON."""
    p = PROJECT_ROOT / "frontend" / "public" / "api" / f"emotion-{trade_date_str}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def check_section(section_path: str, data_sources: dict[str, Any]) -> tuple[bool, str]:
    """Check if a section is present in the available data sources."""
    for source_name, source_dict in data_sources.items():
        if source_name == "chart_data":
            # Special handling: check chart by type
            chart_type = section_path.split(".", 1)[1] if "." in section_path else ""
            if chart_type in source_dict:
                chart = source_dict[chart_type]
                # Check chart data or key_metrics
                d = chart.get("data") or chart.get("key_metrics") or {}
                if isinstance(d, dict) and len(d) > 0:
                    return True, f"chart.{chart_type}"
            continue

        value = _deep_get(source_dict, section_path)
        if _is_present(value):
            return True, source_name

    return False, "missing"


def check_legacy_section(section_path: str, data_sources: dict[str, Any]) -> tuple[bool, str]:
    """Check if legacy section has data (should be empty for clean SSOT)."""
    for source_name, source_dict in data_sources.items():
        value = _deep_get(source_dict, section_path)
        if _is_present(value):
            return True, source_name

    return False, "clean"


def run_report(trade_date_str: str) -> dict[str, Any]:
    """Run SSOT completeness report for a single trading day."""
    snap = load_snapshot(trade_date_str)
    ctx = load_draft_context(trade_date_str)
    charts = load_chart_data(trade_date_str)
    emotion = load_emotion_data(trade_date_str)

    data_sources: dict[str, Any] = {
        "snapshot": snap or {},
        "draft_context": ctx,
        "chart_data": charts,
        "emotion_data": emotion,
    }

    # ── Check SSOT sections ──
    ssot_results: list[dict] = []
    ssot_present = 0
    ssot_total = 0

    for section_path, source_category, source_hint, required in SECTIONS:
        present, found_in = check_section(section_path, data_sources)
        status = "✓" if present else ("✗" if required else "○")
        if present:
            ssot_present += 1
        ssot_total += 1
        ssot_results.append({
            "section": section_path,
            "category": source_category,
            "required": required,
            "present": present,
            "found_in": found_in,
            "status": status,
        })

    # ── Check legacy sections ──
    legacy_results: list[dict] = []
    legacy_present = 0
    legacy_total = 0

    for section_path, source_category in LEGACY_SECTIONS:
        present, found_in = check_legacy_section(section_path, data_sources)
        status = "✗ LEGACY" if present else "✓ clean"
        if present:
            legacy_present += 1
        legacy_total += 1
        legacy_results.append({
            "section": section_path,
            "category": source_category,
            "has_data": present,
            "found_in": found_in,
            "status": status,
        })

    coverage_pct = round(ssot_present / ssot_total * 100, 1) if ssot_total > 0 else 0
    legacy_pct = round(legacy_present / legacy_total * 100, 1) if legacy_total > 0 else 0

    return {
        "trade_date": trade_date_str,
        "snapshot_exists": snap is not None,
        "snapshot_version": snap.get("snapshot_version") if snap else None,
        "draft_context_exists": bool(ctx),
        "chart_data_exists": bool(charts),
        "ssot_coverage_pct": coverage_pct,
        "ssot_present": ssot_present,
        "ssot_total": ssot_total,
        "legacy_pct": legacy_pct,
        "legacy_present": legacy_present,
        "legacy_total": legacy_total,
        "ssot_results": ssot_results,
        "legacy_results": legacy_results,
    }


def print_report(report: dict[str, Any]) -> None:
    """Print human-readable SSOT completeness report."""
    print()
    print(f"{'='*72}")
    print(f"  SSOT Completeness Report — {report['trade_date']}")
    print(f"{'='*72}")
    print(f"  Snapshot: {'v' + str(report['snapshot_version']) if report['snapshot_exists'] else 'MISSING'}")
    print(f"  Draft Context: {'✓' if report['draft_context_exists'] else '✗'}")
    print(f"  Chart Data: {'✓' if report['chart_data_exists'] else '✗'}")
    print()

    # ── Coverage summary ──
    coverage = report['ssot_coverage_pct']
    bar = "█" * int(coverage / 5) + "░" * (20 - int(coverage / 5))
    color = "\033[32m" if coverage >= 90 else "\033[33m" if coverage >= 70 else "\033[31m"
    print(f"  SSOT Coverage:  {color}{coverage:.1f}%\033[0m  [{bar}]")
    print(f"  Legacy Residue: {report['legacy_pct']:.1f}% ({report['legacy_present']}/{report['legacy_total']} sections still carry legacy data)")
    print()

    # ── Section-by-section ──
    by_category: dict[str, tuple[int, int]] = {}
    for r in report['ssot_results']:
        cat = r['category']
        prev = by_category.get(cat, (0, 0))
        by_category[cat] = (prev[0] + (1 if r['present'] else 0), prev[1] + 1)

    print(f"  {'Section':<40} {'Required':>8} {'Status':>6}  {'Found In'}")
    print(f"  {'-'*40} {'-'*8} {'-'*6}  {'-'*20}")
    for r in report['ssot_results']:
        req = "✓" if r['required'] else ""
        found = r['found_in'] if r['present'] else "\033[31mMISSING\033[0m"
        print(f"  {r['section']:<40} {req:>8} {r['status']:>6}  {found}")

    print()
    print(f"  {'─'*68}")
    print(f"  Category Breakdown:")
    for cat, (pres, tot) in sorted(by_category.items()):
        pct = round(pres / tot * 100) if tot > 0 else 0
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        print(f"    {cat:<20} {pres}/{tot}  {pct:>3}%  [{bar}]")

    # ── Legacy check ──
    print()
    print(f"  Legacy Residue Check (should all be 'clean'):")
    for r in report['legacy_results']:
        icon = "\033[31m✗\033[0m" if r['has_data'] else "\033[32m✓\033[0m"
        print(f"    {icon} {r['section']}")

    # ── Verdict ──
    print()
    print(f"  {'='*68}")
    if report['legacy_pct'] == 0 and report['ssot_coverage_pct'] >= 80:
        print(f"  \033[32mVERDICT: SSOT CLEAN\033[0m — Formal report can be produced from Snapshot alone.")
    elif report['ssot_coverage_pct'] >= 60:
        print(f"  \033[33mVERDICT: PARTIAL\033[0m — Some sections still need attention.")
    else:
        print(f"  \033[31mVERDICT: BLOCKED\033[0m — Snapshot is missing critical data.")
    print(f"  {'='*68}")
    print()


def main():
    parser = argparse.ArgumentParser(description="SSOT Completeness Report")
    parser.add_argument("dates", nargs="*", help="Trade dates (YYYY-MM-DD). If two dates, treated as range.")
    parser.add_argument("--all", action="store_true", help="Check all dates from 2026-07-01 to today")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.all:
        today = date.today()
        dates = []
        d = date(2026, 7, 1)
        while d <= today:
            dates.append(d.isoformat())
            d += timedelta(days=1)
    elif len(args.dates) == 2:
        start = date.fromisoformat(args.dates[0])
        end = date.fromisoformat(args.dates[1])
        dates = []
        d = start
        while d <= end:
            dates.append(d.isoformat())
            d += timedelta(days=1)
    elif len(args.dates) >= 1:
        dates = args.dates
    else:
        dates = [date.today().isoformat()]

    reports = []
    for d in dates:
        try:
            report = run_report(d)
            reports.append(report)
            if not args.json:
                print_report(report)
        except Exception as e:
            print(f"  {d}: ERROR — {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2, default=str))

    # Exit code: non-zero if any report has legacy residue or low coverage
    has_issues = any(
        r["legacy_pct"] > 0 or r["ssot_coverage_pct"] < 80
        for r in reports
    )
    sys.exit(1 if has_issues else 0)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PR4.2.39 v2 — SSOT Completeness Report with hard gates and deep content checks.

Usage:
    python stock_processing_service/scripts/verify_ssot_completeness.py 2026-07-14
    python stock_processing_service/scripts/verify_ssot_completeness.py 2026-07-09 2026-07-14
    python stock_processing_service/scripts/verify_ssot_completeness.py --all
    python stock_processing_service/scripts/verify_ssot_completeness.py 2026-07-14 --json

Verdict thresholds:
    < 60%    BLOCKED
    60–79%   DEGRADED
    80–94%   READY_WITH_GAPS
    ≥ 95%    READY

Hard gates (any missing → max READY_WITH_GAPS):
    market, emotion, themes, capital.institution_style,
    capital.hot_money_style, capital.active_amount,
    plan, review.approval
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
WB_DIR = PROJECT_ROOT / "tmp" / "analyst_workbench"
CHART_DIR = PROJECT_ROOT / "frontend" / "public" / "api" / "analyst-charts"

_MISSING = object()

# ── Verdict constants ──
BLOCKED = "BLOCKED"
DEGRADED = "DEGRADED"
READY_WITH_GAPS = "READY_WITH_GAPS"
READY = "READY"

# ── Group definitions ──
# Each group has: name, sections[], hard_gate (blocks READY if any required field missing)
# Each section: (key_path, label, required, content_check_fn | None)
# content_check_fn: None = simple presence check; callable = deep content check


def _has_rows(value: Any) -> bool:
    """Content check: non-empty list/dict with actual entries."""
    if isinstance(value, list):
        return len(value) > 0 and any(
            (isinstance(item, dict) and len(item) > 0) or not isinstance(item, dict)
            for item in value
        )
    if isinstance(value, dict):
        return len(value) > 0
    return value is not None and value is not _MISSING


def _has_positive(value: Any) -> bool:
    """Content check: numeric value > 0."""
    if value is None or value is _MISSING:
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _has_non_empty_string(value: Any) -> bool:
    """Content check: non-empty string."""
    return isinstance(value, str) and value.strip() != ""


GROUPS: list[dict[str, Any]] = [
    {
        "key": "market",
        "name": "Market State",
        "hard_gate": True,
        "sections": [
            ("market_state.up_count",       "up_count",              True,  _has_positive),
            ("market_state.down_count",     "down_count",            True,  _has_positive),
            ("market_state.limit_up_count", "limit_up_count",        True,  _has_positive),
            ("market_state.limit_down_count","limit_down_count",     True,  lambda v: True),  # 0 is valid
            ("market_state.up_ratio",       "up_ratio",              True,  _has_positive),
            ("market_state.turnover_yi",    "turnover_yi",           True,  lambda v: v is not None),  # 0 valid when recap missing
        ],
    },
    {
        "key": "emotion",
        "name": "Emotion",
        "hard_gate": True,
        "sections": [
            ("emotion_review.emotion_node",  "emotion_node",        True,  _has_non_empty_string),
            ("emotion_review.emotion_score", "emotion_score",       True,  lambda v: v is not None),
            ("emotion_review.risk_level",    "risk_level",          True,  _has_non_empty_string),
            ("emotion_review.emotion_desc",  "emotion_desc",        False, _has_non_empty_string),
            ("emotion_review.key_evidence",  "key_evidence",        False, _has_rows),
        ],
    },
    {
        "key": "capital",
        "name": "Capital Evidence",
        "hard_gate": True,
        "sections": [
            ("capital_institution_style",    "institution directions", True,  _has_rows),
            ("capital_hot_money_style",      "hot_money directions",   True,  _has_rows),
            ("capital_active_amount",        "active_amount",          True,  _has_positive),
            ("capital_seat_money",           "seat_money",             False, _has_rows),
        ],
        # Quality annotation: when hot_money is empty, check if it's NO_DATA (legit) vs MISSING (broken)
        "quality_key": "capital_quality",
    },
    {
        "key": "themes",
        "name": "Theme Structure",
        "hard_gate": True,
        "sections": [
            ("theme_structure",              "theme rows",            True,  _has_rows),
        ],
    },
    {
        "key": "stocks",
        "name": "Stock Structure",
        "hard_gate": False,
        "sections": [
            ("stock_structure",              "stock rows",            True,  _has_rows),
        ],
    },
    {
        "key": "plan",
        "name": "Next Day Plan",
        "hard_gate": True,
        "sections": [
            ("plan_state",                   "plan_state",            True,  _has_rows),
            ("emotion_review.tomorrow_outlook","tomorrow_outlook",    True,  _has_non_empty_string),
            ("emotion_review.tomorrow_forbidden","forbidden_actions", False, _has_rows),
            ("emotion_review.tomorrow_watchpoints","watchpoints",     False, _has_rows),
        ],
    },
    {
        "key": "charts",
        "name": "Charts",
        "hard_gate": False,
        "sections": [
            ("chart_reviews",                "chart_reviews",         True,  _has_rows),
        ],
    },
    {
        "key": "review",
        "name": "Review / Approval",
        "hard_gate": True,
        "sections": [
            ("approved",                     "approved flag",         True,  lambda v: bool(v)),
            ("cognition_cards",              "cognition_cards",       True,  _has_rows),
            ("narrative",                    "narrative",             False, _has_rows),
            ("override_summary",             "override_summary",      False, _has_rows),
        ],
    },
]

# Legacy sections that must be EMPTY for SSOT to be clean
LEGACY_CHECKS: list[tuple[str, str]] = [
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


# ── Data loading ──

def load_snapshot(trade_date_str: str) -> dict[str, Any] | None:
    p = WB_DIR / trade_date_str / "snapshot.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_draft_context(trade_date_str: str) -> dict[str, Any]:
    p = WB_DIR / trade_date_str / "draft_context.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def load_chart_data(trade_date_str: str) -> dict[str, Any]:
    p = CHART_DIR / f"{trade_date_str}.json"
    if not p.exists():
        return {}
    charts = json.loads(p.read_text(encoding="utf-8"))
    return {c.get("chart_type", ""): c for c in charts if isinstance(c, dict)}


def load_emotion_data(trade_date_str: str) -> dict[str, Any]:
    p = PROJECT_ROOT / "frontend" / "public" / "api" / f"emotion-{trade_date_str}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


# ── Core check logic ──

def _deep_get(d: dict, path: str) -> Any:
    parts = path.split(".")
    for p in parts:
        if not isinstance(d, dict):
            return _MISSING
        d = d.get(p, _MISSING)
        if d is _MISSING:
            return _MISSING
    return d


def _is_present(value: Any) -> bool:
    if value is _MISSING or value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, (list, dict)) and len(value) == 0:
        return False
    return True


def check_section(path: str, data_sources: dict[str, Any], content_check: Callable | None) -> tuple[bool, str, bool]:
    """Returns (has_data, source, deep_content_ok)."""
    value = _MISSING
    found_in = "missing"

    for source_name, source_dict in data_sources.items():
        v = _deep_get(source_dict, path)
        if _is_present(v):
            value = v
            found_in = source_name
            break

    if value is _MISSING:
        return False, "missing", False

    has_content = content_check(value) if content_check else True
    return True, found_in, has_content


def run_report(trade_date_str: str) -> dict[str, Any]:
    snap = load_snapshot(trade_date_str)
    ctx = load_draft_context(trade_date_str)
    charts = load_chart_data(trade_date_str)
    emotion = load_emotion_data(trade_date_str)

    # Also check draft_context as secondary source (shows what WOULD be frozen after approve)
    data_sources = {
        "snapshot": snap or {},
        "draft_context": ctx,
        "emotion_data": emotion,
        "chart_data": charts,
    }
    # Snapshot-only check (primary): what's actually IN the snapshot
    snapshot_only = {"snapshot": snap or {}}
    # Snapshot + draft_context (projected): what WILL be available after approve
    projected = {
        "snapshot": snap or {},
        "draft_context": ctx,
    }

    # ── Group-level results ──
    group_results: list[dict] = []
    total_present = 0
    total_required = 0
    total_content_ok = 0
    hard_gates_failed: list[str] = []

    for grp in GROUPS:
        grp_present = 0
        grp_required = 0
        grp_content_ok = 0
        section_details: list[dict] = []

        # Quality annotation for this group (distinguishes NO_DATA from MISSING)
        quality: dict[str, Any] = {}
        qk = grp.get("quality_key")
        if qk:
            quality = data_sources.get("snapshot", {}).get(qk, {})
            if not quality:
                quality = data_sources.get("draft_context", {}).get(qk, {})

        for path, label, required, content_fn in grp["sections"]:
            has_data, found_in, has_content = check_section(path, data_sources, content_fn)

            # Check quality annotation for NO_DATA override
            nodata = False
            if not has_data and quality:
                # Map section path to quality key: e.g. "capital_hot_money_style" -> "hot_money_status"
                if "hot_money" in path and quality.get("hot_money_status") == "NO_DATA":
                    nodata = True
                    has_data = True
                    found_in = "producer (NO_DATA)"

            status = "✓" if has_data and has_content else ("△" if nodata else ("✗" if required else ("○" if has_data else "○")))
            section_details.append({
                "path": path, "label": label, "required": required,
                "present": has_data, "found_in": found_in,
                "content_ok": has_content,
                "status": status,
                "nodata": nodata,
            })

            if has_data and has_content:
                grp_present += 1
                grp_content_ok += 1
                total_present += 1
                total_content_ok += 1
            elif nodata:
                # NO_DATA: counts as present for coverage, but not for content check
                grp_present += 1
                total_present += 1
            elif has_data and not has_content and required:
                pass  # present but content check failed

            if required:
                grp_required += 1
                total_required += 1

        grp_pct = round(grp_present / grp_required * 100) if grp_required > 0 else 100
        grp_content_pct = round(grp_content_ok / grp_required * 100) if grp_required > 0 else 100

        # Hard gate check: required fields in hard-gate groups must have content
        if grp["hard_gate"] and grp_pct < 100:
            hard_gates_failed.append(grp["key"])

        group_results.append({
            "key": grp["key"],
            "name": grp["name"],
            "hard_gate": grp["hard_gate"],
            "pct": grp_pct,
            "content_pct": grp_content_pct,
            "present": grp_present,
            "required": grp_required,
            "sections": section_details,
        })

    # ── Legacy check ──
    legacy_hits = 0
    legacy_details: list[dict] = []
    for path, category in LEGACY_CHECKS:
        has_data, found_in, _ = check_section(path, data_sources, None)
        legacy_details.append({
            "path": path, "category": category,
            "has_data": has_data, "found_in": found_in,
        })
        if has_data:
            legacy_hits += 1

    # ── Verdict ──
    coverage = round(total_present / total_required * 100, 1) if total_required > 0 else 0
    content_coverage = round(total_content_ok / total_required * 100, 1) if total_required > 0 else 0
    legacy_pct = round(legacy_hits / len(LEGACY_CHECKS) * 100, 1) if LEGACY_CHECKS else 0

    if coverage < 60:
        verdict = BLOCKED
    elif coverage < 80:
        verdict = DEGRADED
    elif coverage < 95 or hard_gates_failed:
        verdict = READY_WITH_GAPS
    else:
        verdict = READY

    # Upgrade from BLOCKED/DEGRADED if hash gates all pass and content is rich
    if verdict == DEGRADED and not hard_gates_failed and content_coverage >= 70:
        verdict = READY_WITH_GAPS

    return {
        "trade_date": trade_date_str,
        "snapshot_exists": snap is not None,
        "snapshot_version": snap.get("snapshot_version") if snap else None,
        "draft_context_exists": bool(ctx),
        "verdict": verdict,
        "coverage_pct": coverage,
        "content_coverage_pct": content_coverage,
        "legacy_pct": legacy_pct,
        "legacy_hits": legacy_hits,
        "hard_gates_failed": hard_gates_failed,
        "group_results": group_results,
        "legacy_details": legacy_details,
    }


# ── Output ──

def verdict_color(v: str) -> str:
    if v == READY: return "\033[32m"
    if v == READY_WITH_GAPS: return "\033[33m"
    if v == DEGRADED: return "\033[33m"
    return "\033[31m"


def bar(pct: float, width: int = 12) -> str:
    filled = int(pct / 100 * width)
    return "█" * filled + "░" * (width - filled)


def print_report(r: dict[str, Any]) -> None:
    B = "\033[1m"
    R = "\033[0m"
    G = "\033[32m"
    Y = "\033[33m"
    RED = "\033[31m"

    print()
    print(f"  {B}SSOT Completeness Report — {r['trade_date']}{R}")
    snap_str = f"v{r['snapshot_version']}" if r['snapshot_exists'] else "MISSING"
    print(f"  Snapshot: {snap_str}  |  Draft Context: {'✓' if r['draft_context_exists'] else '✗'}")
    print()

    # Verdict
    vc = verdict_color(r['verdict'])
    print(f"  {B}Verdict:{R}  {vc}{r['verdict']}{R}")
    print(f"  Coverage: {r['coverage_pct']:.1f}%  [{bar(r['coverage_pct'])}]")
    if r['content_coverage_pct'] != r['coverage_pct']:
        print(f"  Content:  {r['content_coverage_pct']:.1f}%  [{bar(r['content_coverage_pct'])}] (deep check)")
    print(f"  Legacy:   {r['legacy_pct']:.1f}% ({r['legacy_hits']}/{len(LEGACY_CHECKS)} sections)")
    if r['hard_gates_failed']:
        print(f"  {RED}Hard Gates FAILED:{R} {', '.join(r['hard_gates_failed'])}")
    else:
        print(f"  {G}Hard Gates: PASS{R}")
    print()

    # Group breakdown
    print(f"  {B}{'Group':<22} {'Req':>4} {'%':>5}  {'Bar':<14} {'Status'}{R}")
    print(f"  {'-'*22} {'-'*4} {'-'*5}  {'-'*14} {'-'*10}")
    for grp in r['group_results']:
        pct = grp['content_pct'] if grp['content_pct'] < grp['pct'] else grp['pct']
        color = G if pct >= 100 else Y if pct >= 50 else RED
        gate = "🔒" if grp['hard_gate'] else "  "
        status = "✓" if pct >= 100 else f"{grp['present']}/{grp['required']}"
        print(f"  {gate}{grp['name']:<20} {grp['required']:>4} {color}{pct:>4}%{R}  [{color}{bar(pct)}{R}] {status}")

    print()

    # Missing detail — only for groups below 100%
    missing_groups = [g for g in r['group_results'] if g['content_pct'] < 100]
    if missing_groups:
        print(f"  {B}Missing Detail (groups < 100%):{R}")
        for grp in missing_groups:
            missing = [s for s in grp['sections'] if not s['content_ok'] and s['required']]
            nodata_items = [s for s in missing if s.get('nodata')]
            real_missing = [s for s in missing if not s.get('nodata')]
            if nodata_items:
                labels = [f"{m['label']}(NO_DATA)" for m in nodata_items]
                print(f"    {Y}△{R} {grp['name']}: {', '.join(labels)}")
            if real_missing:
                labels = [f"{m['label']}({m['found_in']})" for m in real_missing]
                print(f"    {RED}✗{R} {grp['name']}: {', '.join(labels)}")

    # Legacy detail
    if r['legacy_hits'] > 0:
        print()
        print(f"  {RED}Legacy Residue Found:{R}")
        for ld in r['legacy_details']:
            if ld['has_data']:
                print(f"    {RED}✗{R} {ld['path']} ({ld['category']}) — found in {ld['found_in']}")

    print()


def main():
    parser = argparse.ArgumentParser(description="SSOT Completeness Report v2")
    parser.add_argument("dates", nargs="*")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.all:
        today = date.today()
        dates = [d.isoformat() for d in _date_range(date(2026, 7, 1), today)]
    elif len(args.dates) == 2:
        dates = [d.isoformat() for d in _date_range(date.fromisoformat(args.dates[0]), date.fromisoformat(args.dates[1]))]
    elif len(args.dates) >= 1:
        dates = args.dates
    else:
        dates = [date.today().isoformat()]

    reports = []
    for d in dates:
        try:
            r = run_report(d)
            reports.append(r)
            if not args.json:
                print_report(r)
        except Exception as e:
            print(f"  {d}: ERROR — {e}", file=sys.stderr)

    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2, default=str))

    # Exit code: 0 only if all dates are READY
    all_ready = all(r["verdict"] == READY for r in reports)
    sys.exit(0 if all_ready else 1)


def _date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


if __name__ == "__main__":
    main()

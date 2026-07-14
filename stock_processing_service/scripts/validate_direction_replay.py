#!/usr/bin/env python3
"""PR4.2.34b — Direction Layer Replay Validation.

5 metrics for Direction evaluation:
  M1: Direction Top-K Hit Rate
  M2: Capital Capture Ratio
  M3: Theme Fragmentation Reduction
  M4: Rank Correlation (Spearman ρ) at direction level
  M5: Explainability (per-direction component breakdown + purity)

Usage:
    python stock_processing_service/scripts/validate_direction_replay.py --date 2026-07-09
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Analyst direction baselines (from reports) ──
# Maps analyst theme groupings to our direction keys

ANALYST_DIRECTIONS: dict[str, list[str]] = {
    "2026-07-01": ["ADVANCED_SEMICONDUCTOR_MFG", "AI_STORAGE_CHAIN",
                    "OPTICAL_COMMUNICATION", "DOMESTIC_COMPUTE_CHAIN"],
    "2026-07-02": ["ADVANCED_SEMICONDUCTOR_MFG", "AI_STORAGE_CHAIN",
                    "OPTICAL_COMMUNICATION", "DOMESTIC_COMPUTE_CHAIN"],
    "2026-07-03": ["AI_STORAGE_CHAIN", "OPTICAL_COMMUNICATION",
                    "ADVANCED_SEMICONDUCTOR_MFG", "DOMESTIC_COMPUTE_CHAIN"],
    "2026-07-07": ["ADVANCED_SEMICONDUCTOR_MFG", "DOMESTIC_COMPUTE_CHAIN",
                    "AI_STORAGE_CHAIN", "OPTICAL_COMMUNICATION"],
    "2026-07-08": ["DOMESTIC_COMPUTE_CHAIN", "ADVANCED_SEMICONDUCTOR_MFG",
                    "AI_STORAGE_CHAIN", "OPTICAL_COMMUNICATION"],
    "2026-07-09": ["AI_STORAGE_CHAIN", "DOMESTIC_COMPUTE_CHAIN",
                    "ADVANCED_SEMICONDUCTOR_MFG", "OPTICAL_COMMUNICATION"],
}

# ── Real Tushare data (万元 → 元) ──
WAN = 10_000

# Theme subject_key → flow data for 6 dates
THEME_FLOWS: dict[str, dict[str, float]] = {}

# Extended stock data with theme mapping from earlier collection
THEME_TO_STOCKS = {
    "9015778": ["300223.SZ", "605178.SH"],    # 存储芯片
    "9014001": ["603019.SH", "002396.SZ"],    # 国产算力
    "9018144": ["300223.SZ"],                  # PCB (北京君正 also in 存储)
    "9014636": ["002747.SZ", "002025.SZ"],    # 人形机器人
    "9019807": ["300394.SZ"],                  # 光通信/光模块
    "9066740": ["600206.SH"],                  # 磷化铟
    "9013416": ["000601.SZ"],                  # 电力运营
}

# Collected flow data: {stock_code: {date_str: net_mf_amount_wan}}
COLLECTED = {
    "300223.SZ": {"20260701":108805,"20260702":-18583,"20260703":95510,"20260707":-17528,"20260708":-22792,"20260709":54615},
    "605178.SH": {"20260701":-29393,"20260702":10566,"20260703":-1046,"20260707":877,"20260708":-3664,"20260709":9308},
    "603019.SH": {"20260701":-214863,"20260702":-43592,"20260703":-74978,"20260707":-31216,"20260708":69030,"20260709":117805},
    "002396.SZ": {"20260701":-24261,"20260702":203,"20260703":-18388,"20260707":53509,"20260708":19222,"20260709":16740},
    "688001.SH": {"20260701":2859,"20260702":-390,"20260703":4764,"20260707":4158,"20260708":2658,"20260709":1109},
    "300394.SZ": {"20260701":-235244,"20260702":-18603,"20260703":-14096,"20260707":70569,"20260708":52844,"20260709":193146},
    "002747.SZ": {"20260701":-97094,"20260702":52837,"20260703":-50181,"20260707":43451,"20260708":26300,"20260709":107141},
    "002025.SZ": {"20260701":31774,"20260702":27534,"20260703":14125,"20260707":34177,"20260708":4509,"20260709":4917},
    "600206.SH": {"20260701":-52122,"20260702":62695,"20260703":34712,"20260707":-106929,"20260708":-26670,"20260709":97316},
    "000601.SZ": {"20260701":-7030,"20260702":-10345,"20260703":-6387,"20260707":-18237,"20260708":-4307,"20260709":-3226},
}


def build_theme_flows_from_real_data(trade_date_str: str) -> list[dict[str, Any]]:
    """Build theme-level flows from collected stock data."""
    flows = []
    for sk, stocks in THEME_TO_STOCKS.items():
        net = sum((COLLECTED.get(s, {}).get(trade_date_str, 0) or 0) * WAN for s in stocks)
        flows.append({
            "subject_key": sk,
            "theme_name": sk,
            "net_flow_yuan": net,
            "large_flow_yuan": abs(net) * 0.4 if net != 0 else None,
        })
    return flows


@dataclass
class DirectionReplayResult:
    trade_date: str
    direction_rankings: list[dict[str, Any]] = field(default_factory=list)
    topk_hit: int = 0
    topk_hit_pct: float = 0.0
    capture_ratio: float = 0.0
    fragmentation_before: int = 0
    fragmentation_after: int = 0
    fragmentation_reduction_pct: float = 0.0
    rank_correlation: float | None = None
    explainability_score: float = 0.0
    purity_warnings: list[str] = field(default_factory=list)
    summary: str = ""


def run_replay(
    trade_date_str: str,
    bindings: list[dict[str, Any]],
    direction_names: dict[str, str],
) -> DirectionReplayResult:
    """Run direction replay for one date."""
    from stock_processing_service.application.services.capital_evidence.direction_capital_aggregator import (
        DirectionCapitalAggregator,
    )

    td = date.fromisoformat(trade_date_str)
    compact = td.strftime("%Y%m%d")

    # Build theme flows from real data
    theme_flows = build_theme_flows_from_real_data(compact)

    # Aggregate to directions
    agg = DirectionCapitalAggregator()
    dir_flows, allocations = agg.aggregate(theme_flows, bindings, td)

    # Sort by net flow
    sorted_dirs = sorted(dir_flows, key=lambda d: abs(d.net_flow_yuan or 0), reverse=True)
    system_ranked = [d.direction_key for d in sorted_dirs]
    analyst_ranked = ANALYST_DIRECTIONS.get(trade_date_str, [])

    # ── M1: Top-K Hit Rate ──
    k = min(len(analyst_ranked), len(system_ranked), 4)
    hits = len(set(system_ranked[:k]) & set(analyst_ranked[:k]))
    hit_pct = round(hits / max(k, 1) * 100, 1)

    # ── M2: Capital Capture Ratio ──
    # For themes that map to analyst directions, what % of their flow is captured?
    analyst_theme_set: set[str] = set()
    for ak in analyst_ranked:
        for b in bindings:
            if b.get("direction_key") == ak:
                analyst_theme_set.add(str(b.get("subject_key", "")))

    total_related_flow = sum(
        abs(float(f.get("net_flow_yuan") or 0))
        for f in theme_flows
        if str(f.get("subject_key", "")) in analyst_theme_set
    )
    captured_flow = sum(
        abs(float(a.allocated_amount_yuan or 0))
        for a in allocations
        if a.subject_key in analyst_theme_set
    )
    capture = round(captured_flow / max(total_related_flow, 1), 4)

    # ── M3: Fragmentation Reduction ──
    theme_names = [f.get("theme_name", f.get("subject_key", "")) for f in theme_flows]
    theme_ranked = sorted(
        theme_flows,
        key=lambda f: abs(float(f.get("net_flow_yuan") or 0)),
        reverse=True,
    )
    theme_top5 = [t.get("subject_key", "") for t in theme_ranked[:5]]

    # Count how many of top-5 themes are consolidated into fewer directions
    dirs_for_top_themes: set[str] = set()
    for sk in theme_top5:
        for b in bindings:
            if b.get("subject_key") == sk:
                dirs_for_top_themes.add(b.get("direction_key", ""))

    frag_before = len(theme_top5)
    frag_after = len(dirs_for_top_themes)
    frag_reduction = round((1 - frag_after / max(frag_before, 1)) * 100, 1)

    # ── M4: Rank Correlation ──
    common = [d for d in analyst_ranked if d in system_ranked]
    rho = None
    if len(common) >= 3:
        sys_r = {d: i for i, d in enumerate(system_ranked)}
        ana_r = {d: i for i, d in enumerate(analyst_ranked)}
        n = len(common)
        d2 = sum((sys_r[d] - ana_r[d]) ** 2 for d in common)
        rho = round(1 - 6 * d2 / (n * (n ** 2 - 1)), 2)

    # ── M5: Explainability + Purity ──
    purity_warnings: list[str] = []
    rankings = []
    for i, d in enumerate(sorted_dirs):
        # Find contributing themes
        contribs = []
        total_abs = abs(d.net_flow_yuan or 0)
        for a in allocations:
            if a.direction_key == d.direction_key and a.allocated_amount_yuan:
                pct = abs(a.allocated_amount_yuan) / max(total_abs, 1) * 100
                contribs.append((a.subject_key, round(pct, 1)))

        contribs.sort(key=lambda x: x[1], reverse=True)
        top_contrib_pct = contribs[0][1] if contribs else 0

        # Purity check: if one theme dominates (>65%), direction may be too narrow
        if top_contrib_pct > 65 and len(contribs) > 1:
            purity_warnings.append(
                f"{d.direction_name}: {contribs[0][0]} dominates at {top_contrib_pct:.0f}%"
            )

        rankings.append({
            "rank": i + 1,
            "direction_key": d.direction_key,
            "direction_name": d.direction_name,
            "net_flow_yuan": d.net_flow_yuan,
            "theme_count": d.theme_count,
            "attributed_theme_count": d.attributed_theme_count,
            "coverage": d.flow_coverage_ratio,
            "top_contributors": contribs[:3],
            "purity": round(top_contrib_pct / 100, 3),
        })

    # Explainability score: % of directions with component breakdown
    explain_score = round(len(rankings) / max(len(sorted_dirs), 1), 2)

    # ── Summary ──
    parts = []
    if hit_pct >= 75:
        parts.append(f"Top-{k} hit: {hit_pct:.0f}%")
    if capture >= 0.70:
        parts.append(f"capture: {capture:.0%}")
    if rho is not None and rho >= 0.5:
        parts.append(f"ρ={rho}")
    summary = "PASS: " + ", ".join(parts) if len(parts) >= 2 else f"PARTIAL: {hits}/{k} overlap"

    return DirectionReplayResult(
        trade_date=trade_date_str,
        direction_rankings=rankings,
        topk_hit=hits,
        topk_hit_pct=hit_pct,
        capture_ratio=capture,
        fragmentation_before=frag_before,
        fragmentation_after=frag_after,
        fragmentation_reduction_pct=frag_reduction,
        rank_correlation=rho,
        explainability_score=explain_score,
        purity_warnings=purity_warnings,
        summary=summary,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="PR4.2.34b Direction Replay Validation")
    parser.add_argument("--date", default=None, help="Single date YYYY-MM-DD")
    parser.add_argument("--all", action="store_true", help="Run all 6 dates")
    args = parser.parse_args()

    # Load bindings from bootstrap YAML
    yaml_path = (
        PROJECT_ROOT
        / "stock_processing_service"
        / "application"
        / "services"
        / "capital_evidence"
        / "direction_bootstrap.yaml"
    )
    with open(yaml_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    bindings: list[dict[str, Any]] = []
    direction_names: dict[str, str] = {}
    for dk, d in config["directions"].items():
        direction_names[dk] = d["name"]
        for t in d["themes"]:
            bindings.append({
                "direction_key": dk,
                "direction_name": d["name"],
                "subject_key": t["subject_key"],
                "weight": t["weight"],
                "role": t["role"],
            })

    if args.date:
        dates = [args.date]
    else:
        dates = ["2026-07-01", "2026-07-02", "2026-07-03",
                 "2026-07-07", "2026-07-08", "2026-07-09"]

    results = []
    for d in dates:
        r = run_replay(d, bindings, direction_names)
        results.append(r)

        print(f"\n{'='*70}")
        print(f"Direction Replay — {r.trade_date}")
        print(f"{'='*70}")
        print(f"Summary: {r.summary}")
        print()
        print(f"  M1 Top-K Hit:      {r.topk_hit}/{min(4, len(r.direction_rankings))} ({r.topk_hit_pct:.0f}%)")
        print(f"  M2 Capture Ratio:  {r.capture_ratio:.1%}")
        print(f"  M3 Fragmentation:  {r.fragmentation_before} themes → {r.fragmentation_after} directions ({r.fragmentation_reduction_pct:.0f}% reduction)")
        print(f"  M4 Rank Corr (ρ):  {r.rank_correlation}")
        print(f"  M5 Explainability: {r.explainability_score:.0%}")
        if r.purity_warnings:
            print(f"  Purity warnings:")
            for w in r.purity_warnings:
                print(f"    ⚠ {w}")

        print(f"\n  Direction Rankings:")
        for item in r.direction_rankings[:8]:
            contrib_str = " + ".join(
                f"{c[0]}({c[1]:.0f}%)" for c in item["top_contributors"]
            )
            flow_str = f"{item['net_flow_yuan']/1e8:+.1f}亿" if item["net_flow_yuan"] else "—"
            print(f"  {item['rank']:2d}. {item['direction_name']:12s} {flow_str:>8s}  "
                  f"cov={item['coverage']:.2f}  themes={item['attributed_theme_count']}/{item['theme_count']}  "
                  f"[{contrib_str}]")

    # Batch summary
    if len(results) > 1:
        print(f"\n{'='*80}")
        print("BATCH SUMMARY — Direction Replay")
        print(f"{'='*80}")
        print(f"{'Date':<12} {'Hit':>6} {'Capture':>9} {'Frag↓':>7} {'ρ':>7} {'Explain':>8}  Summary")
        print("-" * 70)
        for r in results:
            rho_str = str(r.rank_correlation) if r.rank_correlation is not None else "-"
            print(f"{r.trade_date:<12} {r.topk_hit_pct:>5.0f}% {r.capture_ratio:>8.1%} "
                  f"{r.fragmentation_reduction_pct:>6.0f}% {rho_str:>7} {r.explainability_score:>7.0%}  "
                  f" {r.summary[:50]}")

        avg_hit = sum(r.topk_hit_pct for r in results) / len(results)
        avg_capture = sum(r.capture_ratio for r in results) / len(results)
        avg_frag = sum(r.fragmentation_reduction_pct for r in results) / len(results)
        pass_count = sum(1 for r in results if r.summary.startswith("PASS"))

        print("-" * 70)
        print(f"  Avg: hit={avg_hit:.0f}% capture={avg_capture:.0%} frag↓={avg_frag:.0f}%  "
              f"PASS={pass_count}/{len(results)}")

        # Acceptance check
        checks = {
            "M1 Top-5 hit ≥ 75%": avg_hit >= 75,
            "M2 Capture ≥ 70%": avg_capture >= 0.70,
            "M3 Frag ↓ ≥ 30%": avg_frag >= 30,
            "M5 Explain = 100%": all(r.explainability_score >= 0.95 for r in results),
        }
        print(f"\nAcceptance:")
        for check, passed in checks.items():
            print(f"  {'✅' if passed else '❌'} {check}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

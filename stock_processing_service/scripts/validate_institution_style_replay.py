#!/usr/bin/env python3
"""PR4.2.33a Institution Style Replay Audit (Multi-Date Batch).

Validates InstitutionStyleProducer against analyst expectations:
  Metric 1: Top-5 theme overlap
  Metric 2: Rank correlation (Spearman ρ)
  Metric 3: NDCG@5 (Normalized Discounted Cumulative Gain)
  Metric 4: Component sanity (no single-component outlier)
  Metric 5: Cycle discrimination (detects stage concentration)

Usage:
    # Single date dry-run:
    python stock_processing_service/scripts/validate_institution_style_replay.py --date 2026-07-09 --dry-run

    # Multi-date batch dry-run:
    python stock_processing_service/scripts/validate_institution_style_replay.py --dates 2026-06-25,2026-06-30,2026-07-03,2026-07-07,2026-07-08,2026-07-09 --dry-run

    # From DB:
    python stock_processing_service/scripts/validate_institution_style_replay.py --date 2026-07-09
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Analyst baselines (from report analysis) ──

ANALYST_BASELINES: dict[str, list[str]] = {
    "2026-06-25": [
        # TODO: fill from analyst report for this date
        "存储芯片", "国产算力", "PCB", "光通信", "半导体设备",
        "液冷", "卫星", "机器人", "磷化铟", "电力",
    ],
    "2026-06-30": [
        # TODO: fill from analyst report for this date
        "存储芯片", "国产算力", "PCB", "光通信", "半导体设备",
        "液冷", "卫星", "机器人", "磷化铟", "电力",
    ],
    "2026-07-03": [
        # TODO: fill from analyst report for this date
        "存储芯片", "国产算力", "PCB", "光通信", "半导体设备",
        "液冷", "卫星", "机器人", "磷化铟", "电力",
    ],
    "2026-07-07": [
        # TODO: fill from analyst report for this date
        "存储芯片", "国产算力", "PCB", "光通信", "半导体设备",
        "液冷", "卫星", "机器人", "磷化铟", "电力",
    ],
    "2026-07-08": [
        # TODO: fill from analyst report for this date
        "存储芯片", "国产算力", "PCB", "光通信", "半导体设备",
        "液冷", "卫星", "机器人", "磷化铟", "电力",
    ],
    "2026-07-09": [
        "存储芯片",
        "国产算力",
        "PCB印制电路板",
        "半导体设备",
        "光通信",
        "液冷服务器",
        "卫星互联网",
        "人形机器人",
        "磷化铟",
        "电力运营",
    ],
}


@dataclass
class ReplayResult:
    trade_date: str
    system_top10: list[dict[str, Any]]
    analyst_baseline: list[str]
    top5_overlap: int
    top5_overlap_pct: float
    rank_correlation: float | None
    ndcg_at_5: float | None
    component_sanity: dict[str, Any]
    cycle_discrimination: dict[str, Any]
    summary: str


def _ndcg_at_k(system_ranked: list[str], analyst_ranked: list[str], k: int = 5) -> float | None:
    """Compute NDCG@k — penalizes ranking important themes too low.

    Analyst ranking provides relevance scores: #1 = k, #2 = k-1, ..., #k = 1.
    DCG = Σ (relevance_i / log2(i+1)) for i=1..k
    IDCG = ideal DCG (analyst's own ranking)
    NDCG = DCG / IDCG
    """
    if len(system_ranked) < k or len(analyst_ranked) < k:
        return None

    # Relevance: analyst rank position → score (higher rank = higher relevance)
    relevance = {name: max(0, k - i) for i, name in enumerate(analyst_ranked[:k])}

    import math

    def _dcg(ranked: list[str]) -> float:
        score = 0.0
        for i, name in enumerate(ranked[:k]):
            rel = relevance.get(name, 0)
            if rel > 0:
                score += rel / math.log2(i + 2)  # i+2 because log2(1)=0
        return score

    dcg = _dcg(system_ranked)
    idcg = _dcg(analyst_ranked)
    if idcg == 0:
        return None
    return round(dcg / idcg, 4)


def _cycle_discrimination_check(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Detect cycle stage concentration — if many themes share the same stage,
    cycle_score loses discrimination power."""
    from collections import Counter

    stages = [r.get("lifecycle_stage", "") for r in results if r.get("lifecycle_stage")]
    if not stages:
        return {"status": "NO_DATA", "dominant_stage": None, "concentration": 0.0}

    counts = Counter(stages)
    top_stage, top_count = counts.most_common(1)[0]
    concentration = top_count / len(stages)

    if concentration > 0.50:
        status = "WARN"
        detail = f"{top_stage} dominates ({top_count}/{len(stages)} = {concentration:.0%}) — cycle_score loses discrimination"
    elif concentration > 0.35:
        status = "NOTE"
        detail = f"{top_stage} is common ({concentration:.0%}) — monitor for future concentration"
    else:
        status = "OK"
        detail = f"stages well distributed (max={top_stage} at {concentration:.0%})"

    return {
        "status": status,
        "dominant_stage": top_stage,
        "concentration": round(concentration, 3),
        "detail": detail,
    }


def _spearman_rank(system_ranked: list[str], analyst_ranked: list[str]) -> float | None:
    """Compute Spearman rank correlation between two ranked lists."""
    if len(system_ranked) < 3 or len(analyst_ranked) < 3:
        return None

    # Only compare themes present in both lists
    common = set(system_ranked) & set(analyst_ranked)
    if len(common) < 3:
        return None

    sys_ranks = {name: i for i, name in enumerate(system_ranked) if name in common}
    ana_ranks = {name: i for i, name in enumerate(analyst_ranked) if name in common}

    n = len(common)
    d_sq_sum = sum(
        (sys_ranks[name] - ana_ranks[name]) ** 2
        for name in common
    )

    rho = 1.0 - (6.0 * d_sq_sum) / (n * (n**2 - 1))
    return round(rho, 4)


def _component_sanity_check(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Check that high scores aren't driven by a single outlier component."""
    if not results:
        return {"status": "NO_DATA", "issues": []}

    issues: list[str] = []
    for r in results[:10]:
        scores = {
            "flow": r.get("flow_score") or 0,
            "cycle": r.get("cycle_score") or 0,
            "structure": r.get("structure_score") or 0,
            "dt": r.get("dragon_tiger_score") or 0,
        }
        non_zero = {k: v for k, v in scores.items() if v > 0}
        if not non_zero:
            continue

        max_component = max(non_zero, key=non_zero.get)
        max_val = non_zero[max_component]
        avg_others = sum(v for k, v in non_zero.items() if k != max_component) / max(len(non_zero) - 1, 1)

        # If one component is >2x the average of others, flag it
        if max_val > avg_others * 2.0 and avg_others > 0:
            issues.append(
                f"{r.get('theme_name', r.get('subject_key'))}: "
                f"{max_component}={max_val:.1f} dominates (others avg={avg_others:.1f})"
            )

    return {
        "status": "PASS" if len(issues) <= 2 else "WARN",
        "issues_count": len(issues),
        "issues": issues[:5],
    }


def run_replay(
    results: list[dict[str, Any]],
    baseline: list[str],
    trade_date: str,
) -> ReplayResult:
    """Run replay audit comparing system output to analyst baseline."""

    # Sort system results by score descending
    sorted_results = sorted(results, key=lambda r: r.get("institution_score") or 0, reverse=True)
    system_names = [r.get("theme_name", "") for r in sorted_results]

    # Metric 1: Top-5 overlap
    system_top5 = set(system_names[:5])
    analyst_top5 = set(baseline[:5])
    overlap = len(system_top5 & analyst_top5)
    overlap_pct = round(overlap / 5 * 100, 1)

    # Metric 2: Rank correlation
    rank_corr = _spearman_rank(system_names[:10], baseline[:10])

    # Metric 3: NDCG@5 — penalizes ranking important themes too low
    ndcg = _ndcg_at_k(system_names, baseline, k=5)

    # Metric 4: Component sanity
    sanity = _component_sanity_check([r for r in sorted_results[:10]])

    # Metric 5: Cycle discrimination
    cycle_disc = _cycle_discrimination_check(sorted_results[:20])

    # Summary
    issues = []
    if overlap < 3:
        issues.append(f"low overlap ({overlap}/5)")
    if rank_corr is not None and rank_corr < 0.3:
        issues.append(f"weak ranking (ρ={rank_corr})")
    if ndcg is not None and ndcg < 0.5:
        issues.append(f"low NDCG@5 ({ndcg})")
    if sanity["status"] == "WARN":
        issues.append(f"component imbalance ({sanity['issues_count']} issues)")
    if cycle_disc["status"] == "WARN":
        issues.append(f"cycle concentration ({cycle_disc['dominant_stage']})")

    if not issues:
        summary = "PASS: System direction aligns with analyst."
    elif len(issues) <= 1:
        summary = f"PARTIAL: {issues[0]}"
    else:
        summary = f"MISMATCH: {'; '.join(issues)}"

    return ReplayResult(
        trade_date=trade_date,
        system_top10=[
            {"rank": i + 1, "theme": r.get("theme_name"), "score": r.get("institution_score"),
             "components": {
                 "flow": r.get("flow_score"), "cycle": r.get("cycle_score"),
                 "structure": r.get("structure_score"), "dt": r.get("dragon_tiger_score"),
             },
             "confidence": r.get("confidence"), "lifecycle": r.get("lifecycle_stage")}
            for i, r in enumerate(sorted_results[:10])
        ],
        analyst_baseline=baseline,
        top5_overlap=overlap,
        top5_overlap_pct=overlap_pct,
        rank_correlation=rank_corr,
        ndcg_at_5=ndcg,
        component_sanity=sanity,
        cycle_discrimination=cycle_disc,
        summary=summary,
    )


def run_dry_run(trade_date: str) -> ReplayResult:
    """Run replay with sample data (no DB required)."""
    from stock_processing_service.application.services.capital_evidence.institution_style_producer import (
        InstitutionStyleProducer,
    )

    # Sample theme flows
    flows = [
        {"trade_date": trade_date, "subject_key": "9015778", "theme_name": "存储芯片",
         "net_flow_yuan": 1860000000.00, "large_flow_yuan": 520000000.00,
         "flow_coverage_ratio": 0.82, "attributed_stock_count": 16, "stock_count": 20, "positive_stock_count": 12},
        {"trade_date": trade_date, "subject_key": "9014001", "theme_name": "国产算力",
         "net_flow_yuan": 1200000000.00, "large_flow_yuan": 600000000.00,
         "flow_coverage_ratio": 0.75, "attributed_stock_count": 15, "stock_count": 20, "positive_stock_count": 10},
        {"trade_date": trade_date, "subject_key": "9018144", "theme_name": "PCB印制电路板",
         "net_flow_yuan": 800000000.00, "large_flow_yuan": 300000000.00,
         "flow_coverage_ratio": 0.68, "attributed_stock_count": 12, "stock_count": 18, "positive_stock_count": 8},
        {"trade_date": trade_date, "subject_key": "9034501", "theme_name": "半导体设备",
         "net_flow_yuan": 650000000.00, "large_flow_yuan": 250000000.00,
         "flow_coverage_ratio": 0.60, "attributed_stock_count": 10, "stock_count": 16, "positive_stock_count": 7},
        {"trade_date": trade_date, "subject_key": "9045601", "theme_name": "光通信",
         "net_flow_yuan": 500000000.00, "large_flow_yuan": 200000000.00,
         "flow_coverage_ratio": 0.55, "attributed_stock_count": 9, "stock_count": 15, "positive_stock_count": 6},
    ]

    cycles = [
        {"subject_key": "9015778", "final_cycle_state": "FERMENTATION", "previous_stage": "START"},
        {"subject_key": "9014001", "final_cycle_state": "FERMENTATION", "previous_stage": "INCUBATION"},
        {"subject_key": "9018144", "final_cycle_state": "START", "previous_stage": ""},
        {"subject_key": "9034501", "final_cycle_state": "DIFFUSION", "previous_stage": "FERMENTATION"},
        {"subject_key": "9045601", "final_cycle_state": "INCUBATION", "previous_stage": "START"},
    ]

    def _make_stocks(n: int, leaders: int = 1) -> list[dict]:
        stocks = []
        for i in range(leaders):
            stocks.append({"stock_code": f"00000{i}.SZ", "role": "龙头", "watch_score": 80.0})
        for i in range(max(0, n - leaders)):
            stocks.append({"stock_code": f"6000{i:03d}.SH", "role": "", "watch_score": 40.0})
        return stocks

    structures = {
        "9015778": _make_stocks(9, 2),
        "9014001": _make_stocks(8, 2),
        "9018144": _make_stocks(7, 1),
        "9034501": _make_stocks(6, 1),
        "9045601": _make_stocks(5, 1),
    }

    producer = InstitutionStyleProducer()
    results = producer.produce(flows, cycles, structures, None)

    baseline = ANALYST_BASELINES.get(trade_date, [])
    return run_replay([r.to_row() for r in results], baseline, trade_date)


async def run_from_db(trade_date_str: str) -> ReplayResult:
    """Run replay from actual DB tables (requires populated data)."""
    import asyncpg

    conn = await asyncpg.connect(
        f"postgresql://localhost:5432/stock_data_test",
        user=os.environ.get("POSTGRES_USER", "postgres"),
        password=os.environ.get("POSTGRES_PASSWORD", ""),
    )
    try:
        # Load theme flows
        flow_rows = await conn.fetch(
            "SELECT * FROM theme_capital_flow_daily WHERE trade_date = $1::date",
            trade_date_str,
        )
        flows = [dict(r) for r in flow_rows]

        # Load cycles
        cycle_rows = await conn.fetch(
            "SELECT * FROM theme_cycle_judgement_v2 WHERE trade_date = $1::date",
            trade_date_str,
        )
        cycles = [dict(r) for r in cycle_rows]

        # Load stocks
        stock_rows = await conn.fetch(
            "SELECT * FROM strong_stock_watch_history WHERE trade_date = $1::date",
            trade_date_str,
        )
        structures: dict[str, list[dict]] = {}
        for r in stock_rows:
            key = str(r.get("subject_key") or "").strip()
            if key:
                structures.setdefault(key, []).append(dict(r))

        if not flows:
            print(f"WARNING: No theme_capital_flow_daily rows for {trade_date_str}")
            print("Run PR4.2.31f + PR4.2.32a first to populate data.")

    finally:
        await conn.close()

    from stock_processing_service.application.services.capital_evidence.institution_style_producer import (
        InstitutionStyleProducer,
    )
    producer = InstitutionStyleProducer()
    results = producer.produce(flows, cycles, structures, None)

    baseline = ANALYST_BASELINES.get(trade_date_str, [])
    return run_replay([r.to_row() for r in results], baseline, trade_date_str)


def run_batch(dates: list[str], dry_run: bool = True) -> list[ReplayResult]:
    """Run replay audit for multiple dates and produce batch summary."""
    results: list[ReplayResult] = []
    for d in dates:
        if dry_run:
            result = run_dry_run(d)
        else:
            result = asyncio.run(run_from_db(d))
        results.append(result)
    return results


def _print_single_result(result: ReplayResult) -> None:
    print("=" * 60)
    print(f"Institution Style Replay Audit — {result.trade_date}")
    print("=" * 60)
    print()
    print(f"Summary: {result.summary}")
    print()

    print("Metric 1: Top-5 Overlap")
    print(f"  Overlap: {result.top5_overlap}/5 ({result.top5_overlap_pct}%)")
    print(f"  Analyst Top-5: {result.analyst_baseline[:5] if result.analyst_baseline else 'N/A'}")
    print(f"  System  Top-5: {[r['theme'] for r in result.system_top10[:5]]}")
    print()

    print("Metric 2: Rank Correlation")
    print(f"  Spearman ρ: {result.rank_correlation}")
    print()

    print("Metric 3: NDCG@5")
    print(f"  NDCG: {result.ndcg_at_5}")
    print()

    print("Metric 4: Component Sanity")
    print(f"  Status: {result.component_sanity['status']}")
    print(f"  Issues: {result.component_sanity['issues_count']}")
    for issue in result.component_sanity.get("issues", []):
        print(f"    - {issue}")
    print()

    print("Metric 5: Cycle Discrimination")
    cd = result.cycle_discrimination
    print(f"  Status: {cd['status']}")
    print(f"  {cd.get('detail', '')}")
    print()

    print("System Top-10:")
    for r in result.system_top10:
        c = r["components"]
        print(f"  {r['rank']:2d}. {r['theme']:12s}  score={r['score']:5.1f}  "
              f"flow={c['flow'] or 0:5.1f}  cycle={c['cycle'] or 0:5.1f}  "
              f"struct={c['structure'] or 0:5.1f}  dt={c['dt'] or 0:5.1f}  "
              f"conf={r['confidence']:.2f}  stage={r['lifecycle']}")


def _print_batch_summary(results: list[ReplayResult]) -> None:
    print()
    print("=" * 80)
    print("BATCH SUMMARY — Institution Style Replay Audit")
    print("=" * 80)
    print()
    print(f"{'Date':<12} {'Overlap':>8} {'ρ':>8} {'NDCG@5':>8} {'Sanity':>8} {'Cycle':>8} {'Summary'}")
    print("-" * 80)
    for r in results:
        print(f"{r.trade_date:<12} {r.top5_overlap:>4}/5{r.top5_overlap_pct:>4.0f}% "
              f"{r.rank_correlation or '-':>8} "
              f"{r.ndcg_at_5 or '-':>8} "
              f"{r.component_sanity['status']:>8} "
              f"{r.cycle_discrimination['status']:>8} "
              f"  {r.summary[:50]}")

    # Aggregate stats
    avg_overlap = sum(r.top5_overlap for r in results) / max(len(results), 1)
    pass_count = sum(1 for r in results if r.summary.startswith("PASS"))
    partial_count = sum(1 for r in results if r.summary.startswith("PARTIAL"))
    fail_count = sum(1 for r in results if r.summary.startswith("MISMATCH"))

    print("-" * 80)
    print(f"  Avg overlap: {avg_overlap:.1f}/5  |  PASS: {pass_count}  PARTIAL: {partial_count}  FAIL: {fail_count}")
    print()

    # M7 calibration dataset output
    calibration = {
        "model_version": "institution_style_v1",
        "evaluation_dates": [r.trade_date for r in results],
        "metrics": {
            "avg_top5_overlap": round(avg_overlap, 1),
            "avg_ndcg_at_5": round(
                sum(r.ndcg_at_5 for r in results if r.ndcg_at_5 is not None) / max(
                    sum(1 for r in results if r.ndcg_at_5 is not None), 1
                ), 4
            ) if any(r.ndcg_at_5 is not None for r in results) else None,
        },
        "per_date": [
            {
                "trade_date": r.trade_date,
                "top5_overlap": r.top5_overlap,
                "rank_correlation": r.rank_correlation,
                "ndcg_at_5": r.ndcg_at_5,
                "component_sanity": r.component_sanity["status"],
                "cycle_discrimination": r.cycle_discrimination["status"],
                "summary": r.summary,
            }
            for r in results
        ],
    }
    print("M7 Calibration Dataset (JSON):")
    print(json.dumps(calibration, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="PR4.2.33a Institution Style Replay Audit")
    parser.add_argument("--date", default=None, help="Single trade date YYYY-MM-DD")
    parser.add_argument("--dates", default=None, help="Comma-separated dates for batch replay")
    parser.add_argument("--dry-run", action="store_true", help="Use sample data (no DB)")
    args = parser.parse_args()

    if args.dates:
        dates = [d.strip() for d in args.dates.split(",") if d.strip()]
        results = run_batch(dates, dry_run=args.dry_run)
        for r in results:
            _print_single_result(r)
        _print_batch_summary(results)
        return 0
    elif args.date:
        if args.dry_run:
            result = run_dry_run(args.date)
        else:
            result = asyncio.run(run_from_db(args.date))
        _print_single_result(result)
        return 0 if result.top5_overlap >= 2 else 1
    else:
        parser.error("Either --date or --dates is required")


if __name__ == "__main__":
    sys.exit(main())

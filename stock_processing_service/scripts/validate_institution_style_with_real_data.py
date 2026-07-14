#!/usr/bin/env python3
"""PR4.2.33a Institution Style Replay — Real Data Evaluation.

Collects Tushare moneyflow data for key stocks across multiple dates,
aggregates by theme, runs InstitutionStyleProducer, and compares with
analyst baselines extracted from 7 real reports (7/01-7/09).

Usage:
    python stock_processing_service/scripts/validate_institution_style_with_real_data.py
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Configuration ──

THEME_STOCKS: dict[str, list[str]] = {
    "存储芯片":   ["300223.SZ", "605178.SH"],
    "国产算力":   ["603019.SH", "002396.SZ"],
    "半导体设备": ["688001.SH"],
    "光通信":     ["300394.SZ"],
    "人形机器人": ["002747.SZ", "002025.SZ"],
    "磷化铟":     ["600206.SH"],
    "电力运营":   ["000601.SZ"],
}

# Analyst baselines extracted from 7 reports (2026-07-01 ~ 2026-07-09)
# See docs/architecture/ for full report analysis
ANALYST_BASELINES: dict[str, list[str]] = {
    "20260701": ["半导体设备", "存储芯片", "光通信", "PCB", "国产算力"],
    "20260702": ["半导体设备", "存储芯片", "光通信", "半导体硅片", "国产算力"],
    "20260703": ["存储芯片", "PCB", "光通信", "半导体设备", "国产算力"],
    "20260707": ["半导体设备", "国产算力", "存储芯片", "光通信", "液冷服务器"],
    "20260708": ["国产算力", "半导体设备", "存储芯片", "液冷服务器", "光通信"],
    "20260709": ["存储芯片", "国产算力", "PCB", "半导体设备", "光通信"],
}

# Lifecycle stages estimated from analyst report cycle day notes
# Each date has a different market regime that the model must handle
STAGES: dict[str, dict[str, str]] = {
    "20260701": {"半导体设备": "FERMENTATION", "存储芯片": "DIFFUSION", "光通信": "DISTRIBUTION",
                 "国产算力": "DISTRIBUTION", "人形机器人": "START", "磷化铟": "FERMENTATION",
                 "电力运营": "DECAY"},
    "20260702": {"半导体设备": "PEAK", "存储芯片": "DISTRIBUTION", "光通信": "DISTRIBUTION",
                 "国产算力": "DISTRIBUTION", "人形机器人": "FERMENTATION", "磷化铟": "DIFFUSION",
                 "电力运营": "DECAY"},
    "20260703": {"存储芯片": "START", "光通信": "START", "半导体设备": "DISTRIBUTION",
                 "国产算力": "DISTRIBUTION", "人形机器人": "DIFFUSION", "磷化铟": "DIFFUSION",
                 "电力运营": "DECAY"},
    "20260707": {"半导体设备": "START", "国产算力": "INCUBATION", "存储芯片": "DISTRIBUTION",
                 "光通信": "DISTRIBUTION", "人形机器人": "DISTRIBUTION", "磷化铟": "DECAY",
                 "电力运营": "DECAY"},
    "20260708": {"国产算力": "START", "半导体设备": "INCUBATION", "存储芯片": "DISTRIBUTION",
                 "光通信": "DISTRIBUTION", "人形机器人": "DISTRIBUTION", "磷化铟": "DECAY",
                 "电力运营": "DECAY"},
    "20260709": {"存储芯片": "FERMENTATION", "国产算力": "FERMENTATION", "光通信": "START",
                 "半导体设备": "INCUBATION", "人形机器人": "START", "磷化铟": "START",
                 "电力运营": "DECAY"},
}

WAN_TO_YUAN = 10_000
DATES = ["20260701", "20260702", "20260703", "20260707", "20260708", "20260709"]


def collect_tushare_data() -> dict[str, dict[str, Any]]:
    """Collect real Tushare moneyflow data for all theme stocks."""
    token = os.environ.get("TUSHARE_TOKEN", "")
    if not token:
        raise RuntimeError("TUSHARE_TOKEN not set")

    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api(timeout=30)

    all_stocks = sorted(set(s for stocks in THEME_STOCKS.values() for s in stocks))
    collected: dict[str, dict[str, Any]] = {}

    for ts_code in all_stocks:
        collected[ts_code] = {}
        for d in DATES:
            try:
                df = pro.moneyflow(ts_code=ts_code, trade_date=d)
                if len(df) > 0:
                    row = df.iloc[0].to_dict()
                    collected[ts_code][d] = {
                        "net_mf_amount_wan": row.get("net_mf_amount"),
                        "buy_elg_amount": row.get("buy_elg_amount"),
                        "sell_elg_amount": row.get("sell_elg_amount"),
                        "buy_lg_amount": row.get("buy_lg_amount"),
                        "sell_lg_amount": row.get("sell_lg_amount"),
                    }
                else:
                    collected[ts_code][d] = None
            except Exception as e:
                collected[ts_code][d] = {"error": str(e)[:80]}
            time.sleep(0.3)

    return collected


def build_theme_flows(collected: dict, trade_date: str) -> list[dict[str, Any]]:
    """Aggregate stock flows into theme flows."""
    flows = []
    for theme, stocks in THEME_STOCKS.items():
        net_yuan = 0.0
        positive = 0
        for s in stocks:
            val = (collected.get(s, {}).get(trade_date) or {})
            if isinstance(val, dict) and "error" not in val:
                wan = val.get("net_mf_amount_wan") or 0
                net_yuan += wan * WAN_TO_YUAN
                if wan > 0:
                    positive += 1

        n = len(stocks)
        flows.append({
            "trade_date": date(int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:8])),
            "subject_key": theme, "theme_name": theme,
            "net_flow_yuan": net_yuan,
            "large_flow_yuan": abs(net_yuan) * 0.4 if net_yuan != 0 else None,
            "flow_coverage_ratio": 1.0,
            "attributed_stock_count": n, "stock_count": n,
            "positive_stock_count": positive,
        })
    return flows


def build_cycles(trade_date: str) -> list[dict[str, Any]]:
    """Build cycle rows from estimated lifecycle stages."""
    stages = STAGES.get(trade_date, {})
    return [{"subject_key": k, "final_cycle_state": v, "previous_stage": ""}
            for k, v in stages.items()]


def build_structures() -> dict[str, list[dict[str, Any]]]:
    """Build simplified stock structures."""
    return {t: [{"stock_code": s, "role": "龙头" if i == 0 else "", "watch_score": 50.0}
                for i, s in enumerate(stocks)]
            for t, stocks in THEME_STOCKS.items()}


def compute_metrics(system_names: list[str], analyst: list[str]) -> dict[str, Any]:
    """Compute overlap, Spearman ρ, NDCG@5."""
    k = 5
    overlap = len(set(system_names[:k]) & set(analyst[:k]))

    common = [n for n in analyst if n in system_names]
    rho = None
    if len(common) >= 3:
        sys_rank = {n: i for i, n in enumerate(system_names)}
        ana_rank = {n: i for i, n in enumerate(analyst)}
        n = len(common)
        d2 = sum((sys_rank[nm] - ana_rank[nm]) ** 2 for nm in common)
        rho = round(1 - 6 * d2 / (n * (n ** 2 - 1)), 2)

    rel = {n: max(0, k - i) for i, n in enumerate(analyst[:k])}
    dcg = sum(rel.get(n, 0) / math.log2(i + 2) for i, n in enumerate(system_names[:k]))
    idcg = sum(rel.get(n, 0) / math.log2(i + 2) for i, n in enumerate(analyst[:k]))
    ndcg = round(dcg / idcg, 3) if idcg > 0 else None

    return {"overlap": overlap, "rho": rho, "ndcg_at_5": ndcg}


def main() -> int:
    print("=" * 70)
    print("PR4.2.33a Institution Style Replay — Real Data Evaluation")
    print("=" * 70)
    print()

    # Collect data
    print("Collecting Tushare moneyflow data...")
    try:
        collected = collect_tushare_data()
    except RuntimeError as e:
        print(f"SKIP: {e}")
        print("Set TUSHARE_TOKEN and ensure network access to api.tushare.pro")
        return 1

    stock_count = len(collected)
    data_points = sum(
        1 for v in collected.values()
        for d in v.values()
        if isinstance(d, dict) and "error" not in d
    )
    print(f"  Collected: {stock_count} stocks, {data_points} data points")
    print()

    # Run producer
    from stock_processing_service.application.services.capital_evidence.institution_style_producer import (
        InstitutionStyleProducer,
    )
    producer = InstitutionStyleProducer()

    print(f"{'Date':<10} {'System Top-3':<55} {'Overlap':<9} {'ρ':>7} {'NDCG':>7}  Analyst Top-3")
    print("-" * 120)

    all_metrics = []
    for d in DATES:
        theme_flows = build_theme_flows(collected, d)
        cycles = build_cycles(d)
        structures = build_structures()

        results = producer.produce(theme_flows, cycles, structures, None)
        sorted_r = sorted(results, key=lambda r: r.institution_score, reverse=True)

        system_names = [r.theme_name for r in sorted_r]
        analyst = ANALYST_BASELINES.get(d, [])
        metrics = compute_metrics(system_names, analyst)
        all_metrics.append({"date": d, **metrics})

        top3_str = " > ".join(f"{r.theme_name}({r.institution_score:.0f})" for r in sorted_r[:3])
        ana3_str = " > ".join(analyst[:3])
        rho_str = str(metrics["rho"]) if metrics["rho"] is not None else "-"
        ndcg_str = str(metrics["ndcg_at_5"]) if metrics["ndcg_at_5"] is not None else "-"

        print(f"{d}  {top3_str:<55} {metrics['overlap']}/5      {rho_str:>7} {ndcg_str:>7}  {ana3_str}")

    # Summary
    avg_overlap = sum(m["overlap"] for m in all_metrics) / len(all_metrics)
    pass_count = sum(1 for m in all_metrics if m["overlap"] >= 3)
    avg_ndcg = sum(m["ndcg_at_5"] for m in all_metrics if m["ndcg_at_5"] is not None)
    avg_ndcg /= max(sum(1 for m in all_metrics if m["ndcg_at_5"] is not None), 1)

    print()
    print(f"Summary: Avg overlap {avg_overlap:.1f}/5 | PASS (≥3): {pass_count}/{len(all_metrics)} | Avg NDCG@5: {avg_ndcg:.3f}")
    print()

    # Calibration dataset
    print("M7 Calibration Dataset:")
    print(json.dumps({
        "model": "institution_style_v1",
        "dates": len(all_metrics),
        "avg_overlap": round(avg_overlap, 1),
        "avg_ndcg_at_5": round(avg_ndcg, 3),
        "per_date": all_metrics,
    }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())

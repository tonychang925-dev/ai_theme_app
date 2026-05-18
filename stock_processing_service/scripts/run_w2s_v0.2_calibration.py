"""
W2S Phase 0.6 — v0.2 Calibration Run
=====================================
Improvements over v0.1:
  P0: proxy_X semantics split (unconfirmed/positive_open/negative_open/X)
  P1: Candidate pool quality report (candidate_type, support_type, score buckets)
  P2: Benchmark returns (market avg, subject avg, excess returns)
  P3: Auction scorer quantile calibration

Strategy: w2s_signal_validation_v0.2_calibration
This is a RESEARCH version — not a trading strategy.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("w2s_v0.2")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.tests.replay._post_market_replay_runner import _ReplayDatabaseStockFacade
from stock_processing_service.application.services.backtest.w2s_feature_snapshot_service import (
    W2SFeatureSnapshotService,
)
from stock_processing_service.application.services.backtest.w2s_signal_builder_service import (
    W2SSignalBuilderService,
)
from stock_processing_service.application.services.backtest.w2s_signal_validation_service import (
    W2SSignalValidationService,
)
from stock_processing_service.application.services.backtest.w2s_validation_summary_service import (
    W2SValidationSummaryService,
)

STRATEGY_VERSION = "w2s_signal_validation_v0.2_calibration"
START_DATE = date(2026, 4, 1)
END_DATE = date(2026, 5, 15)
DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")


def _create_run_id() -> str:
    return f"w2s_v0.2_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


async def step1_data_check(gw) -> dict:
    """Quick data check, non-blocking."""
    logger.info("=== Step 1: Data Check ===")
    rows = await gw._client.execute_query(
        "SELECT COUNT(*) as cnt, COUNT(DISTINCT trade_date) as dates FROM weak_to_strong_candidate_pool WHERE trade_date >= $1 AND trade_date <= $2",
        (START_DATE, END_DATE),
    )
    r = rows[0]
    print(f"Candidates: {r['cnt']} rows across {r['dates']} dates")
    bar_rows = await gw._client.execute_query(
        "SELECT COUNT(DISTINCT trade_date) as dates FROM stock_daily_snapshot WHERE trade_date >= $1 AND trade_date <= $2",
        (START_DATE, END_DATE),
    )
    print(f"Bar dates: {bar_rows[0]['dates']}")
    return {"candidates": r["cnt"], "candidate_dates": r["dates"]}


async def step2_build_snapshot(gw, read_port, run_id: str) -> dict:
    """Build feature snapshots with v0.2 proxy classification."""
    logger.info("=== Step 2: Build v0.2 Feature Snapshot ===")
    svc = W2SFeatureSnapshotService(read_ports=read_port, gateway=gw)

    try:
        await gw._client.execute_query(
            "INSERT INTO w2s_backtest_run (run_id, strategy_id, strategy_version, run_type, start_date, end_date, status, started_at) VALUES ($1, 'weak_to_strong', $2, 'signal_validation', $3, $4, 'running', NOW()) ON CONFLICT (run_id) DO UPDATE SET status = 'running', started_at = NOW()",
            (run_id, STRATEGY_VERSION, START_DATE, END_DATE),
        )
    except Exception:
        pass

    result = await svc.build(
        run_id=run_id,
        strategy_version=STRATEGY_VERSION,
        start_date=START_DATE,
        end_date=END_DATE,
        force_rebuild=True,
    )
    print(f"Snapshots: {result['snapshot_count']} built, {result['written']} written")
    return result


async def step3_validate(gw, read_port, run_id: str) -> dict:
    """Build signals + validate forward returns + benchmark."""
    logger.info("=== Step 3: Build Signals ===")
    builder = W2SSignalBuilderService(gateway=gw)
    sig_result = await builder.build(run_id=run_id)
    print(f"Signals: {sig_result['signal_count']} built, {sig_result['written']} written")

    logger.info("=== Step 4: Validate Forward Returns ===")
    validator = W2SSignalValidationService(read_ports=read_port, gateway=gw)
    val_result = await validator.validate(run_id=run_id, look_forward_days=(1, 2, 3, 5))
    print(f"Validations: {val_result['validated_count']} processed, {val_result['written']} written")

    # Benchmark computation
    logger.info("=== Step 5: Compute Benchmarks ===")
    try:
        benchmark_data = await compute_benchmarks(gw, run_id)
    except Exception as exc:
        logger.warning("Benchmarks failed: %s", exc)
        benchmark_data = {"n_signals": 0, "error": str(exc)}

    # Candidate pool quality report
    logger.info("=== Step 6: Candidate Pool Quality Report ===")
    try:
        quality_data = await compute_candidate_pool_quality(gw, run_id)
    except Exception as exc:
        logger.warning("Quality report failed: %s", exc)
        quality_data = {}

    # Auction scorer calibration
    logger.info("=== Step 7: Auction Scorer Calibration ===")
    try:
        calibration_data = await compute_auction_calibration(gw, run_id)
    except Exception as exc:
        logger.warning("Calibration failed (non-blocking): %s", exc)
        calibration_data = {"error": str(exc), "real_auction_quantiles": {}, "proxy_quantiles": {}, "calibrated_thresholds": {}, "current_distribution": []}

    return {
        "signals": sig_result,
        "validation": val_result,
        "benchmarks": benchmark_data,
        "candidate_quality": quality_data,
        "auction_calibration": calibration_data,
    }


async def compute_benchmarks(gw, run_id: str) -> dict:
    """Compute market and subject benchmark returns."""
    # Market average returns for the same period
    market = await gw._client.execute_query(
        """SELECT AVG(next_3d_return) as mkt_ar3, AVG(next_5d_return) as mkt_ar5
           FROM strategy_signal_validation WHERE run_id = $1 AND next_3d_return IS NOT NULL""",
        (run_id,),
    )
    mkt = market[0] if market else {}

    # Subject benchmark: compute in Python from simpler queries
    sigs_with_subj = await gw._client.execute_query(
        "SELECT s.signal_id, s.subject_key FROM strategy_signal_daily s WHERE s.run_id = $1",
        (run_id,),
    )
    vals_simple = await gw._client.execute_query(
        "SELECT signal_id, next_3d_return, next_5d_return FROM strategy_signal_validation WHERE run_id = $1 AND next_3d_return IS NOT NULL",
        (run_id,),
    )
    val_by_id = {str(v["signal_id"]): v for v in vals_simple}

    # Group by subject_key
    subj_data: dict[str, list[float]] = {}
    for s in sigs_with_subj:
        sk = str(s.get("subject_key") or "")
        if not sk:
            continue
        v = val_by_id.get(str(s["signal_id"]))
        if v:
            subj_data.setdefault(sk, []).append(float(v["next_3d_return"] or 0))

    subject = [
        {"subject_key": sk, "n": len(rets), "subj_ar3": sum(rets)/len(rets), "subj_ar5": 0}
        for sk, rets in sorted(subj_data.items(), key=lambda x: -len(x[1]))[:10]
    ]

    # Compute excess vs subject (simple: signal return - subject avg return)
    subj_avgs: dict[str, float] = {}
    for sr in subject:
        subj_avgs[str(sr["subject_key"])] = float(sr["subj_ar3"] or 0)

    n_excess = 0
    sum_excess_3d = 0.0
    for s in sigs_with_subj:
        sk = str(s.get("subject_key") or "")
        v = val_by_id.get(str(s["signal_id"]))
        if v and sk:
            ar3 = float(v["next_3d_return"] or 0)
            subj_avg = subj_avgs.get(sk, 0)
            sum_excess_3d += ar3 - subj_avg
            n_excess += 1

    avg_excess_3d = sum_excess_3d / n_excess if n_excess > 0 else 0
    avg_excess_5d = 0  # simplified for v0.2

    n_signals = len(val_by_id)
    return {
        "n_signals": n_signals,
        "avg_ret_3d": float(mkt.get("mkt_ar3", 0) or 0),
        "avg_ret_5d": float(mkt.get("mkt_ar5", 0) or 0),
        "avg_excess_vs_subject_3d": avg_excess_3d,
        "avg_excess_vs_subject_5d": avg_excess_5d,
        "top_subjects": [
            {"subject_key": sr["subject_key"], "n": sr["n"],
             "ar3": float(sr["subj_ar3"] or 0), "ar5": float(sr["subj_ar5"] or 0)}
            for sr in subject
        ],
    }


async def compute_candidate_pool_quality(gw, run_id: str) -> dict:
    """Candidate pool quality: group by candidate_type, support_type, score buckets.

    Uses simple separate queries + Python join to avoid complex SQL.
    """
    # Load all snapshots + validation data
    snaps = await gw._client.execute_query(
        "SELECT stock_id, candidate_trade_date, candidate_type, support_type, weak_type, leader_role_proxy, pool_entry_type FROM w2s_backtest_feature_snapshot WHERE run_id = $1",
        (run_id,),
    )
    vals = await gw._client.execute_query(
        "SELECT stock_id, trade_date, next_1d_return, next_3d_return, next_5d_return, is_win_3d, is_win_5d, hit_limit_up_5d, loss_over_5pct FROM strategy_signal_validation WHERE run_id = $1 AND next_3d_return IS NOT NULL",
        (run_id,),
    )

    # Build lookup
    val_lookup: dict[tuple, dict] = {}
    for v in vals:
        key = (str(v["stock_id"]), str(v["trade_date"])[:10])
        val_lookup[key] = v

    # Join
    joined: list[dict] = []
    for s in snaps:
        key = (str(s["stock_id"]), str(s["candidate_trade_date"])[:10])
        v = val_lookup.get(key)
        if v:
            joined.append({**{f"f_{k}": s[k] for k in s}, **{f"v_{k}": v[k] for k in v}})

    def _group_by(dim: str) -> list[dict]:
        groups: dict[str, list] = {}
        for row in joined:
            key = str(row.get(f"f_{dim}") or "unknown")
            groups.setdefault(key, []).append(row)
        results = []
        for k, rows in sorted(groups.items(), key=lambda x: -len(x[1])):
            n = len(rows)
            ar1 = sum(float(r["v_next_1d_return"] or 0) for r in rows) / n
            ar3 = sum(float(r["v_next_3d_return"] or 0) for r in rows) / n
            ar5 = sum(float(r["v_next_5d_return"] or 0) for r in rows) / n
            wr3 = sum(1 for r in rows if r.get("v_is_win_3d")) / n
            wr5 = sum(1 for r in rows if r.get("v_is_win_5d")) / n
            results.append({"dim": k, "n": n, "ar1": ar1, "ar3": ar3, "ar5": ar5, "wr3": wr3, "wr5": wr5})
        return results

    return {
        "candidate_type": _group_by("candidate_type"),
        "support_type": _group_by("support_type"),
        "weak_type": _group_by("weak_type"),
        "leader_role_proxy": _group_by("leader_role_proxy"),
        "pool_entry_type": _group_by("pool_entry_type"),
    }


async def compute_auction_calibration(gw, run_id: str) -> dict:
    """Calibrate auction scorer using quantile analysis."""
    # Get auction scores from snapshots
    snaps = await gw._client.execute_query(
        "SELECT auction_score, confirm_level, confirm_source, pool_entry_type, stock_id, candidate_trade_date FROM w2s_backtest_feature_snapshot WHERE run_id = $1",
        (run_id,),
    )
    # Get returns from validations
    vals = await gw._client.execute_query(
        "SELECT stock_id, trade_date, next_3d_return, is_win_3d FROM strategy_signal_validation WHERE run_id = $1",
        (run_id,),
    )
    # Join in Python
    val_map: dict[tuple, dict] = {}
    for v in vals:
        key = (str(v["stock_id"]), str(v["trade_date"])[:10])
        val_map[key] = v

    scores: list[dict] = []
    for s in snaps:
        key = (str(s["stock_id"]), str(s["candidate_trade_date"])[:10])
        v = val_map.get(key, {})
        scores.append({
            "auction_score": float(s["auction_score"] or 0),
            "confirm_level": s["confirm_level"],
            "confirm_source": s["confirm_source"],
            "pool_entry_type": s["pool_entry_type"],
            "next_3d_return": float(v.get("next_3d_return", 0) or 0) if v else 0,
            "is_win_3d": bool(v.get("is_win_3d", False)) if v else False,
        })

    # Separate real auction and proxy scores
    real_scores = [float(r["auction_score"] or 0) for r in scores if r["confirm_source"] in ("real_auction", "auction_snapshot")]
    proxy_scores = [float(r["auction_score"] or 0) for r in scores if r["confirm_source"] == "daily_open_proxy"]

    def quantiles(vals: list[float]) -> dict:
        if not vals:
            return {}
        s = sorted(vals)
        n = len(s)
        return {
            "min": s[0], "p20": s[int(n*0.2)], "p40": s[int(n*0.4)],
            "p50": s[int(n*0.5)], "p60": s[int(n*0.6)], "p80": s[int(n*0.8)], "max": s[-1],
            "n": n,
        }

    # Compute calibrated thresholds from real_auction data (if available)
    real_q = quantiles(real_scores)
    calibrated = {}
    if real_q and real_q.get("n", 0) >= 20:
        calibrated = {
            "A_threshold": real_q.get("p80", 75),
            "B_threshold": real_q.get("p60", 60),
            "C_threshold": real_q.get("p40", 40),
            "method": "quantile_from_real_auction",
            "note": "top 20%=A, 20-40%=B, 40-60%=C, bottom 40%=X",
        }
    else:
        # Fall back to proxy scores if real data too small
        proxy_q = quantiles(proxy_scores)
        if proxy_q and proxy_q.get("n", 0) >= 50:
            calibrated = {
                "A_threshold": proxy_q.get("p80", 75),
                "B_threshold": proxy_q.get("p60", 60),
                "C_threshold": proxy_q.get("p40", 40),
                "method": "quantile_from_proxy",
                "note": "real_auction sample too small, using proxy distribution",
            }

    # Current distribution: group by confirm_level from scores data
    from collections import Counter
    level_counts: dict[tuple, Counter] = {}
    for s in scores:
        key = (str(s["confirm_level"]), str(s["confirm_source"]))
        level_counts.setdefault(key, {"n": 0, "ar3_sum": 0.0, "n_ret": 0})
        level_counts[key]["n"] += 1
        if s.get("next_3d_return", 0):
            level_counts[key]["ar3_sum"] += float(s["next_3d_return"])
            level_counts[key]["n_ret"] += 1

    dist = [
        {"level": k[0], "source": k[1],
         "n": v["n"],
         "ar3": v["ar3_sum"] / v["n_ret"] if v["n_ret"] > 0 else 0}
        for k, v in sorted(level_counts.items(), key=lambda x: x[0][0])
    ]

    return {
        "real_auction_quantiles": real_q,
        "proxy_quantiles": quantiles(proxy_scores),
        "calibrated_thresholds": calibrated,
        "current_distribution": [
            {"level": r["confirm_level"], "source": r["confirm_source"],
             "n": r["n"], "ar3": float(r["ar3"] or 0)}
            for r in dist
        ],
    }


async def report(step1: dict, step3: dict, run_id: str) -> None:
    """Print comprehensive v0.2 report."""
    print("\n" + "=" * 80)
    print("  W2S v0.2 CALIBRATION REPORT")
    print("=" * 80)
    print(f"  Run ID:       {run_id}")
    print(f"  Strategy:     {STRATEGY_VERSION}")
    print(f"  Range:        {START_DATE} → {END_DATE}")
    print(f"  Candidates:   {step1['candidates']} rows, {step1['candidate_dates']} dates")
    s3 = step3.get("validation", {})
    print(f"  Validated:    {s3.get('validated_count', 0)} signals")

    # Benchmark
    bm = step3.get("benchmarks", {})
    print(f"\n{'─' * 80}")
    print("  BENCHMARK RETURNS (v0.2)")
    print(f"{'─' * 80}")
    print(f"  N signals:                 {bm.get('n_signals', 0)}")
    print(f"  Avg 3d return:             {bm.get('avg_ret_3d', 0):.3%}")
    print(f"  Avg 5d return:             {bm.get('avg_ret_5d', 0):.3%}")
    print(f"  Avg excess vs subject 3d:  {bm.get('avg_excess_vs_subject_3d', 0):.3%}")
    print(f"  Avg excess vs subject 5d:  {bm.get('avg_excess_vs_subject_5d', 0):.3%}")

    if bm.get("top_subjects"):
        print(f"\n  Top subjects:")
        for s in bm["top_subjects"][:5]:
            print(f"    {s['subject_key']}: N={s['n']} AR3d={s['ar3']:.3%} AR5d={s['ar5']:.3%}")

    # Candidate pool quality
    cq = step3.get("candidate_quality", {})
    print(f"\n{'─' * 80}")
    print("  CANDIDATE POOL QUALITY (v0.2)")
    print(f"{'─' * 80}")

    for dim_name in ["pool_entry_type", "candidate_type", "support_type", "weak_type", "leader_role_proxy"]:
        data = cq.get(dim_name, [])
        if not data:
            continue
        print(f"\n  By {dim_name}:")
        print(f"  {'Group':<30} {'N':>5} {'WR3d':>7} {'AR3d':>8} {'AR5d':>8}")
        print(f"  {'─' * 30} {'─' * 5} {'─' * 7} {'─' * 8} {'─' * 8}")
        for r in data[:10]:
            wr3 = f"{r.get('wr3', 0):.1%}" if r.get('wr3') is not None else "N/A"
            ar3 = f"{r.get('ar3', 0):.3%}" if r.get('ar3') is not None else "N/A"
            ar5 = f"{r.get('ar5', 0):.3%}" if r.get('ar5') is not None else "N/A"
            print(f"  {str(r['dim'])[:30]:<30} {int(r.get('n', 0)):>5} {wr3:>7} {ar3:>8} {ar5:>8}")

    # Auction calibration
    cal = step3.get("auction_calibration", {})
    print(f"\n{'─' * 80}")
    print("  AUCTION SCORER CALIBRATION (v0.2)")
    print(f"{'─' * 80}")

    real_q = cal.get("real_auction_quantiles", {})
    if real_q:
        print(f"\n  Real auction raw_score distribution (N={real_q.get('n', 0)}):")
        print(f"    min={real_q.get('min', 0):.1f} p20={real_q.get('p20', 0):.1f} p40={real_q.get('p40', 0):.1f} p50={real_q.get('p50', 0):.1f} p60={real_q.get('p60', 0):.1f} p80={real_q.get('p80', 0):.1f} max={real_q.get('max', 0):.1f}")

    proxy_q = cal.get("proxy_quantiles", {})
    if proxy_q:
        print(f"\n  Proxy raw_score distribution (N={proxy_q.get('n', 0)}):")
        print(f"    min={proxy_q.get('min', 0):.1f} p20={proxy_q.get('p20', 0):.1f} p40={proxy_q.get('p40', 0):.1f} p50={proxy_q.get('p50', 0):.1f} p60={proxy_q.get('p60', 0):.1f} p80={proxy_q.get('p80', 0):.1f} max={proxy_q.get('max', 0):.1f}")

    calib = cal.get("calibrated_thresholds", {})
    if calib:
        print(f"\n  Calibrated thresholds ({calib.get('method', 'unknown')}):")
        print(f"    A >= {calib.get('A_threshold', 75):.1f}")
        print(f"    B >= {calib.get('B_threshold', 60):.1f}")
        print(f"    C >= {calib.get('C_threshold', 40):.1f}")
        print(f"    X <  {calib.get('C_threshold', 40):.1f}")
        print(f"    Note: {calib.get('note', '')}")

    # Current vs expected distribution
    dist = cal.get("current_distribution", [])
    if dist:
        print(f"\n  Current level distribution:")
        for d in dist:
            print(f"    {d['level']:25s} {d['source']:20s} N={d['n']:>4d} AR3d={d['ar3']:.3%}")

    print(f"\n{'═' * 80}")
    print("  v0.2 KEY FINDINGS")
    print(f"{'═' * 80}")

    # Assess proxy semantics fix
    proxy_types = {d["level"] for d in dist if d["level"].startswith("proxy_")}
    print(f"\n  P0: Proxy semantics: {len(proxy_types)} distinct levels")
    for pt in sorted(proxy_types):
        count = sum(d["n"] for d in dist if d["level"] == pt)
        print(f"      {pt}: {count} signals")

    # Assess benchmark
    excess_3d = bm.get("avg_excess_vs_subject_3d", 0)
    if excess_3d > 0:
        print(f"\n  P2: Excess return vs subject: {excess_3d:.3%} (positive = value-add over subject avg)")
    else:
        print(f"\n  P2: Excess return vs subject: {excess_3d:.3%} (candidate pool underperforms subject avg)")

    print(f"\n  ⚠️  v0.2 is a RESEARCH version — not a trading strategy.")
    print(f"  → If calibration shows A/B/C/X monotonicity, upgrade to v0.3.")
    print(f"{'═' * 80}\n")

    # Save report
    report_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "evaluate_service", "data", "results", "phase0_reports",
        f"w2s_v0.2_{run_id}.json",
    )
    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w") as f:
        json.dump({
            "run_id": run_id, "strategy_version": STRATEGY_VERSION,
            "step1": step1,
            "benchmarks": bm,
            "candidate_quality": cq,
            "auction_calibration": cal,
        }, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Full report: {report_path}")


async def main() -> None:
    run_id = _create_run_id()
    print(f"\n{'▓' * 80}")
    print(f"  W2S v0.2 CALIBRATION RUN")
    print(f"  Run ID:     {run_id}")
    print(f"  Strategy:   {STRATEGY_VERSION}")
    print(f"  Range:      {START_DATE} → {END_DATE}")
    print(f"{'▓' * 80}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    facade = _ReplayDatabaseStockFacade(gw)
    read_port = StockReadGatewayAdapter(facade)

    try:
        step1 = await step1_data_check(gw)
        await step2_build_snapshot(gw, read_port, run_id)
        step3 = await step3_validate(gw, read_port, run_id)
        await report(step1, step3, run_id)

        try:
            await gw._client.execute_query(
                "UPDATE w2s_backtest_run SET status='completed', completed_at=NOW() WHERE run_id=$1", (run_id,))
        except Exception:
            pass
    finally:
        close_fn = getattr(gw, "close", None)
        if callable(close_fn):
            await close_fn()


if __name__ == "__main__":
    asyncio.run(main())

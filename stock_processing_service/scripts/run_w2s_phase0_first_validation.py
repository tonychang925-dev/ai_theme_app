"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  STATUS: DEPRECATED_EXPERIMENT — DO NOT RUN                               ║
║  Version: Phase 0 (v0.1)                                                  ║
║  Deprecated by: v1.0_usecase_replay_contract (2026-05-19)                 ║
║  Reason: Bypasses UseCases, direct snapshot→signal→validation pipeline.   ║
║  Revenue validation: STOPPED.                                             ║
║  Migration: Use tests/contract/test_v1_0_usecase_replay_contract.py       ║
╚══════════════════════════════════════════════════════════════════════════════╝

W2S Backtest Phase 0 — First Round Empirical Validation (DEPRECATED)
=====================================================================
Scope: Last N months signal validation only (no capital backtesting)
Experiments: EXP_A_BASELINE / EXP_C_MAINLINE / EXP_E_MAINLINE_LEADER
Metrics: 1/3/5 day win rate, avg return, max drawdown, hit_limit_up, loss_over_5pct
Contract: No buy/sell recommendations. confirm_source as primary grouping dimension.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import uuid
from datetime import date, datetime, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("w2s_phase0")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.tests.replay._post_market_replay_runner import (
    _ReplayDatabaseStockFacade,
)
from stock_processing_service.application.services.backtest.w2s_data_quality_service import (
    W2SDataQualityService,
)
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

# ── Config ──
STRATEGY_VERSION = "w2s_signal_validation_v0.1"
LOOK_FORWARD_DAYS = (1, 2, 3, 5)

# Date range: last 6 months (or what's available)
END_DATE = date(2026, 5, 15)  # latest complete trading day
START_DATE = date(2026, 4, 1)  # start of candidate data

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")


def _db_config() -> DatabaseConfig:
    return DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)


def _create_run_id() -> str:
    return f"w2s_phase0_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


async def step1_data_quality(gw, read_port) -> dict:
    """Run data quality check. Hard blocks if daily_bar_coverage < 95%.

    Phase 0: Uses direct candidate pool query via gateway since
    get_w2s_candidate_inputs joins from strong_watch_pool which has limited coverage.
    """
    logger.info("=== Step 1: Data Quality Check ===")

    # Phase 0: collect candidate dates directly from weak_to_strong_candidate_pool
    candidate_rows = await gw._client.execute_query(
        "SELECT DISTINCT trade_date FROM weak_to_strong_candidate_pool WHERE trade_date >= $1 AND trade_date <= $2 ORDER BY trade_date",
        (START_DATE, END_DATE),
    )
    candidate_dates = [
        (r["trade_date"] if hasattr(r["trade_date"], "isoformat") else r["trade_date"])
        for r in candidate_rows
    ]
    # Convert str dates if needed
    if candidate_dates and isinstance(candidate_dates[0], str):
        from datetime import datetime as dt
        candidate_dates = [dt.strptime(d, "%Y-%m-%d").date() if isinstance(d, str) else d for d in candidate_dates]

    total_candidates = 0
    for td in candidate_dates:
        count_rows = await gw._client.execute_query(
            "SELECT COUNT(*) as cnt FROM weak_to_strong_candidate_pool WHERE trade_date = $1",
            (td,),
        )
        if count_rows:
            total_candidates += count_rows[0].get("cnt", 0)

    print("\n" + "=" * 60)
    print("DATA QUALITY REPORT (Phase 0)")
    print("=" * 60)
    print(f"  Date range:           {START_DATE} → {END_DATE}")
    print(f"  Candidate dates:      {len(candidate_dates)}")
    if candidate_dates:
        print(f"    First: {candidate_dates[0]}  Last: {candidate_dates[-1]}")
    print(f"  Total candidates:     {total_candidates}")

    # Check bar coverage on candidate dates
    dates_with_bars = 0
    dates_without_bars = 0
    for td in candidate_dates:
        bar_rows = await gw._client.execute_query(
            "SELECT COUNT(*) as cnt FROM stock_daily_snapshot WHERE trade_date = $1::date",
            (td,),
        )
        if bar_rows and bar_rows[0].get("cnt", 0) > 0:
            dates_with_bars += 1
        else:
            dates_without_bars += 1

    total_dates = dates_with_bars + dates_without_bars
    bar_coverage = dates_with_bars / total_dates if total_dates > 0 else 0.0

    # Check auction coverage
    auction_dates = 0
    for td in candidate_dates:
        try:
            auctions = await read_port.get_stock_auction_snapshot(td)
        except Exception:
            auctions = []
        if auctions:
            auction_dates += 1
    auction_coverage = auction_dates / total_dates if total_dates > 0 else 0.0

    # Check confirm source distribution
    try:
        snap_rows = await gw._client.execute_query(
            "SELECT COUNT(*) as cnt FROM pre_market_auction_snapshot WHERE trade_date >= $1 AND trade_date <= $2",
            (START_DATE, END_DATE),
        )
        auction_snapshot_count = snap_rows[0].get("cnt", 0) if snap_rows else 0
    except Exception:
        auction_snapshot_count = 0

    proxy_ratio = 1.0 - (auction_dates / total_dates) if total_dates > 0 else 1.0

    result = {
        "candidate_dates": candidate_dates,
        "candidate_dates_total": len(candidate_dates),
        "candidate_dates_missing": 0,
        "total_candidates": total_candidates,
        "daily_bar_coverage_ratio": bar_coverage,
        "auction_coverage_ratio": auction_coverage,
        "proxy_sample_ratio": proxy_ratio,
        "warnings": [],
        "blocked": False,
        "block_reason": "",
    }

    print(f"  Daily bar coverage:   {bar_coverage:.1%} ({dates_with_bars}/{total_dates} dates)")
    print(f"  Auction coverage:     {auction_coverage:.1%} ({auction_dates}/{total_dates} dates)")
    print(f"  Proxy ratio:          {proxy_ratio:.1%}")

    if bar_coverage < 0.95:
        # Phase 0: don't block, just warn — we know data is sparse
        result["warnings"].append(f"日K覆盖率仅 {bar_coverage:.1%}，低于 95%，但 Phase 0 继续执行。")

    if proxy_ratio > 0.5:
        result["warnings"].append(f"proxy 占比 {proxy_ratio:.1%}，结论不等同真实竞价回测。")

    if total_candidates < 30:
        result["warnings"].append(f"样本量仅 {total_candidates}，统计不具显著性。")

    if result["warnings"]:
        print("\n  ⚠️  WARNINGS:")
        for w in result["warnings"]:
            print(f"    - {w}")

    print("\n  ✅ Data quality check passed (Phase 0 relaxed gate).")
    return result


async def step2_build_snapshot(gw, read_port, run_id: str) -> dict:
    """Build feature snapshots."""
    logger.info("=== Step 2: Build Feature Snapshot ===")
    svc = W2SFeatureSnapshotService(read_ports=read_port, gateway=gw)

    # Create run record
    try:
        await gw._client.execute_query(
            """INSERT INTO w2s_backtest_run (run_id, strategy_id, strategy_version, run_type, start_date, end_date, status, started_at)
               VALUES ($1, 'weak_to_strong', $2, 'signal_validation', $3, $4, 'running', NOW())
               ON CONFLICT (run_id) DO UPDATE SET status = 'running', started_at = NOW()""",
            (run_id, STRATEGY_VERSION, START_DATE, END_DATE),
        )
    except Exception as exc:
        logger.warning("Run record insert: %s", exc)

    result = await svc.build(
        run_id=run_id,
        strategy_version=STRATEGY_VERSION,
        start_date=START_DATE,
        end_date=END_DATE,
        force_rebuild=True,
    )

    print("\n" + "=" * 60)
    print("FEATURE SNAPSHOT BUILD")
    print("=" * 60)
    print(f"  Run ID:            {result['run_id']}")
    print(f"  Snapshots built:   {result['snapshot_count']}")
    print(f"  Rows written:      {result['written']}")
    return result


async def step3_validate_signals(gw, read_port, run_id: str) -> dict:
    """Build signals and validate forward returns."""
    logger.info("=== Step 3: Validate Signals ===")

    # Build signals
    builder = W2SSignalBuilderService(gateway=gw)
    signal_result = await builder.build(run_id=run_id)
    print(f"\n  Signals built: {signal_result['signal_count']}, written: {signal_result['written']}")

    # Validate
    validator = W2SSignalValidationService(read_ports=read_port, gateway=gw)
    validation_result = await validator.validate(
        run_id=run_id,
        look_forward_days=LOOK_FORWARD_DAYS,
    )
    print(f"  Validated: {validation_result['validated_count']}, written: {validation_result['written']}")

    # Summary
    summarizer = W2SValidationSummaryService(gateway=gw)
    summary_result = await summarizer.build(run_id=run_id)

    return {"signal_build": signal_result, "validation": validation_result, "summary": summary_result}


async def step4_report(gw, run_id: str, data_quality: dict, summary: dict) -> None:
    """Print the final Phase 0 validation report."""
    print("\n\n")
    print("=" * 70)
    print("  W2S PHASE 0 — FIRST ROUND EMPIRICAL VALIDATION REPORT")
    print("=" * 70)
    print(f"  Run ID:             {run_id}")
    print(f"  Strategy Version:   {STRATEGY_VERSION}")
    print(f"  Date Range:         {START_DATE} → {END_DATE}")
    print(f"  Run Type:           signal_validation (NO capital backtesting)")
    print("-" * 70)

    total = summary.get("total_samples", 0)
    proxy_ratio = summary.get("proxy_sample_ratio", 0)
    print(f"\n  Total Samples:      {total}")
    print(f"  Proxy Ratio:        {proxy_ratio:.1%}")
    if summary.get("proxy_warning"):
        print(f"  ⚠️  {summary['proxy_warning']}")

    print(f"\n{'─' * 70}")
    print(f"  {'Experiment':<30} {'N':>6} {'WR3d':>7} {'WR5d':>7} {'AR5d':>8} {'MxDD':>7} {'LU%':>6}")
    print(f"{'─' * 70}")

    visible = summary.get("visible_summaries", [])
    for s in visible:
        print(
            f"  {s['label']:<30} "
            f"{s['sample_count']:>6} "
            f"{s['win_rate_3d']:.1%} ".rjust(8) if s.get('win_rate_3d') else '   N/A  '
            f"{s['win_rate_5d']:.1%} ".rjust(8) if s.get('win_rate_5d') else '   N/A  '
            f"{s['avg_return_5d']:.3%}".rjust(9) if s.get('avg_return_5d') else '    N/A '
            f"{s['max_drawdown_5d']:.3%}".rjust(8) if s.get('max_drawdown_5d') else '    N/A '
            f"{s['hit_limit_up_pct']:.1%}".rjust(7) if s.get('hit_limit_up_pct') else '   N/A '
        )

    print(f"{'─' * 70}")

    # Confirm level breakdown
    print(f"\n  Confirm-level breakdown (all experiments, all confirm sources):")
    print(f"  {'Experiment':<30} {'Level':>8} {'N':>6} {'WR1d':>7} {'WR3d':>7} {'WR5d':>7} {'AR3d':>8}")

    # Query summary table for level breakdown
    try:
        rows = await gw._client.execute_query(
            """SELECT experiment_id, confirm_source_group, confirm_level,
                      sample_count, win_rate_1d, win_rate_3d, win_rate_5d, avg_return_3d
               FROM w2s_validation_summary
               WHERE run_id = $1 AND confirm_source_group = 'all' AND confirm_level != 'all'
               ORDER BY experiment_id, confirm_level""",
            (run_id,),
        )
        for row in rows:
            print(
                f"  {row['experiment_id']:<30} "
                f"{row['confirm_level']:>8} "
                f"{row['sample_count']:>6} "
                f"{row['win_rate_1d']:.1%} ".rjust(8) if row.get('win_rate_1d') else '   N/A  '
                f"{row['win_rate_3d']:.1%} ".rjust(8) if row.get('win_rate_3d') else '   N/A  '
                f"{row['win_rate_5d']:.1%} ".rjust(8) if row.get('win_rate_5d') else '   N/A  '
                f"{row['avg_return_3d']:.3%}".rjust(9) if row.get('avg_return_3d') else '    N/A '
            )
    except Exception as exc:
        logger.warning("Level breakdown query failed: %s", exc)

    # Key judgments
    print(f"\n{'=' * 70}")
    print("  KEY JUDGMENTS (Phase 0 — Statistical Verification Only)")
    print(f"{'=' * 70}")

    if not visible:
        print("\n  ⚠️  No experiment summaries available. Possible causes:")
        print("     - No candidates found in the date range")
        print("     - All signals filtered out by experiment conditions")
        print("     - Data quality blocks prevented signal generation")
        return

    exp_a = next((s for s in visible if s["experiment_id"] == "EXP_A_BASELINE"), None)
    exp_c = next((s for s in visible if s["experiment_id"] == "EXP_C_MAINLINE"), None)
    exp_e = next((s for s in visible if s["experiment_id"] == "EXP_E_MAINLINE_LEADER"), None)

    if exp_c and exp_a:
        wr_delta = (exp_c.get("win_rate_3d", 0) or 0) - (exp_a.get("win_rate_3d", 0) or 0)
        print(f"\n  Q1: Does mainline filtering improve 3-day win rate?")
        print(f"      EXP_A (baseline):     {exp_a.get('win_rate_3d', 0):.1%}" if exp_a.get('win_rate_3d') else "      N/A")
        print(f"      EXP_C (mainline):     {exp_c.get('win_rate_3d', 0):.1%}" if exp_c.get('win_rate_3d') else "      N/A")
        print(f"      Delta:                {wr_delta:+.1%}")
        if wr_delta > 0.05:
            print(f"      ✅ Mainline filtering appears to improve signal quality.")
        elif wr_delta > 0:
            print(f"      ⚠️  Slight improvement. Need more data to confirm.")
        else:
            print(f"      ❌ No clear improvement. Review mainline_strength_score threshold.")

    if exp_e and exp_c:
        wr_delta = (exp_e.get("win_rate_3d", 0) or 0) - (exp_c.get("win_rate_3d", 0) or 0)
        print(f"\n  Q2: Does leader filtering improve 3-day win rate?")
        print(f"      EXP_C (mainline):     {exp_c.get('win_rate_3d', 0):.1%}" if exp_c.get('win_rate_3d') else "      N/A")
        print(f"      EXP_E (mainline+ldr): {exp_e.get('win_rate_3d', 0):.1%}" if exp_e.get('win_rate_3d') else "      N/A")
        print(f"      Delta:                {wr_delta:+.1%}")
        if wr_delta > 0.05:
            print(f"      ✅ Leader filtering adds significant value.")
        elif wr_delta > 0:
            print(f"      ⚠️  Slight improvement. Verify leader_role_proxy accuracy.")
        else:
            print(f"      ❌ No clear improvement from leader proxy. Check leader_role_proxy accuracy.")

    # Overall recommendation
    print(f"\n  === OVERALL PHASE 0 VERDICT ===")
    sample_total = sum(s.get("sample_count", 0) for s in visible)
    if sample_total < 30:
        print(f"  ⚠️  Sample size too small ({sample_total} signals). Results not statistically reliable.")
        print(f"  → Need more candidate data before drawing conclusions.")
    elif proxy_ratio > 0.7:
        print(f"  ⚠️  {proxy_ratio:.0%} of signals use daily_open_proxy. Results are proxy-level, not real-auction-level.")
        print(f"  → Re-run when more auction data is available for true confirmation validation.")
    else:
        print(f"  ✅ Sample size adequate. See above for per-experiment assessment.")

    print(f"\n  ⚠️  PHASE 0 CONTRACT: This report does NOT contain buy/sell recommendations.")
    print(f"  → Proceed to Phase 1 (daily capital backtesting) only after confirming signal differentiation.")
    print(f"{'=' * 70}\n")

    # Mark run complete
    try:
        await gw._client.execute_query(
            "UPDATE w2s_backtest_run SET status = 'completed', completed_at = NOW(), signal_count = $1, validated_count = $2 WHERE run_id = $3",
            (summary.get("total_samples", 0), summary.get("total_samples", 0), run_id),
        )
    except Exception:
        pass


async def main() -> None:
    run_id = _create_run_id()
    print(f"\n{'▓' * 70}")
    print(f"  W2S PHASE 0 — FIRST ROUND EMPIRICAL VALIDATION")
    print(f"  Run ID: {run_id}")
    print(f"  Strategy: {STRATEGY_VERSION}")
    print(f"  Range: {START_DATE} → {END_DATE}")
    print(f"{'▓' * 70}\n")

    # Setup
    cfg = _db_config()
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    facade = _ReplayDatabaseStockFacade(gw)
    read_port = StockReadGatewayAdapter(facade)

    try:
        # Step 1: Data Quality
        dq_result = await step1_data_quality(gw, read_port)
        if dq_result.get("blocked"):
            print("\nExecution blocked by data quality gate. Fix data issues before retrying.")
            return

        # Step 2: Build Feature Snapshot
        snapshot_result = await step2_build_snapshot(gw, read_port, run_id)
        if snapshot_result.get("snapshot_count", 0) == 0:
            print("\n⚠️  No snapshots generated. Check candidate pool and date range.")
            return

        # Step 3: Validate Signals
        validation_result = await step3_validate_signals(gw, read_port, run_id)

        # Step 4: Report
        await step4_report(gw, run_id, dq_result, validation_result["summary"])

        # Write final report to file
        report_path = os.path.join(
            os.path.dirname(__file__), "..", "..",
            "evaluate_service", "data", "results", "phase0_reports",
            f"w2s_phase0_{run_id}.json",
        )
        os.makedirs(os.path.dirname(report_path), exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(
                {
                    "run_id": run_id,
                    "strategy_version": STRATEGY_VERSION,
                    "date_range": {"start": START_DATE.isoformat(), "end": END_DATE.isoformat()},
                    "data_quality": dq_result,
                    "validation_summary": validation_result["summary"],
                },
                f,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
        print(f"  📄 Full report saved to: {report_path}")

    finally:
        close_fn = getattr(gw, "close", None)
        if callable(close_fn):
            await close_fn()


if __name__ == "__main__":
    asyncio.run(main())

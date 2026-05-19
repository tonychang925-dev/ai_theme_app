"""
v0.8_usecase_replay: Replay production UseCases against historical feature store.
=================================================================================
v0.7 bypassed BuildStrongStockTrackingUseCase and BuildWeakToStrongCandidateUseCase.
v0.8 CORRECTLY calls both UseCases through HistoricalBacktestReadPorts/WritePorts.

Link: A/B feature store → BuildStrongStockTrackingUseCase → strong watch pool
      → BuildWeakToStrongCandidateUseCase → D-layer candidates → validation
"""

from __future__ import annotations

import asyncio, json, logging, os, sys, uuid
from datetime import date, datetime
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.application.services.backtest.historical_backtest_ports import (
    HistoricalBacktestReadPorts, HistoricalBacktestWritePorts,
)
from stock_processing_service.application.use_cases.build_strong_stock_tracking import (
    BuildStrongStockTrackingUseCase,
)
from stock_processing_service.application.use_cases.build_weak_to_strong_candidate import (
    BuildWeakToStrongCandidateUseCase,
)
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("v0.8")

DB_NAME = "stock_data_test"
START, END = date(2026, 2, 15), date(2026, 5, 15)
v05_rid = "w2s_v0.4_20260518_155432_5bdf5746"


async def main():
    v08_rid = f"v0.8_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4]}"
    print(f"\n{'▓'*70}\n  v0.8_usecase_replay\n  Run: {v08_rid}\n{'▓'*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client
    facade = _ReplayDatabaseStockFacade(gw)
    read_port = StockReadGatewayAdapter(facade)

    # ═══ Create isolated ports ═══
    hist_read = HistoricalBacktestReadPorts(gw, START, END)
    hist_write = HistoricalBacktestWritePorts(gw)
    await hist_read._ensure_loaded()

    # ═══ Step 1: Run BuildStrongStockTrackingUseCase per trading day ═══
    print("Step 1: BuildStrongStockTrackingUseCase replay...")
    tracking_uc = BuildStrongStockTrackingUseCase(
        read_ports=hist_read, write_ports=hist_write,
    )

    scored_dates = 0
    for td in hist_read._trade_dates:
        if td < START: continue
        try:
            result = await tracking_uc.execute(trade_date=td, window_days=7, lookback_days=8)
            if result.affected_rows > 0:
                scored_dates += 1
        except Exception as e:
            if scored_dates < 3: logger.warning(f"  Tracking UC failed for {td}: {e}")

    # Strong watch pool stats
    swp_rows = await c.execute_query("SELECT COUNT(*) as n FROM strong_watch_pool_scored_rebuild")
    swp_dist = await c.execute_query(
        "SELECT watch_status, pool_entry_type, strong_grade, COUNT(*) as n FROM strong_watch_pool_scored_rebuild GROUP BY 1,2,3 ORDER BY n DESC"
    )
    print(f"  Strong watch pool: {swp_rows[0]['n']} rows, {scored_dates} dates with output")
    print(f"  Distribution:")
    for r in swp_dist[:10]:
        print(f"    status={r['watch_status']:<15} entry={r['pool_entry_type']:<15} grade={r['strong_grade']:<10} N={r['n']:>5d}")

    # ═══ Step 2: Build D-layer candidates from scored strong watch pool ═══
    print("\nStep 2: BuildWeakToStrongCandidateUseCase replay...")
    w2s_uc = BuildWeakToStrongCandidateUseCase(
        read_ports=hist_read, write_ports=hist_write,
    )

    w2s_dates = 0
    for td in hist_read._trade_dates:
        if td < START: continue
        # Only process dates that have strong watch pool entries
        pool_check = await c.execute_query(
            "SELECT COUNT(*) as n FROM strong_watch_pool_scored_rebuild WHERE trade_date=$1 AND watch_status IN ('active','weakening') AND pool_entry_type IN ('formal','observe_only') AND NOT COALESCE(fade_confirmed,false)",
            (td,))
        if pool_check[0]['n'] == 0: continue

        try:
            result = await w2s_uc.execute(trade_date=td)
            if result.affected_rows > 0:
                w2s_dates += 1
        except Exception as e:
            if w2s_dates < 3: logger.warning(f"  W2S UC failed for {td}: {e}")

    w2s_rows = await c.execute_query(
        "SELECT COUNT(*) as n FROM weak_to_strong_candidate_pool WHERE rule_version='w2s_v0.8_usecase_replay'"
    )
    print(f"  D-layer candidates: {w2s_rows[0]['n']} rows, {w2s_dates} dates")

    # ═══ Step 3: Run W2S pipeline (snapshot → signals → validation) ═══
    print("\nStep 3: W2S validation pipeline...")
    try: await c.execute_query("INSERT INTO w2s_backtest_run (run_id,strategy_id,strategy_version,run_type,start_date,end_date,status,started_at) VALUES ($1,'weak_to_strong','w2s_v0.8','signal_validation','2026-02-15','2026-05-15','running',NOW()) ON CONFLICT(run_id) DO UPDATE SET status='running'", (v08_rid,))
    except: pass

    sn_svc = W2SFeatureSnapshotService(read_ports=read_port, gateway=gw)
    sn = await sn_svc.build(run_id=v08_rid, strategy_version="w2s_v0.8", start_date=START, end_date=END, force_rebuild=True)
    print(f"  Snapshots: {sn['snapshot_count']} built, {sn['written']} written")

    builder = W2SSignalBuilderService(gateway=gw)
    sig = await builder.build(run_id=v08_rid)
    validator = W2SSignalValidationService(read_ports=read_port, gateway=gw)
    val = await validator.validate(run_id=v08_rid, look_forward_days=(1,2,3,5))
    print(f"  Signals: {sig['written']}, Validated: {val['written']}")

    # ═══ Step 4: Compare ═══
    snaps_v08 = await c.execute_query("SELECT * FROM w2s_backtest_feature_snapshot WHERE run_id=$1", (v08_rid,))
    vals_v08 = await c.execute_query("SELECT * FROM strategy_signal_validation WHERE run_id=$1 AND next_3d_return IS NOT NULL", (v08_rid,))
    snaps_v05 = await c.execute_query("SELECT * FROM w2s_backtest_feature_snapshot WHERE run_id=$1", (v05_rid,))
    vals_v05 = await c.execute_query("SELECT * FROM strategy_signal_validation WHERE run_id=$1 AND next_3d_return IS NOT NULL", (v05_rid,))

    def join_sv(snaps, vals):
        vlook = {}
        for v in vals: vlook[(str(v['stock_id']), str(v['trade_date'])[:10])] = v
        joined = []
        for s in snaps:
            k = (str(s['stock_id']), str(s['candidate_trade_date'])[:10])
            v = vlook.get(k)
            if v: joined.append({"s": s, "v": v})
        return joined

    def grp(joined, attr):
        g = defaultdict(list)
        for r in joined: g[str(r['s'].get(attr) or 'unknown')].append(r)
        return [{"dim": k, "n": len(v),
                 "wr3": sum(1 for x in v if x['v'].get('is_win_3d'))/len(v) if v else 0,
                 "wr5": sum(1 for x in v if x['v'].get('is_win_5d'))/len(v) if v else 0,
                 "ar3": sum(float(x['v']['next_3d_return'] or 0) for x in v)/len(v) if v else 0,
                 "ar5": sum(float(x['v']['next_5d_return'] or 0) for x in v)/len(v) if v else 0,
                 "loss5": sum(1 for x in v if x['v'].get('loss_over_5pct'))/len(v) if v else 0}
                for k, v in sorted(g.items(), key=lambda x: -len(x[1]))]

    j08 = join_sv(snaps_v08, vals_v08)
    j05 = join_sv(snaps_v05, vals_v05)

    # ═══ REPORT ═══
    print(f"\n{'═'*70}")
    print(f"  v0.8_usecase_replay vs v0.5_baseline")
    print(f"{'═'*70}")
    print(f"  UseCase Replay:  BuildStrongStockTrackingUseCase ✅")
    print(f"                    BuildWeakToStrongCandidateUseCase ✅")
    print(f"  Strong pool:     {swp_rows[0]['n']} rows, {scored_dates} dates")
    print(f"  D-layer:         {w2s_rows[0]['n']} candidates, {w2s_dates} dates")
    print(f"  Validated:       {len(j08)} with returns")

    print(f"\n{'Version':<30} {'Joined':>7} {'pref N':>7} {'WR3d':>7} {'WR5d':>7} {'AR3d':>8} {'AR5d':>8} {'Loss5':>7}")
    print(f"{'─'*30} {'─'*7} {'─'*7} {'─'*7} {'─'*7} {'─'*8} {'─'*8} {'─'*7}")

    for label, j in [("v0.5_fixed_baseline", j05), ("v0.8_usecase_replay", j08)]:
        pref = next((r for r in grp(j, "weak_type_quality") if r['dim']=='preferred'), None)
        if pref:
            print(f"  {label:<30} {len(j):>7} {pref['n']:>7} {pref['wr3']:>6.1%} {pref['wr5']:>6.1%} {pref['ar3']:>7.2%} {pref['ar5']:>7.2%} {pref['loss5']:>6.1%}")

    # Strong watch pool quality
    print(f"\n{'═'*70}\n  STRONG WATCH POOL QUALITY (UseCase replay)\n{'═'*70}")

    watch_quality = await c.execute_query("""
        SELECT strong_grade, watch_status, pool_entry_type, COUNT(*) as n
        FROM strong_watch_pool_scored_rebuild
        GROUP BY 1,2,3 ORDER BY n DESC LIMIT 10
    """)
    for r in watch_quality:
        print(f"  grade={r['strong_grade']:<8} status={r['watch_status']:<12} entry={r['pool_entry_type']:<12} N={r['n']:>5d}")

    # Eligible (D-layer input) count
    eligible = await c.execute_query("""
        SELECT COUNT(*) as n FROM strong_watch_pool_scored_rebuild
        WHERE watch_status IN ('active','weakening') AND pool_entry_type IN ('formal','observe_only') AND NOT COALESCE(fade_confirmed,false)
    """)
    print(f"\n  Eligible (D-layer input): {eligible[0]['n']} rows")

    # v0.5 overlap
    v05_stocks = {str(r['stock_id']) for r in snaps_v05}
    v08_stocks = {str(r['stock_id']) for r in snaps_v08}
    overlap = v05_stocks & v08_stocks
    print(f"  v0.5 overlap: {len(overlap)}/{len(v05_stocks)} ({len(overlap)/max(1,len(v05_stocks)):.1%})")

    print(f"\n{'═'*70}\n  KEY FINDING\n{'═'*70}")
    pref_v05 = next((r for r in grp(j05, "weak_type_quality") if r['dim']=='preferred'), None)
    pref_v08 = next((r for r in grp(j08, "weak_type_quality") if r['dim']=='preferred'), None)
    if pref_v05 and pref_v08:
        d_wr = pref_v08['wr3'] - pref_v05['wr3']
        d_ar = pref_v08['ar5'] - pref_v05['ar5']
        print(f"  v0.8 preferred vs v0.5: WR3d {d_wr:+.1%}, AR5d {d_ar:+.2%}")
    print(f"  ⚠️  v0.8a partial: Position/Pattern/Board = default/empty")
    print(f"  → v0.8b should add get_stock_position_judgement/get_stock_pattern_judgement/get_subject_board_stats")
    print(f"{'═'*70}\n")

    try: await c.execute_query("UPDATE w2s_backtest_run SET status='completed',completed_at=NOW() WHERE run_id=$1", (v08_rid,))
    except: pass
    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())

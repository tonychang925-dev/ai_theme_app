"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  STATUS: DEPRECATED_EXPERIMENT — DO NOT RUN                               ║
║  Version: v0.3                                                            ║
║  Deprecated by: v1.0_usecase_replay_contract (2026-05-19)                 ║
║  Reason: Hand-written experiment logic, bypasses UseCases.                ║
║  Revenue validation: STOPPED.                                             ║
║  Migration: Use tests/contract/test_v1_0_usecase_replay_contract.py       ║
╚══════════════════════════════════════════════════════════════════════════════╝

W2S Phase 0.6 — v0.3 Weak Type Calibration Run (DEPRECATED)
=============================================================
v0.3 improvements:
  - confirm_source/confirm_level as standalone columns
  - weak_type_quality (preferred/neutral/danger) + scoring
  - leader_role_proxy multi-field fallback
  - Candidate pool quality v2 + excess returns

Strategy: w2s_signal_validation_v0.3_weak_type_calibration
"""

from __future__ import annotations

import asyncio, json, logging, os, sys, uuid
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("w2s_v0.3")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import StockReadGatewayAdapter
from stock_processing_service.tests.replay._post_market_replay_runner import _ReplayDatabaseStockFacade
from stock_processing_service.application.services.backtest.w2s_feature_snapshot_service import W2SFeatureSnapshotService
from stock_processing_service.application.services.backtest.w2s_signal_builder_service import W2SSignalBuilderService
from stock_processing_service.application.services.backtest.w2s_signal_validation_service import W2SSignalValidationService

STRATEGY_VERSION = "w2s_signal_validation_v0.3_weak_type_calibration"
START_DATE = date(2026, 4, 1)
END_DATE = date(2026, 5, 15)
DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")


def _rid() -> str:
    return f"w2s_v0.3_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


async def build_and_validate(gw, read_port, run_id: str) -> dict:
    # Snapshot
    svc = W2SFeatureSnapshotService(read_ports=read_port, gateway=gw)
    try: await gw._client.execute_query("INSERT INTO w2s_backtest_run (run_id,strategy_id,strategy_version,run_type,start_date,end_date,status,started_at) VALUES ($1,'weak_to_strong',$2,'signal_validation',$3,$4,'running',NOW()) ON CONFLICT(run_id) DO UPDATE SET status='running',started_at=NOW()", (run_id,STRATEGY_VERSION,START_DATE,END_DATE))
    except: pass
    snap = await svc.build(run_id=run_id, strategy_version=STRATEGY_VERSION, start_date=START_DATE, end_date=END_DATE, force_rebuild=True)
    print(f"  Snapshots: {snap['snapshot_count']} built, {snap['written']} written")

    # Signals
    builder = W2SSignalBuilderService(gateway=gw)
    sig = await builder.build(run_id=run_id)
    print(f"  Signals:   {sig['signal_count']} built, {sig['written']} written")

    # Validation
    validator = W2SSignalValidationService(read_ports=read_port, gateway=gw)
    val = await validator.validate(run_id=run_id, look_forward_days=(1,2,3,5))
    print(f"  Validated: {val['validated_count']} signals, {val['written']} written")

    return {"snapshots": snap, "signals": sig, "validation": val}


async def compute_reports(gw, run_id: str) -> dict:
    # Load data
    snaps = await gw._client.execute_query("SELECT * FROM w2s_backtest_feature_snapshot WHERE run_id=$1", (run_id,))
    vals = await gw._client.execute_query("SELECT * FROM strategy_signal_validation WHERE run_id=$1 AND next_3d_return IS NOT NULL", (run_id,))
    sigs = await gw._client.execute_query("SELECT signal_id, subject_key FROM strategy_signal_daily WHERE run_id=$1", (run_id,))

    # Build lookup
    vlook = {}
    for v in vals:
        k = (str(v["stock_id"]), str(v["trade_date"])[:10])
        vlook[k] = v
    sig_lookup = {str(s["signal_id"]): s for s in sigs}

    # Join snaps with vals
    joined = []
    for s in snaps:
        k = (str(s["stock_id"]), str(s["candidate_trade_date"])[:10])
        v = vlook.get(k)
        if v:
            joined.append({"s": s, "v": v})

    if not joined:
        return {"error": "no joined data"}

    def grp(key_attr: str, order_by_n: bool = True) -> list[dict]:
        groups: dict[str, list] = {}
        for row in joined:
            kval = str(row["s"].get(key_attr) or "unknown")
            groups.setdefault(kval, []).append(row)
        res = []
        for k, rows in sorted(groups.items(), key=lambda x: -len(x[1]) if order_by_n else x[0]):
            n = len(rows)
            ar1 = sum(float(r["v"]["next_1d_return"] or 0) for r in rows) / n
            ar3 = sum(float(r["v"]["next_3d_return"] or 0) for r in rows) / n
            ar5 = sum(float(r["v"]["next_5d_return"] or 0) for r in rows) / n
            wr3 = sum(1 for r in rows if r["v"].get("is_win_3d")) / n
            wr5 = sum(1 for r in rows if r["v"].get("is_win_5d")) / n
            hit = sum(1 for r in rows if r["v"].get("hit_limit_up_5d")) / n
            loss5 = sum(1 for r in rows if r["v"].get("loss_over_5pct")) / n
            res.append({"dim": k, "n": n, "ar1": ar1, "ar3": ar3, "ar5": ar5, "wr3": wr3, "wr5": wr5, "hit_lu": hit, "loss5": loss5})
        return res

    # Excess return vs subject
    subj_rets: dict[str, list[float]] = {}
    sig_to_subj = {}
    for row in joined:
        sid = str(row["s"].get("stock_id", ""))
        sk = str(row["s"].get("subject_key", ""))
        ret3 = float(row["v"].get("next_3d_return") or 0)
        sig_to_subj[sid] = sk
        if sk:
            subj_rets.setdefault(sk, []).append(ret3)
    subj_avg = {sk: sum(rets)/len(rets) for sk, rets in subj_rets.items()}

    excess_sum = 0.0
    excess_n = 0
    for row in joined:
        sk = str(row["s"].get("subject_key", ""))
        ret3 = float(row["v"].get("next_3d_return") or 0)
        savg = subj_avg.get(sk, 0)
        excess_sum += ret3 - savg
        excess_n += 1
    avg_excess_3d = excess_sum / excess_n if excess_n else 0

    # Proxy/real distributions
    level_dist = Counter()
    for row in joined:
        cs = str(row["s"].get("confirm_source") or "missing")
        cl = str(row["s"].get("confirm_level_detail") or row["s"].get("confirm_level") or "missing")
        level_dist[(cl, cs)] += 1

    return {
        "n_joined": len(joined),
        "avg_excess_vs_subject_3d": avg_excess_3d,
        "pool_entry_type": grp("pool_entry_type"),
        "candidate_type": grp("candidate_type"),
        "weak_type": grp("weak_type"),
        "weak_type_quality": grp("weak_type_quality"),
        "support_type": grp("support_type"),
        "leader_role_proxy": grp("leader_role_proxy"),
        "confirm_level_distribution": [{"level": k[0], "source": k[1], "n": v} for k, v in sorted(level_dist.items())],
        "confirm_source_distribution": dict(Counter(str(r["s"].get("confirm_source") or "missing") for r in joined)),
    }


async def main():
    run_id = _rid()
    print(f"\n{'▓'*70}\n  W2S v0.3 CALIBRATION\n  Run: {run_id}\n  Strategy: {STRATEGY_VERSION}\n  Range: {START_DATE} → {END_DATE}\n{'▓'*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    facade = _ReplayDatabaseStockFacade(gw)
    read_port = StockReadGatewayAdapter(facade)

    try:
        pipeline = await build_and_validate(gw, read_port, run_id)
        reports = await compute_reports(gw, run_id)

        # ── PRINT REPORT ──
        print(f"\n{'═'*70}")
        print(f"  W2S v0.3 — WEAK TYPE CALIBRATION REPORT")
        print(f"{'═'*70}")
        print(f"  Joined:  {reports['n_joined']} snapshots with returns")
        print(f"  Excess:  {reports['avg_excess_vs_subject_3d']:.3%} vs subject avg")

        # weak_type (most important)
        print(f"\n{'─'*70}\n  WEAK TYPE ANALYSIS (v0.3)\n{'─'*70}")
        print(f"  {'Type':<25} {'Quality':<12} {'N':>5} {'WR3d':>7} {'WR5d':>7} {'AR3d':>8} {'AR5d':>8} {'HitLU':>6} {'Loss5':>6}")
        print(f"  {'─'*25} {'─'*12} {'─'*5} {'─'*7} {'─'*7} {'─'*8} {'─'*8} {'─'*6} {'─'*6}")
        for r in reports.get("weak_type", []):
            wt = str(r["dim"])
            quality = "preferred" if wt in ("big_negative_line","bad_limit_up") else ("danger" if wt == "high_open_low_close" else "neutral")
            print(f"  {wt:<25} {quality:<12} {r['n']:>5} {r['wr3']:.1%}  {r['wr5']:.1%}  {r['ar3']:>7.2%} {r['ar5']:>7.2%} {r['hit_lu']:.1%}  {r['loss5']:.1%}")

        # weak_type_quality summary
        print(f"\n{'─'*70}\n  WEAK TYPE QUALITY SUMMARY\n{'─'*70}")
        for r in reports.get("weak_type_quality", []):
            print(f"  {r['dim']:<15} N={r['n']:>3d}  WR3d={r['wr3']:.1%}  AR5d={r['ar5']:.2%}")

        # leader_role_proxy
        lr = reports.get("leader_role_proxy", [])
        unknown_ratio = next((r["n"]/sum(x["n"] for x in lr) for r in lr if r["dim"]=="unknown"), 1.0)
        print(f"\n{'─'*70}\n  LEADER ROLE PROXY (v0.3)\n{'─'*70}")
        print(f"  Unknown ratio: {unknown_ratio:.0%}")
        for r in lr:
            print(f"  {r['dim']:<20} N={r['n']:>3d}  WR3d={r['wr3']:.1%}  AR5d={r['ar5']:.2%}")

        # pool_entry_type
        print(f"\n{'─'*70}\n  POOL ENTRY TYPE (after weak_type_downgrade)\n{'─'*70}")
        for r in reports.get("pool_entry_type", []):
            print(f"  {r['dim']:<20} N={r['n']:>3d}  WR3d={r['wr3']:.1%}  AR5d={r['ar5']:.2%}")

        # Confirm distribution
        print(f"\n{'─'*70}\n  CONFIRM LEVEL DISTRIBUTION\n{'─'*70}")
        for d in reports.get("confirm_level_distribution", []):
            print(f"  {d['level']:<25} {d['source']:<20} N={d['n']:>4d}")
        print(f"\n  Confirm sources: {reports.get('confirm_source_distribution', {})}")

        # Key findings
        print(f"\n{'═'*70}\n  v0.3 KEY FINDINGS\n{'═'*70}")
        wt_data = {r["dim"]: r for r in reports.get("weak_type", [])}
        bnl = wt_data.get("big_negative_line", {})
        holc = wt_data.get("high_open_low_close", {})
        if bnl and holc:
            delta_wr = bnl.get("wr3", 0) - holc.get("wr3", 0)
            delta_ar = bnl.get("ar5", 0) - holc.get("ar5", 0)
            print(f"  big_negative_line vs high_open_low_close:")
            print(f"    WR3d delta: {delta_wr:+.1%}  AR5d delta: {delta_ar:+.2%}")
            if delta_wr > 0.1:
                print(f"  ✅ big_negative_line significantly outperforms — weak_type_quality confirmed")
            else:
                print(f"  ⚠️  Difference exists but sample size limits confidence")
        print(f"  Leader unknown ratio: {unknown_ratio:.0%}")
        if unknown_ratio < 0.8:
            print(f"  ✅ Leader proxy now identifies non-unknown classifications")
        else:
            print(f"  ⚠️  leader_role_proxy still mostly unknown — need more identity data")
        print(f"\n  v0.3 is a RESEARCH version. Next: v0.4 with Phase -1 feature store.")
        print(f"{'═'*70}\n")

        try: await gw._client.execute_query("UPDATE w2s_backtest_run SET status='completed',completed_at=NOW() WHERE run_id=$1",(run_id,))
        except: pass
    finally:
        close_fn = getattr(gw, "close", None)
        if callable(close_fn): await close_fn()


if __name__ == "__main__":
    asyncio.run(main())

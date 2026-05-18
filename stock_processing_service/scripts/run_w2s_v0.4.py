"""
W2S v0.4 — 3-Month Expansion Validation
=========================================
Phase -1 feature store enabled. 6 experiments. 3-month range.
Strategy: w2s_signal_validation_v0.4_expand_3m
"""

from __future__ import annotations

import asyncio, json, logging, os, sys, uuid
from collections import Counter
from datetime import date, datetime
from typing import Any

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("w2s_v0.4")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import StockReadGatewayAdapter
from stock_processing_service.tests.replay._post_market_replay_runner import _ReplayDatabaseStockFacade
from stock_processing_service.application.services.backtest.w2s_feature_snapshot_service import W2SFeatureSnapshotService
from stock_processing_service.application.services.backtest.w2s_signal_builder_service import W2SSignalBuilderService
from stock_processing_service.application.services.backtest.w2s_signal_validation_service import W2SSignalValidationService

STRATEGY_VERSION = "w2s_signal_validation_v0.4_expand_3m"
START_DATE = date(2026, 2, 15)
END_DATE = date(2026, 5, 15)
DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")


def _rid() -> str: return f"w2s_v0.4_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


EXPERIMENTS = {
    "EXP_A_BASELINE": {"label": "全量基准", "cond": lambda r: r["s"]["pool_entry_type"] in ("formal", "observe_only")},
    "EXP_B_FORMAL_ONLY": {"label": "仅formal", "cond": lambda r: r["s"]["pool_entry_type"] == "formal"},
    "EXP_C_PREFERRED_ONLY": {"label": "仅preferred", "cond": lambda r: r["s"]["pool_entry_type"] == "formal" and r["s"].get("weak_type_quality") == "preferred"},
    "EXP_D_DANGER_EXCLUDED": {"label": "剔除danger", "cond": lambda r: r["s"]["pool_entry_type"] == "formal" and r["s"].get("weak_type_quality") != "danger"},
    "EXP_E_PREFERRED_MAINLINE": {"label": "preferred+主线", "cond": lambda r: r["s"]["pool_entry_type"] == "formal" and r["s"].get("weak_type_quality") == "preferred" and (_to_f(r["s"].get("mainline_strength_score")) >= 60) and not r["s"].get("fade_confirmed", False)},
    "EXP_F_PREFERRED_MAINLINE_LEADER": {"label": "pref+主线+龙头", "cond": lambda r: _exp_e(r) and r["s"].get("leader_role_proxy") in ("leader", "potential_leader", "strong_trend")},
}

# Pre-compute EXP_E for EXP_F
def _exp_e(r): return r["s"]["pool_entry_type"] == "formal" and r["s"].get("weak_type_quality") == "preferred" and _to_f(r["s"].get("mainline_strength_score")) >= 60 and not r["s"].get("fade_confirmed", False)


def _to_f(v): return float(v or 0)


async def build_and_validate(gw, read_port, run_id):
    svc = W2SFeatureSnapshotService(read_ports=read_port, gateway=gw)
    try: await gw._client.execute_query("INSERT INTO w2s_backtest_run (run_id,strategy_id,strategy_version,run_type,start_date,end_date,status,started_at) VALUES ($1,'weak_to_strong',$2,'signal_validation',$3,$4,'running',NOW()) ON CONFLICT(run_id) DO UPDATE SET status='running',started_at=NOW()", (run_id,STRATEGY_VERSION,START_DATE,END_DATE))
    except: pass
    snap = await svc.build(run_id=run_id, strategy_version=STRATEGY_VERSION, start_date=START_DATE, end_date=END_DATE, force_rebuild=True)
    print(f"  Snapshots: {snap['snapshot_count']} built, {snap['written']} written")

    builder = W2SSignalBuilderService(gateway=gw)
    sig = await builder.build(run_id=run_id)
    print(f"  Signals:   {sig['signal_count']} built, {sig['written']} written")

    validator = W2SSignalValidationService(read_ports=read_port, gateway=gw)
    val = await validator.validate(run_id=run_id, look_forward_days=(1,2,3,5))
    print(f"  Validated: {val['validated_count']} signals, {val['written']} written")
    return {"snapshots": snap, "signals": sig, "validation": val}


async def compute_report(gw, run_id):
    snaps = await gw._client.execute_query("SELECT * FROM w2s_backtest_feature_snapshot WHERE run_id=$1", (run_id,))
    vals = await gw._client.execute_query("SELECT * FROM strategy_signal_validation WHERE run_id=$1 AND next_3d_return IS NOT NULL", (run_id,))
    vlook = {}
    for v in vals:
        k = (str(v["stock_id"]), str(v["trade_date"])[:10])
        vlook[k] = v

    joined = []
    for s in snaps:
        k = (str(s["stock_id"]), str(s["candidate_trade_date"])[:10])
        v = vlook.get(k)
        if v: joined.append({"s": s, "v": v})

    if not joined: return {"error": "no data", "n": 0}

    def grp(attr, rows=None):
        rows = rows or joined
        groups: dict[str, list] = {}
        for r in rows:
            kval = str(r["s"].get(attr) or "unknown")
            groups.setdefault(kval, []).append(r)
        res = []
        for k, rs in sorted(groups.items(), key=lambda x: -len(x[1])):
            n = len(rs)
            ar3 = sum(float(r["v"]["next_3d_return"] or 0) for r in rs) / n
            ar5 = sum(float(r["v"]["next_5d_return"] or 0) for r in rs) / n
            wr3 = sum(1 for r in rs if r["v"].get("is_win_3d")) / n
            wr5 = sum(1 for r in rs if r["v"].get("is_win_5d")) / n
            loss5 = sum(1 for r in rs if r["v"].get("loss_over_5pct")) / n
            res.append({"dim": k, "n": n, "ar3": ar3, "ar5": ar5, "wr3": wr3, "wr5": wr5, "loss5": loss5})
        return res

    # Excess returns
    subj_rets: dict[str, list[float]] = {}
    for r in joined:
        sk = str(r["s"].get("subject_key") or "")
        ret3 = float(r["v"].get("next_3d_return") or 0)
        if sk: subj_rets.setdefault(sk, []).append(ret3)
    subj_avg = {sk: sum(rets)/len(rets) for sk, rets in subj_rets.items()}
    ex_sum, ex_n = 0.0, 0
    for r in joined:
        sk = str(r["s"].get("subject_key") or "")
        ret3 = float(r["v"]["next_3d_return"] or 0)
        ex_sum += ret3 - subj_avg.get(sk, 0)
        ex_n += 1
    excess_3d = ex_sum / ex_n if ex_n else 0

    # 6 experiments
    exp_results = {}
    for eid, ecfg in EXPERIMENTS.items():
        filtered = [r for r in joined if ecfg["cond"](r)]
        if filtered:
            fs = {r["s"]["stock_id"] for r in filtered}
            nf = len(filtered)
            ar3f = sum(float(r["v"]["next_3d_return"] or 0) for r in filtered) / nf
            ar5f = sum(float(r["v"]["next_5d_return"] or 0) for r in filtered) / nf
            wr3f = sum(1 for r in filtered if r["v"].get("is_win_3d")) / nf
            wr5f = sum(1 for r in filtered if r["v"].get("is_win_5d")) / nf
            lossf = sum(1 for r in filtered if r["v"].get("loss_over_5pct")) / nf
            exp_results[eid] = {"label": ecfg["label"], "n": nf, "wr3": wr3f, "wr5": wr5f, "ar3": ar3f, "ar5": ar5f, "loss5": lossf}

    # confirm distribution
    lvl_dist = Counter()
    for r in joined:
        cs = str(r["s"].get("confirm_source") or "missing")
        cl = str(r["s"].get("confirm_level_detail") or r["s"].get("confirm_level") or "missing")
        lvl_dist[(cl, cs)] += 1

    return {
        "n": len(joined),
        "excess_3d": excess_3d,
        "experiments": exp_results,
        "weak_type": grp("weak_type"),
        "weak_type_quality": grp("weak_type_quality"),
        "leader_role_proxy": grp("leader_role_proxy"),
        "pool_entry_type": grp("pool_entry_type"),
        "candidate_type": grp("candidate_type"),
        "support_type": grp("support_type"),
        "confirm_dist": [{"lvl": k[0], "src": k[1], "n": v} for k, v in sorted(lvl_dist.items())],
        "confirm_sources": dict(Counter(str(r["s"].get("confirm_source") or "missing") for r in joined)),
    }


async def main():
    run_id = _rid()
    print(f"\n{'▓'*70}\n  W2S v0.4 — 3-MONTH EXPANSION\n  Run: {run_id}\n  Range: {START_DATE} → {END_DATE}\n{'▓'*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    facade = _ReplayDatabaseStockFacade(gw)
    read_port = StockReadGatewayAdapter(facade)

    try:
        await build_and_validate(gw, read_port, run_id)
        rpt = await compute_report(gw, run_id)

        print(f"\n{'═'*70}\n  W2S v0.4 REPORT\n{'═'*70}")
        print(f"  Joined: {rpt['n']} with returns  |  Excess vs subject: {rpt.get('excess_3d', 0):.3%}")

        # 6 Experiments
        print(f"\n{'─'*70}\n  EXPERIMENTS (v0.4, ~3 months)\n{'─'*70}")
        print(f"  {'Experiment':<30} {'N':>5} {'WR3d':>7} {'WR5d':>7} {'AR3d':>8} {'AR5d':>8} {'Loss5':>6}")
        print(f"  {'─'*30} {'─'*5} {'─'*7} {'─'*7} {'─'*8} {'─'*8} {'─'*6}")
        for eid in ["EXP_A_BASELINE","EXP_B_FORMAL_ONLY","EXP_C_PREFERRED_ONLY","EXP_D_DANGER_EXCLUDED","EXP_E_PREFERRED_MAINLINE","EXP_F_PREFERRED_MAINLINE_LEADER"]:
            e = rpt.get("experiments", {}).get(eid, {})
            if e:
                print(f"  {e['label']:<30} {e['n']:>5} {e['wr3']:.1%}  {e['wr5']:.1%}  {e['ar3']:>7.2%} {e['ar5']:>7.2%} {e['loss5']:.1%}")

        # Weak type quality
        print(f"\n{'─'*70}\n  WEAK TYPE QUALITY (v0.4)\n{'─'*70}")
        for r in rpt.get("weak_type_quality", []):
            print(f"  {r['dim']:<15} N={r['n']:>3d}  WR3d={r['wr3']:.1%}  AR5d={r['ar5']:.2%}  Loss5={r['loss5']:.1%}")

        # Leader role proxy
        lr = rpt.get("leader_role_proxy", [])
        total_lr = sum(x["n"] for x in lr)
        unk = next((x for x in lr if x["dim"] == "unknown"), None)
        uk_ratio = unk["n"] / total_lr if unk and total_lr else 1.0
        print(f"\n{'─'*70}\n  LEADER ROLE PROXY (v0.4, Phase -1 enabled)\n{'─'*70}")
        print(f"  Unknown ratio: {uk_ratio:.0%} (from {total_lr} total)")
        for r in lr:
            print(f"  {r['dim']:<20} N={r['n']:>3d}  WR3d={r['wr3']:.1%}  AR5d={r['ar5']:.2%}")

        # Key findings
        print(f"\n{'═'*70}\n  v0.4 KEY FINDINGS\n{'═'*70}")
        exp = rpt.get("experiments", {})
        exp_a = exp.get("EXP_A_BASELINE", {})
        exp_c = exp.get("EXP_C_PREFERRED_ONLY", {})
        exp_e = exp.get("EXP_E_PREFERRED_MAINLINE", {})
        exp_f = exp.get("EXP_F_PREFERRED_MAINLINE_LEADER", {})

        if exp_c and exp_a:
            d = exp_c.get("wr3", 0) - exp_a.get("wr3", 0)
            print(f"  preferred vs baseline WR3d: {d:+.1%}")
        if exp_e and exp_c:
            d = exp_e.get("wr3", 0) - exp_c.get("wr3", 0)
            print(f"  mainline vs preferred WR3d: {d:+.1%}")
        if exp_f and exp_e:
            d = exp_f.get("wr3", 0) - exp_e.get("wr3", 0)
            print(f"  leader vs mainline WR3d:  {d:+.1%}")
        print(f"  Leader unknown ratio:     {uk_ratio:.0%}")
        print(f"  Excess vs subject:        {rpt.get('excess_3d', 0):.3%}")
        print(f"{'═'*70}\n")

        try: await gw._client.execute_query("UPDATE w2s_backtest_run SET status='completed',completed_at=NOW() WHERE run_id=$1",(run_id,))
        except: pass
    finally:
        close_fn = getattr(gw, "close", None)
        if callable(close_fn): await close_fn()


if __name__ == "__main__":
    asyncio.run(main())

"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  STATUS: FROZEN BASELINE — v1.1b_signal_validation                         ║
║  Frozen: 2026-05-19                                                        ║
║  Output: w2s_signal_validation_v1_1b (197 rows, WR3d 58.9%, AR5d +5.29%)  ║
╚══════════════════════════════════════════════════════════════════════════════╝

v1.1b_signal_validation — Forward return validation of v1.0 UseCase candidates.
================================================================================
Input: w2s_candidate_rebuild ONLY (rule_version=w2s_v1.0_usecase_replay).
Output: isolated tables (w2s_signal_validation_v1_1b, w2s_validation_summary_v1_1b).
No revenue backtest. No strategy threshold changes. No C/D hand-writing.

Usage: python stock_processing_service/tests/contract/run_v1_1b_signal_validation.py
"""

from __future__ import annotations

import asyncio, json, os, sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")


async def load_bars(c, start_date: date, end_date: date) -> dict[date, dict[str, dict]]:
    """Load daily bars for forward return computation."""
    rows = await c.execute_query(
        """SELECT DISTINCT ON (trade_date, stock_id)
           trade_date, stock_id, open_price, high_price, low_price, close_price, pre_close, pct_chg
           FROM stock_daily_snapshot
           WHERE trade_date >= $1 AND trade_date <= $2
           AND source_name LIKE 'tushare%'
           ORDER BY trade_date, stock_id""",
        (start_date - timedelta(days=1), end_date + timedelta(days=10)),
    )
    bars: dict[date, dict[str, dict]] = {}
    for r in rows:
        td = r["trade_date"]
        bars.setdefault(td, {})[str(r["stock_id"])] = r
    return bars


def compute_forward_returns(
    candidate: dict, bars: dict[date, dict[str, dict]], trade_dates: list[date]
) -> dict[str, Any]:
    """Compute forward returns for a single candidate."""
    stock_id = str(candidate["stock_id"])
    trade_date = candidate["trade_date"]
    if isinstance(trade_date, str):
        trade_date = date.fromisoformat(trade_date)

    entry_bar = bars.get(trade_date, {}).get(stock_id)
    if not entry_bar:
        return {"status": "no_entry_bar"}

    entry_close = float(entry_bar.get("close_price") or 0)
    if entry_close <= 0:
        return {"status": "no_entry_price"}

    # Find next trading days
    next_dates = [d for d in trade_dates if d > trade_date]
    if len(next_dates) < 5:
        return {"status": "insufficient_future_dates"}

    # Compute returns
    results = {"status": "ok", "entry_close": entry_close}

    for horizon, ndays in [("1d", 1), ("3d", 3), ("5d", 5)]:
        if len(next_dates) < ndays:
            continue
        target_date = next_dates[ndays - 1]
        target_bar = bars.get(target_date, {}).get(stock_id)
        if not target_bar:
            continue

        target_close = float(target_bar.get("close_price") or 0)
        ret = (target_close - entry_close) / entry_close
        results[f"next_{horizon}_return"] = ret
        results[f"is_win_{horizon}"] = ret > 0

    # Max return and drawdown over 5 days
    max_ret_5d = 0.0
    min_ret_5d = 0.0
    hit_lu_5d = False
    for i, nd in enumerate(next_dates[:5]):
        b = bars.get(nd, {}).get(stock_id)
        if not b:
            continue
        c = float(b.get("close_price") or 0)
        ret = (c - entry_close) / entry_close
        max_ret_5d = max(max_ret_5d, ret)
        min_ret_5d = min(min_ret_5d, ret)
        if float(b.get("pct_chg") or 0) >= 9.5:
            hit_lu_5d = True

    results["max_return_5d"] = max_ret_5d
    results["min_return_5d"] = min_ret_5d
    results["hit_limit_up_5d"] = hit_lu_5d
    results["loss_over_5pct"] = min_ret_5d <= -0.05

    return results


def bucket(value: float, bins: list[float]) -> str:
    for b in bins:
        if value < b:
            return f"<{b}"
    return f">={bins[-1]}"


def compute_group_stats(rows: list[dict], attr: str, min_n: int = 3) -> list[dict]:
    """Compute WR/AR/Loss stats grouped by an attribute from the candidate dict."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        val = str(r.get(attr) or "unknown")
        groups[val].append(r)

    result = []
    for k, rs in sorted(groups.items(), key=lambda x: -len(x[1])):
        if len(rs) < min_n:
            continue
        n = len(rs)
        wr1 = sum(1 for r in rs if r.get("is_win_1d")) / n
        wr3 = sum(1 for r in rs if r.get("is_win_3d")) / n
        wr5 = sum(1 for r in rs if r.get("is_win_5d")) / n
        ar1 = sum(float(r.get("next_1d_return") or 0) for r in rs) / n
        ar3 = sum(float(r.get("next_3d_return") or 0) for r in rs) / n
        ar5 = sum(float(r.get("next_5d_return") or 0) for r in rs) / n
        loss5 = sum(1 for r in rs if r.get("loss_over_5pct")) / n
        hit_lu = sum(1 for r in rs if r.get("hit_limit_up_5d")) / n
        max_dd = min(float(r.get("min_return_5d") or 0) for r in rs)

        result.append({
            "dim": k, "n": n,
            "wr1": wr1, "wr3": wr3, "wr5": wr5,
            "ar1": ar1, "ar3": ar3, "ar5": ar5,
            "loss5": loss5, "hit_lu": hit_lu, "max_dd_5d": max_dd,
        })
    return result


async def main():
    print(f"\n{'='*70}")
    print(f"  v1.1b SIGNAL VALIDATION")
    print(f"  Mode: SIGNAL ONLY — NO CAPITAL BACKTEST")
    print(f"{'='*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # ═══ Step 1: Load candidates ═══
    candidates = await c.execute_query("""
        SELECT stock_id, stock_name, trade_date, subject_key, theme_name,
               weak_type, support_type, support_strength, pool_entry_type,
               candidate_score, candidate_type, rule_version,
               source_trace->>'usecase' as source_usecase
        FROM w2s_candidate_rebuild
        WHERE rule_version = 'w2s_v1.0_usecase_replay'
        ORDER BY trade_date, stock_id
    """)
    print(f"Input candidates: {len(candidates)}")

    # ═══ Step 2: Load bars ═══
    trade_dates_set = {r["trade_date"] for r in candidates}
    min_date = min(trade_dates_set)
    max_date = max(trade_dates_set)
    trade_dates_query = await c.execute_query(
        "SELECT DISTINCT trade_date FROM stock_daily_snapshot WHERE trade_date >= $1 AND trade_date <= $2 AND source_name LIKE 'tushare%' ORDER BY trade_date",
        (min_date, max_date + timedelta(days=10)),
    )
    trade_dates = [r["trade_date"] for r in trade_dates_query]

    bars = await load_bars(c, min_date, max_date)
    print(f"Trading date range: {min_date} → {max_date} ({len(trade_dates)} days)")
    print(f"Bars loaded: {sum(len(v) for v in bars.values())} rows")

    # ═══ Step 3: Compute forward returns ═══
    validated = []
    for cand in candidates:
        result = compute_forward_returns(cand, bars, trade_dates)
        if result.get("status") == "ok" and result.get("next_3d_return") is not None:
            validated.append({**cand, **result})

    print(f"Validated (with 3d returns): {len(validated)}")

    # ═══ Step 4: Compute market baseline ═══
    # Market avg: average return of all stocks on each date
    market_returns_3d = []
    for cand in candidates:
        td = cand["trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        bar_today = bars.get(td, {})
        if not bar_today:
            continue
        next_dates = [d for d in trade_dates if d > td]
        if len(next_dates) < 3:
            continue
        # Sample up to 100 random stocks for market average
        all_stocks = list(bar_today.keys())[:100]
        if len(all_stocks) < 10:
            continue
        t3_date = next_dates[2]
        bars_t3 = bars.get(t3_date, {})
        rets = []
        for sid in all_stocks:
            entry = bar_today.get(sid, {})
            exit_bar = bars_t3.get(sid, {})
            if entry and exit_bar:
                ec = float(entry.get("close_price") or 0)
                xc = float(exit_bar.get("close_price") or 0)
                if ec > 0:
                    rets.append((xc - ec) / ec)
        if rets:
            market_returns_3d.append(sum(rets) / len(rets))
    market_ar3 = sum(market_returns_3d) / len(market_returns_3d) if market_returns_3d else 0
    print(f"Market baseline AR3d: {market_ar3:.4f} ({len(market_returns_3d)} date-samples)")

    # ═══ Step 5: Overall metrics ═══
    n = len(validated)
    wr1 = sum(1 for r in validated if r.get("is_win_1d")) / n if n else 0
    wr3 = sum(1 for r in validated if r.get("is_win_3d")) / n if n else 0
    wr5 = sum(1 for r in validated if r.get("is_win_5d")) / n if n else 0
    ar1 = sum(float(r.get("next_1d_return") or 0) for r in validated) / n if n else 0
    ar3 = sum(float(r.get("next_3d_return") or 0) for r in validated) / n if n else 0
    ar5 = sum(float(r.get("next_5d_return") or 0) for r in validated) / n if n else 0
    loss5 = sum(1 for r in validated if r.get("loss_over_5pct")) / n if n else 0
    hit_lu = sum(1 for r in validated if r.get("hit_limit_up_5d")) / n if n else 0

    print(f"\n{'='*70}")
    print(f"  OVERALL METRICS (n={n})")
    print(f"{'='*70}")
    print(f"  WR1d: {wr1:.1%}  |  WR3d: {wr3:.1%}  |  WR5d: {wr5:.1%}")
    print(f"  AR1d: {ar1:+.2%}  |  AR3d: {ar3:+.2%}  |  AR5d: {ar5:+.2%}")
    print(f"  Loss5%: {loss5:.1%}  |  HitLU5d: {hit_lu:.1%}  |  Market AR3: {market_ar3:+.2%}")
    print(f"  Excess vs market (AR3d): {ar3 - market_ar3:+.2%}")

    # ═══ Step 6: Group breakdowns ═══
    groupings = {
        "support_type": "support_type",
        "pool_entry_type": "pool_entry_type",
    }

    for label, attr in groupings.items():
        groups = compute_group_stats(validated, attr)
        if groups:
            print(f"\n  By {label}:")
            print(f"  {'dim':<20} {'n':>4} {'WR3d':>7} {'AR3d':>8} {'AR5d':>8} {'Loss5':>6} {'HitLU':>6}")
            for g in groups:
                print(f"  {g['dim']:<20} {g['n']:>4} {g['wr3']:>6.1%} {g['ar3']:>7.2%} {g['ar5']:>7.2%} {g['loss5']:>5.1%} {g['hit_lu']:>5.1%}")

    # support_strength bucket
    for r in validated:
        ss = float(r.get("support_strength") or 0)
        r["support_strength_bucket"] = bucket(ss, [50, 60, 70, 80])

    for label, attr in [
        ("support_strength_bucket", "support_strength_bucket"),
    ]:
        groups = compute_group_stats(validated, attr)
        if groups:
            print(f"\n  By {label}:")
            print(f"  {'dim':<20} {'n':>4} {'WR3d':>7} {'AR3d':>8} {'AR5d':>8} {'Loss5':>6} {'HitLU':>6}")
            for g in groups:
                print(f"  {g['dim']:<20} {g['n']:>4} {g['wr3']:>6.1%} {g['ar3']:>7.2%} {g['ar5']:>7.2%} {g['loss5']:>5.1%} {g['hit_lu']:>5.1%}")

    # ═══ Step 7: v0.5 comparison ═══
    # v0.5 baseline reference values (from prior runs)
    v05_ref = {"WR3d": 0.610, "AR5d": 0.0518, "Loss5": 0.430}

    print(f"\n{'='*70}")
    print(f"  COMPARISON")
    print(f"{'='*70}")
    print(f"  {'Metric':<20} {'v1.1b_usecase':>15} {'v0.5_baseline':>15} {'delta':>10}")
    print(f"  {'─'*20} {'─'*15} {'─'*15} {'─'*10}")
    print(f"  {'N':<20} {n:>15} {'~100':>15}")
    print(f"  {'WR3d':<20} {wr3:>14.1%} {v05_ref['WR3d']:>14.1%} {wr3 - v05_ref['WR3d']:>+9.1%}")
    print(f"  {'AR5d':<20} {ar5:>14.2%} {v05_ref['AR5d']:>14.2%} {ar5 - v05_ref['AR5d']:>+9.2%}")
    print(f"  {'Loss5%':<20} {loss5:>14.1%} {v05_ref['Loss5']:>14.1%} {loss5 - v05_ref['Loss5']:>+9.1%}")

    # ═══ Step 8: Write to isolated validation table ═══
    await c.execute_query("""
        CREATE TABLE IF NOT EXISTS w2s_signal_validation_v1_1b (
            trade_date DATE, stock_id VARCHAR(32), stock_name VARCHAR(64),
            weak_type VARCHAR(64), support_type VARCHAR(64),
            support_strength VARCHAR(32), pool_entry_type VARCHAR(32),
            candidate_score VARCHAR(32),
            next_1d_return DOUBLE PRECISION, next_3d_return DOUBLE PRECISION,
            next_5d_return DOUBLE PRECISION,
            max_return_5d DOUBLE PRECISION, min_return_5d DOUBLE PRECISION,
            is_win_1d BOOLEAN, is_win_3d BOOLEAN, is_win_5d BOOLEAN,
            loss_over_5pct BOOLEAN, hit_limit_up_5d BOOLEAN,
            PRIMARY KEY (trade_date, stock_id)
        )
    """)

    written = 0
    for r in validated:
        try:
            await c.execute_query("""
                INSERT INTO w2s_signal_validation_v1_1b (
                    trade_date, stock_id, stock_name,
                    weak_type, support_type, support_strength, pool_entry_type, candidate_score,
                    next_1d_return, next_3d_return, next_5d_return,
                    max_return_5d, min_return_5d,
                    is_win_1d, is_win_3d, is_win_5d,
                    loss_over_5pct, hit_limit_up_5d
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                ON CONFLICT (trade_date, stock_id) DO UPDATE SET
                    next_1d_return=EXCLUDED.next_1d_return,
                    next_3d_return=EXCLUDED.next_3d_return,
                    next_5d_return=EXCLUDED.next_5d_return,
                    max_return_5d=EXCLUDED.max_return_5d,
                    min_return_5d=EXCLUDED.min_return_5d,
                    is_win_1d=EXCLUDED.is_win_1d,
                    is_win_3d=EXCLUDED.is_win_3d,
                    is_win_5d=EXCLUDED.is_win_5d,
                    loss_over_5pct=EXCLUDED.loss_over_5pct,
                    hit_limit_up_5d=EXCLUDED.hit_limit_up_5d
            """, (
                r["trade_date"], str(r["stock_id"]), str(r.get("stock_name", "")),
                str(r.get("weak_type", "")), str(r.get("support_type", "")),
                str(r.get("support_strength", "0")), str(r.get("pool_entry_type", "")),
                str(r.get("candidate_score", "")),
                float(r.get("next_1d_return") or 0), float(r.get("next_3d_return") or 0),
                float(r.get("next_5d_return") or 0),
                float(r.get("max_return_5d") or 0), float(r.get("min_return_5d") or 0),
                bool(r.get("is_win_1d")), bool(r.get("is_win_3d")), bool(r.get("is_win_5d")),
                bool(r.get("loss_over_5pct")), bool(r.get("hit_limit_up_5d")),
            ))
            written += 1
        except Exception as e:
            print(f"  Write error: {e}")

    print(f"\n  Written to w2s_signal_validation_v1_1b: {written} rows")

    # ═══ Step 9: Output report JSON ═══
    report = {
        "phase": "v1.1b_signal_validation",
        "executed_at": datetime.now().isoformat(),
        "input": {
            "source_table": "w2s_candidate_rebuild",
            "rule_version": "w2s_v1.0_usecase_replay",
            "candidates_total": len(candidates),
            "validated_with_3d_return": n,
        },
        "overall": {
            "N": n,
            "WR1d": wr1, "WR3d": wr3, "WR5d": wr5,
            "AR1d": ar1, "AR3d": ar3, "AR5d": ar5,
            "Loss5pct": loss5, "HitLU5d": hit_lu,
            "MarketAR3d": market_ar3,
            "ExcessAR3d": ar3 - market_ar3,
        },
        "by_support_type": compute_group_stats(validated, "support_type"),
        "by_pool_entry_type": compute_group_stats(validated, "pool_entry_type"),
        "by_support_strength_bucket": compute_group_stats(validated, "support_strength_bucket"),
        "comparison_v05": {
            "v1_1b_WR3d": wr3, "v0_5_WR3d": v05_ref["WR3d"],
            "v1_1b_AR5d": ar5, "v0_5_AR5d": v05_ref["AR5d"],
            "v1_1b_Loss5": loss5, "v0_5_Loss5": v05_ref["Loss5"],
        },
        "grade": (
            "强通过" if wr3 >= v05_ref["WR3d"] and ar5 >= v05_ref["AR5d"]
            else "较好通过" if wr3 >= 0.55 and ar5 >= 0.02 and loss5 <= 0.45
            else "最低通过" if n >= 50 and wr3 > 0.50 and ar5 > 0 and loss5 < 0.55
            else "未通过"
        ),
    }

    out_path = Path(__file__).parent / f"v1_1b_signal_validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n  Report: {out_path}")
    print(f"  Grade: {report['grade']}")

    await gw.close()
    return report


if __name__ == "__main__":
    asyncio.run(main())

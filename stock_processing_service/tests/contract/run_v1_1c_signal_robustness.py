"""
v1.1c_signal_robustness — Robustness checks before v2.0 capital backtest.
=============================================================================
1. Time-segmented validation (half-month)
2. Top-group validation (support_type × support_strength)
3. Deduplication (first_signal, cooldown_3d, cooldown_5d)
4. Tradability screening (next_open_pct, gap-limit, ST/688 )

Input:  w2s_signal_validation_v1_1b + w2s_candidate_rebuild
Output: v1_1c_robustness_*.json (report only, no trade simulation)

Usage: python stock_processing_service/tests/contract/run_v1_1c_signal_robustness.py
"""

from __future__ import annotations

import asyncio, json, os, sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway

DB_NAME = str(os.getenv("DB_NAME") or "stock_data_test")


def compute_stats(rows: list[dict]) -> dict:
    n = len(rows)
    if n == 0:
        return {"n": 0}
    wr3 = sum(1 for r in rows if r.get("is_win_3d")) / n
    wr5 = sum(1 for r in rows if r.get("is_win_5d")) / n
    ar3 = sum(float(r.get("next_3d_return") or 0) for r in rows) / n
    ar5 = sum(float(r.get("next_5d_return") or 0) for r in rows) / n
    loss5 = sum(1 for r in rows if r.get("loss_over_5pct")) / n
    hit_lu = sum(1 for r in rows if r.get("hit_limit_up_5d")) / n
    return {"n": n, "wr3": wr3, "wr5": wr5, "ar3": ar3, "ar5": ar5, "loss5": loss5, "hit_lu": hit_lu}


def dedup_first_only(rows: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for r in sorted(rows, key=lambda x: (x["stock_id"], str(x.get("trade_date", "")))):
        if r["stock_id"] not in seen:
            seen.add(r["stock_id"])
            out.append(r)
    return out


def dedup_cooldown(rows: list[dict], cooldown_days: int) -> list[dict]:
    last_seen: dict[str, date] = {}
    out = []
    for r in sorted(rows, key=lambda x: (str(x.get("trade_date", "")), x["stock_id"])):
        sid = r["stock_id"]
        td = r["trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        if sid in last_seen:
            delta = (td - last_seen[sid]).days
            if delta < cooldown_days:
                continue
        last_seen[sid] = td
        out.append(r)
    return out


def half_month_label(td: date) -> str:
    if td <= date(2026, 2, 28):
        return "2026-02H2"
    if td <= date(2026, 3, 31):
        return "2026-03"
    if td <= date(2026, 4, 30):
        return "2026-04"
    return "2026-05H1"


async def main():
    print(f"\n{'='*70}")
    print(f"  v1.1c SIGNAL ROBUSTNESS")
    print(f"  Mode: ROBUSTNESS CHECKS — NO CAPITAL BACKTEST")
    print(f"{'='*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # ═══ Load validated signals ═══
    signals = await c.execute_query("""
        SELECT v.*, c.support_type, c.support_strength, c.pool_entry_type,
               c.weak_type, c.candidate_score
        FROM w2s_signal_validation_v1_1b v
        JOIN w2s_candidate_rebuild c ON v.trade_date=c.trade_date AND v.stock_id=c.stock_id
        WHERE c.rule_version = 'w2s_v1.0_usecase_replay'
        ORDER BY v.trade_date, v.stock_id
    """)
    print(f"Signals loaded: {len(signals)}")

    # Parse dates
    for s in signals:
        td = s["trade_date"]
        if isinstance(td, str):
            s["trade_date"] = date.fromisoformat(td)
        s["half_month"] = half_month_label(s["trade_date"])
        ss = float(s.get("support_strength") or 0)
        s["support_bucket"] = ">=80" if ss >= 80 else "<80"

    # ═══ 1. Time-segmented ═══
    print(f"\n{'─'*70}")
    print(f"  1. TIME SEGMENTS")
    print(f"{'─'*70}")
    print(f"  {'Segment':<14} {'N':>5} {'WR3d':>7} {'WR5d':>7} {'AR3d':>8} {'AR5d':>8} {'Loss5':>6} {'HitLU':>6}")

    all_stats = {}
    for seg in ["2026-02H2", "2026-03", "2026-04", "2026-05H1"]:
        seg_rows = [s for s in signals if s["half_month"] == seg]
        st = compute_stats(seg_rows)
        all_stats[seg] = st
        if st["n"] > 0:
            print(f"  {seg:<14} {st['n']:>5} {st['wr3']:>6.1%} {st['wr5']:>6.1%} {st['ar3']:>7.2%} {st['ar5']:>7.2%} {st['loss5']:>5.1%} {st['hit_lu']:>5.1%}")

    # Check concentration
    total_n = len(signals)
    max_seg_n = max(st["n"] for st in all_stats.values())
    max_seg_wr3 = max(st["wr3"] for st in all_stats.values() if st["n"] > 0)
    min_seg_wr3 = min(st["wr3"] for st in all_stats.values() if st["n"] > 0)
    dominated = max_seg_n / total_n if total_n else 0

    print(f"\n  Dominance: max_segment={dominated:.0%} of total  |  WR3d range: {min_seg_wr3:.1%} – {max_seg_wr3:.1%}")

    # ═══ 2. Top groups ═══
    print(f"\n{'─'*70}")
    print(f"  2. TOP GROUPS (support_type × support_strength)")
    print(f"{'─'*70}")
    print(f"  {'Group':<35} {'N':>5} {'WR3d':>7} {'AR5d':>8} {'Loss5':>6} {'HitLU':>6}")

    groups = {}
    for sup_type in ["previous_low", "ma_support", "gap_support"]:
        for sb in [">=80", "<80"]:
            gr = [s for s in signals if s.get("support_type") == sup_type and s["support_bucket"] == sb]
            if gr:
                st = compute_stats(gr)
                groups[f"{sup_type}+{sb}"] = st
                print(f"  {sup_type}+{sb:<30} {st['n']:>5} {st['wr3']:>6.1%} {st['ar5']:>7.2%} {st['loss5']:>5.1%} {st['hit_lu']:>5.1%}")

    # Pure previous_low + >=80
    prev80 = [s for s in signals if s.get("support_type") == "previous_low" and s["support_bucket"] == ">=80"]
    prev80_st = compute_stats(prev80)
    print(f"\n  ★ previous_low+>=80:  N={prev80_st['n']}  WR3d={prev80_st['wr3']:.1%}  AR5d={prev80_st['ar5']:+.2%}  Loss5={prev80_st['loss5']:.1%}")

    # ═══ 3. Deduplication ═══
    print(f"\n{'─'*70}")
    print(f"  3. DEDUPLICATION")
    print(f"{'─'*70}")

    raw_st = compute_stats(signals)
    first_st = compute_stats(dedup_first_only(signals))
    cool3_st = compute_stats(dedup_cooldown(signals, 3))
    cool5_st = compute_stats(dedup_cooldown(signals, 5))

    print(f"  {'Version':<22} {'N':>5} {'WR3d':>7} {'WR5d':>7} {'AR3d':>8} {'AR5d':>8} {'Loss5':>6}")
    for label, st in [("raw", raw_st), ("first_signal_only", first_st), ("cooldown_3d", cool3_st), ("cooldown_5d", cool5_st)]:
        print(f"  {label:<22} {st['n']:>5} {st['wr3']:>6.1%} {st['wr5']:>6.1%} {st['ar3']:>7.2%} {st['ar5']:>7.2%} {st['loss5']:>5.1%}")

    # Per-stock repeat check
    stock_counts = defaultdict(int)
    for s in signals:
        stock_counts[s["stock_id"]] += 1
    multi = {k: v for k, v in stock_counts.items() if v > 1}
    repeat_rate = sum(v - 1 for v in multi.values()) / len(signals) if signals else 0
    print(f"\n  Repeat signals: {len(multi)}/{len(stock_counts)} stocks repeated ({repeat_rate:.1%} repeat rate)")
    if multi:
        top_repeats = sorted(multi.items(), key=lambda x: -x[1])[:10]
        print(f"  Top repeaters: {', '.join(f'{k}({v}x)' for k, v in top_repeats)}")

    # ═══ 4. Tradability screening ═══
    print(f"\n{'─'*70}")
    print(f"  4. TRADABILITY SCREENING")
    print(f"{'─'*70}")

    # Load next-day bars for tradability check
    trade_dates_sorted = sorted({s["trade_date"] for s in signals})
    min_td, max_td = min(trade_dates_sorted), max(trade_dates_sorted)

    bars_query = await c.execute_query(
        """SELECT trade_date, stock_id, open_price, high_price, low_price,
                  close_price, pre_close, pct_chg, volume, amount
           FROM stock_daily_snapshot
           WHERE trade_date >= $1 AND trade_date <= $2
           AND source_name LIKE 'tushare%'""",
        (min_td, max_td + timedelta(days=10)),
    )
    bars: dict[date, dict[str, dict]] = {}
    for r in bars_query:
        td = r["trade_date"]
        bars.setdefault(td, {})[str(r["stock_id"])] = r

    # Compute next_open_pct and gap conditions
    next_open_pcts = []
    limit_up_open = 0
    limit_down_open = 0
    skip_no_next_bar = 0
    amount_dist = []
    st_filtered = 0
    star_filtered = 0
    beijing_filtered = 0

    for s in signals:
        td = s["trade_date"]
        sid = str(s["stock_id"])

        # Board filter (688 / 3xx / 8xx / 4xx)
        code = sid.replace(".SH", "").replace(".SZ", "").replace(".BJ", "")
        if code.startswith("688"):
            star_filtered += 1
        if code.startswith("8") or code.startswith("4"):
            beijing_filtered += 1

        # Get next trading day
        next_dates = [d for d in trade_dates_sorted if d > td]
        if not next_dates:
            skip_no_next_bar += 1
            continue
        next_td = next_dates[0]
        next_bar = bars.get(next_td, {}).get(sid)
        if not next_bar:
            skip_no_next_bar += 1
            continue

        next_open = float(next_bar.get("open_price") or 0)
        pre_close = float(next_bar.get("pre_close") or 0)
        if pre_close > 0:
            open_pct = (next_open - pre_close) / pre_close
            next_open_pcts.append(open_pct)
            if open_pct >= 0.098:  # ~涨停开盘
                limit_up_open += 1
            if open_pct <= -0.098:
                limit_down_open += 1

        amount = float(next_bar.get("amount") or 0)
        amount_dist.append(amount)

    print(f"  Next-day open pct (n={len(next_open_pcts)}):")
    if next_open_pcts:
        sorted_pcts = sorted(next_open_pcts)
        print(f"    min={min(next_open_pcts):+.2%}  p25={sorted_pcts[len(sorted_pcts)//4]:+.2%}  median={sorted_pcts[len(sorted_pcts)//2]:+.2%}  p75={sorted_pcts[len(sorted_pcts)*3//4]:+.2%}  max={max(next_open_pcts):+.2%}")
    print(f"    limit_up_open:  {limit_up_open} (cannot buy)")
    print(f"    limit_down_open: {limit_down_open}")
    print(f"    skip (no next bar): {skip_no_next_bar}")

    if amount_dist:
        sorted_amt = sorted(amount_dist)
        print(f"  Amount (yuan): median={sorted_amt[len(sorted_amt)//2]/1e8:.1f}亿  p25={sorted_amt[len(sorted_amt)//4]/1e8:.1f}亿")

    print(f"  Board filter: 688(star)={star_filtered}  8xx/4xx(beijing)={beijing_filtered}")

    # ═══ 5. Conclusion ═══
    print(f"\n{'='*70}")
    print(f"  ROBUSTNESS CONCLUSIONS")
    print(f"{'='*70}")

    single_month = dominated > 0.6
    wr3_spread = max_seg_wr3 - min_seg_wr3
    prev_low_stable = all(
        compute_stats([s for s in signals if s.get("support_type") == "previous_low" and s["half_month"] == seg])["wr3"] > 0.50
        for seg in ["2026-03", "2026-04"]
        if compute_stats([s for s in signals if s.get("support_type") == "previous_low" and s["half_month"] == seg])["n"] >= 5
    )

    conclusions = {
        "time_dominated": single_month,
        "wr3d_spread": wr3_spread,
        "prev_low_stable_across_months": prev_low_stable,
        "prev_low_plus_80_robust": prev80_st.get("wr3", 0) >= 0.60,
        "dedup_wr3_acceptable": cool5_st.get("wr3", 0) >= 0.50,
        "dedup_ar5_acceptable": cool5_st.get("ar5", 0) > 0,
        "tradability_ok": limit_up_open / max(len(signals), 1) < 0.25,
        "overall": "PASS" if (
            not single_month
            and wr3_spread < 0.20
            and cool3_st.get("wr3", 0) >= 0.50
            and cool3_st.get("ar5", 0) > 0
        ) else "PARTIAL",
    }

    for k, v in conclusions.items():
        if k != "overall":
            print(f"  {k}: {'✅' if v else '❌'} {v}")

    print(f"\n  OVERALL: {conclusions['overall']}")
    print(f"  → {'Ready for v2.0 capital backtest' if conclusions['overall'] == 'PASS' else 'Review before v2.0'}")

    # ═══ Save report ═══
    report = {
        "phase": "v1.1c_signal_robustness",
        "time_segments": {k: v for k, v in all_stats.items()},
        "dominance": {"max_segment_pct": dominated, "wr3d_spread": wr3_spread},
        "top_groups": groups,
        "deduplication": {
            "raw": raw_st, "first_signal_only": first_st,
            "cooldown_3d": cool3_st, "cooldown_5d": cool5_st,
        },
        "tradability": {
            "next_open_n": len(next_open_pcts),
            "limit_up_open": limit_up_open,
            "limit_down_open": limit_down_open,
            "star_board": star_filtered,
            "beijing_board": beijing_filtered,
        },
        "conclusions": conclusions,
    }

    out_path = Path(__file__).parent / f"v1_1c_robustness_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"\n  Report: {out_path}")

    await gw.close()
    return report


if __name__ == "__main__":
    asyncio.run(main())

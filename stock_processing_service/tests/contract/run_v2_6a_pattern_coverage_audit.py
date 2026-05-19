"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  v2.6a — Pattern/Volume Feature Coverage Audit                            ║
║  Date: 2026-05-19                                                          ║
║  Purpose: Diagnostic on current pattern/volume feature state               ║
╚══════════════════════════════════════════════════════════════════════════════╝

Checks current pattern_labels, volume_pattern_status, breakout_status,
pullback_status distribution in w2s_candidate_rebuild candidates.

Usage: python stock_processing_service/tests/contract/run_v2_6a_pattern_coverage_audit.py
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


async def main():
    print(f"\n{'='*70}")
    print(f"  v2.6a — PATTERN/VOLUME FEATURE COVERAGE AUDIT")
    print(f"{'='*70}\n")

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=DB_NAME)
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    c = gw._client

    # ── Load candidate bar data ──
    cand_rows = await c.execute_query("""
        SELECT c.trade_date, c.stock_id, c.stock_name,
               c.support_type, c.support_strength, c.candidate_score,
               c.weak_type, c.pool_entry_type
        FROM w2s_candidate_rebuild c
        WHERE c.rule_version = 'w2s_v1.0_usecase_replay'
        ORDER BY c.trade_date, c.stock_id
    """)

    print(f"  Candidate rows: {len(cand_rows)}")

    # ── Load bars in bulk (one range query, Python lookup) ──
    all_dates = sorted({r["trade_date"] for r in cand_rows})
    for i in range(len(all_dates)):
        if isinstance(all_dates[i], str):
            all_dates[i] = date.fromisoformat(all_dates[i])

    min_d = all_dates[0]
    max_d = all_dates[-1]

    bar_rows = await c.execute_query(
        """SELECT trade_date, stock_id, open_price, high_price, low_price,
                  close_price, pre_close, pct_chg, volume, amount
           FROM stock_daily_snapshot
           WHERE trade_date >= $1 AND trade_date <= $2
           AND source_name LIKE 'tushare%'
           ORDER BY trade_date, stock_id""",
        (min_d - timedelta(days=30), max_d + timedelta(days=1)),
    )

    bars: dict[date, dict[str, dict]] = defaultdict(dict)
    all_bar_dates = set()
    for r in bar_rows:
        td = r["trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        bars[td][str(r["stock_id"])] = r
        all_bar_dates.add(td)

    bar_dates_sorted = sorted(all_bar_dates)
    print(f"  Bars loaded: {len(bar_rows)} rows across {len(all_bar_dates)} dates")

    # ── Compute prior day index from loaded bars ──
    def get_prior_date(td: date) -> date | None:
        prev = [d for d in bar_dates_sorted if d < td]
        return prev[-1] if prev else None

    def get_prior_bar(sid: str, td: date) -> dict | None:
        prev_d = get_prior_date(td)
        if prev_d is None:
            return None
        return bars.get(prev_d, {}).get(sid)

    # ── Classification counts ──
    volume_pattern_counts: dict[str, int] = defaultdict(int)
    breakout_counts: dict[str, int] = defaultdict(int)
    pullback_counts: dict[str, int] = defaultdict(int)
    pattern_label_counts: dict[str, int] = defaultdict(int)
    high_vol_bar_count = 0
    high_vol_unbroken_count = 0
    has_vol_surge = 0
    has_vol_shrink = 0
    limit_up_count = 0
    bad_limit_up_count = 0
    bad_limit_up_pullback_count = 0

    for r in cand_rows:
        td = r["trade_date"]
        if isinstance(td, str):
            td = date.fromisoformat(td)
        sid = str(r["stock_id"])

        bar = bars.get(td, {}).get(sid)
        if not bar:
            continue
        pct = float(bar.get("pct_chg") or 0)
        vol = float(bar.get("volume") or 0)
        high = float(bar.get("high_price") or 0)
        low = float(bar.get("low_price") or 0)
        close = float(bar.get("close_price") or 0)
        prior = get_prior_bar(sid, td)

        # ── Current (stub) classification ──
        # 1. Volume pattern
        prior_vol = float(prior.get("volume") or 0) if prior else 0
        prior_close = float(prior.get("close_price") or 0) if prior else 0
        prior_high = float(prior.get("high_price") or 0) if prior else 0

        if prior and vol > prior_vol * 1.5:
            if pct > 0:
                volume_pattern_counts["放量上涨"] += 1
                has_vol_surge += 1
            else:
                volume_pattern_counts["放量下跌"] += 1
        elif prior and vol < prior_vol * 0.6:
            volume_pattern_counts["缩量"] += 1
            has_vol_shrink += 1
        else:
            volume_pattern_counts["平量"] += 1

        # 2. Breakout
        if pct >= 9.5:
            breakout_counts["涨停突破"] += 1
            limit_up_count += 1
        elif pct > 5 and vol > prior_vol * 1.5:
            breakout_counts["放量突破"] += 1
        else:
            breakout_counts["未显著突破"] += 1

        # 3. Pullback
        if prior and close < prior_close and vol < prior_vol * 0.8:
            pullback_counts["缩量回踩"] += 1
        elif prior and close < prior_close:
            pullback_counts["下跌"] += 1
        elif prior and close > prior_close and vol < prior_vol * 0.8:
            pullback_counts["缩量上涨"] += 1
        else:
            pullback_counts["正常"] += 1

        # 4. Pattern labels
        if pct >= 9.5:
            pattern_label_counts["涨停"] += 1
        if pct <= -5:
            pattern_label_counts["大阴线"] += 1
        if -5 < pct <= -2:
            pattern_label_counts["中阴线"] += 1
        if abs(pct) < 2:
            pattern_label_counts["十字星/窄幅"] += 1
        if high > close and (high - close) / close > 0.03 and pct < 3:
            pattern_label_counts["上影线"] += 1
        if pct > 4:
            pattern_label_counts["大阳线"] += 1

        # 5. 高量不破 check (simplified, from Python bars cache)
        # Find highest volume day in last 20 trading days (excluding today)
        max_vol = 0.0
        max_vol_low = 0.0
        for past_d in bar_dates_sorted:
            if past_d >= td:
                break
            past_bar = bars.get(past_d, {}).get(sid)
            if past_bar:
                pv = float(past_bar.get("volume") or 0)
                if pv > max_vol:
                    max_vol = pv
                    max_vol_low = float(past_bar.get("low_price") or 0)
            # limit to ~20 lookback
            if len([d for d in bar_dates_sorted if past_d <= d < td]) > 20:
                continue

        if max_vol > 0:
            high_vol_bar_count += 1
            if low > max_vol_low:
                high_vol_unbroken_count += 1

        # 6. 烂板回撤 check
        if r.get("weak_type") == "bad_limit_up":
            bad_limit_up_count += 1
            if prior_high > 0:
                pullback_pct = (close - prior_high) / prior_high
                if pullback_pct > -0.03:
                    bad_limit_up_pullback_count += 1

    total = len(cand_rows)

    # ── Print report ──
    print(f"\n{'─'*70}")
    print(f"  1. CURRENT PATTERN COVERAGE (n={total})")
    print(f"{'─'*70}")

    print(f"\n  volume_pattern_status:")
    for label, cnt in sorted(volume_pattern_counts.items(), key=lambda x: -x[1]):
        print(f"    {label:<20} {cnt:>5} ({cnt/total*100:>5.1f}%)")

    print(f"\n  breakout_status:")
    for label, cnt in sorted(breakout_counts.items(), key=lambda x: -x[1]):
        print(f"    {label:<20} {cnt:>5} ({cnt/total*100:>5.1f}%)")

    print(f"\n  pullback_status:")
    for label, cnt in sorted(pullback_counts.items(), key=lambda x: -x[1]):
        print(f"    {label:<20} {cnt:>5} ({cnt/total*100:>5.1f}%)")

    print(f"\n  pattern_labels:")
    for label, cnt in sorted(pattern_label_counts.items(), key=lambda x: -x[1]):
        print(f"    {label:<20} {cnt:>5} ({cnt/total*100:>5.1f}%)")

    print(f"\n{'─'*70}")
    print(f"  2. MISSING FEATURES (GAPS)")
    print(f"{'─'*70}")

    print(f"\n  高量不破:")
    print(f"    Stocks in bar cache:               {len(bars)}")
    print(f"    Has high-vol bar in last 20d:     {high_vol_bar_count} ({high_vol_bar_count/total*100:.1f}%)")
    print(f"    High-vol bar unbroken:            {high_vol_unbroken_count} ({high_vol_unbroken_count/max(high_vol_bar_count,1)*100:.1f}% of those)")

    print(f"\n  倍量不穿:")
    print(f"    (requires 2nd-highest vol bar detection — not yet computable)")

    print(f"\n  烂板质量:")
    print(f"    bad_limit_up candidates:           {bad_limit_up_count}")
    print(f"    Within 3% of prior high (good):    {bad_limit_up_pullback_count}")

    print(f"\n  缩量回踩:")
    print(f"    Has vol shrink (vol < 0.6x prior): {has_vol_shrink} ({has_vol_shrink/total*100:.1f}%)")

    print(f"\n  放量突破:")
    print(f"    Has vol surge (vol > 1.5x prior):  {has_vol_surge} ({has_vol_surge/total*100:.1f}%)")
    print(f"    涨停:                              {limit_up_count}")

    print(f"\n{'─'*70}")
    print(f"  3. ENHANCEMENT PLAN")
    print(f"{'─'*70}")
    print(f"")
    print(f"  ✅ 放量/缩量: basic vol comparison exists, needs threshold calibration")
    print(f"  ✅ 高量不破: {high_vol_unbroken_count}/{high_vol_bar_count} computable from daily bar data")
    print(f"  ❌ 倍量不穿: needs 2nd-highest vol bar + double bottom detection")
    print(f"  ❌ 缩量回踩: currently hardcoded default, needs actual price+vol check")
    print(f"  ❌ 放量突破: needs prior resistance level identification")
    print(f"  ❌ 烂板回撤: needs intraday range data, daily bar approximation only")
    print(f"  ❌ 前高/箱体: needs multi-month structure detection")
    print(f"")

    # Save report
    report = {
        "phase": "v2.6a_pattern_coverage_audit",
        "n_candidates": total,
        "volume_pattern_distribution": dict(volume_pattern_counts),
        "breakout_distribution": dict(breakout_counts),
        "pullback_distribution": dict(pullback_counts),
        "pattern_label_distribution": dict(pattern_label_counts),
        "high_vol_bar_detected": high_vol_bar_count,
        "high_vol_unbroken": high_vol_unbroken_count,
        "bad_limit_up_count": bad_limit_up_count,
        "bad_limit_up_good_quality": bad_limit_up_pullback_count,
        "has_vol_surge": has_vol_surge,
        "has_vol_shrink": has_vol_shrink,
    }

    out_path = Path(__file__).parent / f"v2_6a_pattern_coverage_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(f"  Report: {out_path}")

    await gw.close()


if __name__ == "__main__":
    asyncio.run(main())

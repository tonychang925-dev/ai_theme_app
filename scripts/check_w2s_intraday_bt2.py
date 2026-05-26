"""BT-2: 扩大样本回测与评分有效性验证。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_w2s_intraday_bt2.py --trade-date 2026-05-26 [--limit 0]
"""
from __future__ import annotations

import asyncio, json, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.w2s_intraday_backtest import W2SIntradayBacktest, BacktestSignal

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


def time_bucket(ts: str) -> str:
    """将分钟时间戳分桶。"""
    t = ts[11:16] if "T" in ts else ts[11:16] if len(ts) > 16 else ts
    try:
        hm = int(t[:2] + t[3:5])
        if hm <= 945:
            return "09:30-09:45"
        if hm <= 1030:
            return "09:45-10:30"
        if hm <= 1130:
            return "10:30-11:30"
        if hm <= 1400:
            return "13:00-14:00"
        return "14:00-15:00"
    except Exception:
        return "unknown"


async def main():
    import argparse
    p = argparse.ArgumentParser(description="BT-2 W2S Backtest Expanded")
    p.add_argument("--trade-date", default="2026-05-26")
    p.add_argument("--limit", type=int, default=0, help="0=all stocks")
    args = p.parse_args()

    bt = W2SIntradayBacktest(DSN)

    # Multi-date: 5/25 (D1 candidates) + 5/26 (strong_watch)
    trade_dates = ["2026-05-25", "2026-05-26"]
    all_results = {}
    all_sigs = []

    for td in trade_dates:
        limit = args.limit if args.limit > 0 else 50
        result = await bt.run(td, limit_stocks=limit)
        all_results[td] = result
        for s in result.signals:
            s._trade_date = td  # tag with date
        all_sigs.extend(result.signals)
        print(f"=== {td}: {result.stocks_tested} stocks | {result.total_minutes} min | {len(result.signals)} signals ===\n")

    sigs = all_sigs

    for lvl in ("A", "B", "C"):
        stats = result.by_level.get(lvl)
        if not stats:
            continue
        print(f"Level {lvl}: count={stats['count']} avg_score={stats['avg_score']}")
        print(f"  win_5m={stats['win_rate_5m']:.1%} avg_ret_5m={stats['avg_ret_5m']:.2f}%")
        print(f"  avg_ret_30m={stats['avg_ret_30m']:.2f}%")
        print(f"  limit_up={stats['hit_limit_up_rate']:.1%} false={stats['false_signal_rate']:.1%}")

    # ── 单调性 ──
    a_win = result.by_level.get("A", {}).get("avg_ret_30m")
    b_win = result.by_level.get("B", {}).get("avg_ret_30m")
    c_win = result.by_level.get("C", {}).get("avg_ret_30m")
    mono = (a_win or -999) >= (b_win or -999) >= (c_win or -999)
    print(f"\nMonotonicity (30m): A={a_win} B={b_win} C={c_win} → {'✅' if mono else '⚠️ NOT monotonic'}")

    # ── 时间分桶 ──
    by_time = defaultdict(list)
    for s in sigs:
        by_time[time_bucket(s.minute_ts)].append(s)
    print("\n--- By time bucket ---")
    for bucket in sorted(by_time.keys()):
        bs = by_time[bucket]
        avg_r = sum(s.ret_30m for s in bs if s.ret_30m) / max(len(bs), 1)
        print(f"  {bucket}: {len(bs)} signals avg_ret_30m={avg_r:.2f}%")

    # ── 平台突破诊断 ──
    plat_break_yes = [s for s in sigs if s.break_platform]
    print(f"\n--- Platform Break ---")
    print(f"  break_platform_30m=true: {len(plat_break_yes)}/{len(sigs)} ({len(plat_break_yes)/max(len(sigs),1)*100:.1f}%)")
    if plat_break_yes:
        avg_r = sum(s.ret_30m for s in plat_break_yes if s.ret_30m) / max(len(plat_break_yes), 1)
        print(f"  avg_ret_30m={avg_r:.2f}%")

    # ── false_signal v1 vs v2 ──
    false_v1 = sum(1 for s in sigs if s.fell_below_vwap)
    print(f"\n--- False Signal ---")
    print(f"  false_v2: {false_v1}/{len(sigs)} ({false_v1/max(len(sigs),1)*100:.1f}%)")

    # ── chase_risk 诊断 ──
    # computed inside backtest but not in BacktestSignal, compute here
    chase_sigs = []
    for s in sigs:
        distance_to_vwap = abs(s.current - s.vwap) / s.current if s.current > 0 else 0
        chase = distance_to_vwap > 0.03
        if chase:
            chase_sigs.append(s)
    print(f"\n--- Chase Risk ---")
    print(f"  chase_risk (distance_to_vwap>3%): {len(chase_sigs)}/{len(sigs)} ({len(chase_sigs)/max(len(sigs),1)*100:.1f}%)")
    ab_chase = [s for s in chase_sigs if s.alert_level in ("A", "B")]
    print(f"  A/B with chase_risk: {len(ab_chase)}/{len([s for s in sigs if s.alert_level in ('A','B')])}")

    # ── 按条件分组 ──
    groups = {
        "break_platform": [s for s in sigs if s.break_platform],
        "amount_accel": [s for s in sigs if s.amount_accel],
        "above_vwap_08": [s for s in sigs if s.above_vwap_ratio >= 0.8],
        "rel_turn_pos": [s for s in sigs if s.relative_strength > 0],
    }
    print("\n--- By condition ---")
    for gname, gsigs in groups.items():
        if gsigs:
            avg_r = sum(s.ret_30m for s in gsigs if s.ret_30m) / max(len(gsigs), 1)
            print(f"  {gname}: {len(gsigs)} signals avg_ret_30m={avg_r:.2f}%")

    # ── Top/Bottom 样本 ──
    valid = [s for s in sigs if s.ret_30m is not None]
    valid.sort(key=lambda s: s.ret_30m or 0, reverse=True)
    print("\n--- Top 10 signals (by ret_30m) ---")
    for s in valid[:10]:
        print(f"  [{s.alert_level}] {s.stock_name} {s.minute_ts[11:19]} C={s.current} VWAP={s.vwap} ret_30m={s.ret_30m:.2f}%")

    print("\n--- Bottom 10 signals (by ret_30m) ---")
    for s in valid[-10:]:
        print(f"  [{s.alert_level}] {s.stock_name} {s.minute_ts[11:19]} C={s.current} VWAP={s.vwap} ret_30m={s.ret_30m:.2f}%")

    # ── A/B 中失败的(after 30m < -1%) ──
    ab_fails = [s for s in sigs if s.alert_level in ("A", "B") and s.ret_30m is not None and s.ret_30m < -1]
    print(f"\n--- A/B failures (ret_30m < -1%): {len(ab_fails)} ---")
    for s in ab_fails[:5]:
        print(f"  [{s.alert_level}] {s.stock_name} {s.minute_ts[11:19]} C={s.current} ret_30m={s.ret_30m:.2f}%")

    await bt.close()

    # JSON summary
    print("\n" + json.dumps({
        "trade_date": args.trade_date,
        "stocks": result.stocks_tested,
        "signals": len(sigs),
        "by_level": result.by_level,
        "monotonic_30m": mono,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())

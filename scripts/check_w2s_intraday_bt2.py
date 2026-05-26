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
    limit = args.limit if args.limit > 0 else 50
    result = await bt.run(args.trade_date, limit_stocks=limit)

    sigs = result.signals

    # ── 总体统计 ──
    print(f"=== BT-2: {args.trade_date} | {result.stocks_tested} stocks | {result.total_minutes} min | {len(sigs)} signals ===\n")

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

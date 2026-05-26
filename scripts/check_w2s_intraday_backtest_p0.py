"""BT-0/BT-1 P0 验证: 盘中弱转强回测引擎。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_w2s_intraday_backtest_p0.py --trade-date 2026-05-26 [--limit 10]
"""
from __future__ import annotations

import asyncio, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.w2s_intraday_backtest import W2SIntradayBacktest

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    import argparse
    p = argparse.ArgumentParser(description="BT-0/BT-1 W2S Intraday Backtest P0")
    p.add_argument("--trade-date", default="2026-05-26")
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()

    bt = W2SIntradayBacktest(DSN)
    result = await bt.run(args.trade_date, limit_stocks=args.limit)

    print(f"Stocks tested: {result.stocks_tested}")
    print(f"Total minutes: {result.total_minutes}")
    print(f"Signals: {len(result.signals)}")

    for lvl in ("A", "B", "C"):
        stats = result.by_level.get(lvl)
        if stats:
            print(f"\n── Level {lvl} ({stats['count']} signals) ──")
            print(f"  avg_score={stats['avg_score']}")
            print(f"  win_rate_5m={stats['win_rate_5m']:.1%} avg_ret_5m={stats['avg_ret_5m']:.2f}%")
            print(f"  avg_ret_30m={stats['avg_ret_30m']:.2f}%")
            print(f"  hit_limit_up={stats['hit_limit_up_rate']:.1%}")
            print(f"  false_signal={stats['false_signal_rate']:.1%}")

    # 抽样信号
    for s in result.signals[:5]:
        print(f"\n  [{s.alert_level}] {s.stock_name} {s.minute_ts} score={s.intraday_score}")
        print(f"    C={s.current} VWAP={s.vwap} above={s.above_vwap_ratio} rel={s.relative_strength}")
        print(f"    ret_5m={s.ret_5m}% ret_30m={s.ret_30m}% limit_up={s.hit_limit_up} false={s.fell_below_vwap}")
        print(f"    breakdown={json.dumps(s.score_breakdown)}")

    await bt.close()

    if result.signals:
        a_win = result.by_level.get("A", {}).get("win_rate_5m", 0)
        b_win = result.by_level.get("B", {}).get("win_rate_5m", 0)
        c_win = result.by_level.get("C", {}).get("win_rate_5m", 0)
        if a_win >= b_win >= c_win:
            print(f"\n✅ Level monotonic: A({a_win:.1%}) >= B({b_win:.1%}) >= C({c_win:.1%})")
        else:
            print(f"\n⚠️  Level NOT monotonic: A={a_win:.1%} B={b_win:.1%} C={c_win:.1%}")
    print(f"\n✅ BT-0/BT-1 P0 done")


if __name__ == "__main__":
    asyncio.run(main())

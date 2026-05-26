"""P1-I-3 P0 验证: 盘中分钟状态层构建。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_intraday_minute_state_p0.py --trade-date 2026-05-26 [--dry-run]
"""
from __future__ import annotations

import asyncio, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.intraday_minute_state_builder import IntradayMinuteStateBuilder
from stock_processing_service.sinks.intraday_minute_state_db_sink import IntradayMinuteStateDbSink

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    import argparse
    p = argparse.ArgumentParser(description="P1-I-3 Intraday Minute State P0")
    p.add_argument("--trade-date", default="2026-05-26")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    builder = IntradayMinuteStateBuilder(DSN)
    result = await builder.build(args.trade_date)

    print(f"Universe: {result.universe_count} stocks")
    print(f"Stock minute rows: {result.stock_minute_rows}")
    print(f"Index minute rows: {result.index_minute_rows}")
    print(f"Missing quotes: {result.missing_quote_count}")
    print(f"Latest minute_ts: {result.latest_minute_ts}")

    if args.dry_run:
        print("\n[dry-run] 未写入 DB")
    else:
        sink = IntradayMinuteStateDbSink(DSN)
        bars = await builder.build_stock_minutes(args.trade_date, await builder.load_universe(args.trade_date))
        index_minutes = await builder.build_index_minutes(args.trade_date)
        bars = await builder.apply_index_relative(bars, index_minutes)

        n_stock = await sink.write_stock_bars(bars)
        n_index = await sink.write_index_minutes(index_minutes)
        print(f"\n✅ Written: {n_stock} stock bars + {n_index} index bars")
        await sink.close()

    await builder.close()
    print(f"\n{'✅' if result.stock_minute_rows > 0 else '⚠️  no data'} P1-I-3 P0 done")


if __name__ == "__main__":
    asyncio.run(main())

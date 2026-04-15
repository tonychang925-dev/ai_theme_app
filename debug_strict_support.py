#!/usr/bin/env python3
"""
调试严格支撑位分析
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def debug_shenjian():
    builder = WeakToStrongCandidateBuilder()

    try:
        # 测试4月7日
        trade_date = date(2026, 4, 7)
        stock_id = "002361"

        print(f"测试神剑股份支撑位分析 - {trade_date}")
        print("=" * 70)

        # 直接调用支撑位分析方法
        support_analysis = await builder.analyze_strict_support(stock_id, -3.11, trade_date)

        print(f"支撑位分析结果:")
        for key, value in support_analysis.items():
            print(f"  {key}: {value}")

        # 获取K线数据
        print(f"\n获取K线数据...")
        kline_data = await builder.kline_service.get_kline_data(stock_id, trade_date, days_before=5, days_after=0)

        print(f"获取到{len(kline_data)}条K线数据:")
        for kline in sorted(kline_data, key=lambda x: x['trade_date']):
            date_str = kline['trade_date'].strftime("%Y-%m-%d")
            print(f"  {date_str}: O{kline['open_price']:.2f} H{kline['high_price']:.2f} "
                  f"L{kline['low_price']:.2f} C{kline['close_price']:.2f} ({kline['pct_chg']:.1f}%)")

        # 调用analyze_gap_support
        print(f"\n调用analyze_gap_support...")
        gap_analysis = await builder.kline_service.analyze_gap_support(stock_id, trade_date)

        print(f"缺口分析结果:")
        for key, value in gap_analysis.items():
            if key == 'technical_signals':
                print(f"  {key}:")
                for signal in value:
                    print(f"    - {signal}")
            else:
                print(f"  {key}: {value}")

    finally:
        await builder.close()

async def main():
    try:
        await debug_shenjian()
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
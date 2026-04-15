#!/usr/bin/env python3
"""
测试神剑股份的高级压力支撑分析
"""
import asyncio
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.kline_data_service import KlineDataService

async def test_shenjian_advanced():
    stock_id = "002361"
    test_date = date(2026, 4, 7)

    print(f"测试神剑股份高级压力支撑分析 - {stock_id} - {test_date}")
    print("=" * 80)

    service = KlineDataService()

    # 首先检查数据量
    kline_data = await service.get_kline_data(stock_id, test_date, days_before=60, days_after=0)
    print(f"获取到{len(kline_data)}条K线数据")

    if len(kline_data) > 0:
        dates = [d['trade_date'] for d in kline_data]
        dates.sort()
        print(f"日期范围: {dates[0]} 到 {dates[-1]}")

    # 高级分析
    advanced_result = await service.analyze_advanced_support(stock_id, test_date, lookback_days=60)

    print(f"\n高级分析结果:")
    print(f"  has_advanced_analysis: {advanced_result.get('has_advanced_analysis', False)}")

    if 'error' in advanced_result:
        print(f"  错误: {advanced_result['error']}")

    data_summary = advanced_result.get('data_summary', {})
    print(f"  数据摘要: {data_summary}")

    # 斐波那契分析结果
    fib_levels = advanced_result.get('fibonacci_levels', {})
    if fib_levels.get('has_fibonacci', False):
        print(f"  ✅ 斐波那契分析可用")
        print(f"    波动范围: {fib_levels.get('swing_low', 0):.2f} - {fib_levels.get('swing_high', 0):.2f}")
        print(f"    当前价格: {fib_levels.get('current_price', 0):.2f}")
    else:
        print(f"  ❌ 斐波那契分析不可用: 数据不足或计算失败")

    # 成交量分布
    volume_profile = advanced_result.get('volume_profile', {})
    if volume_profile.get('has_volume_profile', False):
        print(f"  ✅ 成交量分布可用")
    else:
        print(f"  ❌ 成交量分布不可用")

    # 枢轴点
    pivot_points = advanced_result.get('pivot_points', {})
    if pivot_points.get('has_pivot_points', False):
        print(f"  ✅ 枢轴点分析可用")
        daily_pivots = pivot_points.get('daily_pivots', {})
        if daily_pivots:
            print(f"    日线枢轴点(P): {daily_pivots.get('pivot', 0):.2f}")
    else:
        print(f"  ❌ 枢轴点分析不可用")

    # 多时间框架
    multi_timeframe = advanced_result.get('multi_timeframe_levels', {})
    if multi_timeframe.get('has_multi_timeframe', False):
        print(f"  ✅ 多时间框架分析可用")
    else:
        print(f"  ❌ 多时间框架分析不可用")

    # 信号
    signals = advanced_result.get('advanced_signals', [])
    if signals:
        print(f"  📊 技术信号:")
        for signal in signals:
            print(f"    • {signal}")
    else:
        print(f"  ⚠️  无技术信号")

    await service.close()

async def main():
    await test_shenjian_advanced()

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
使用数据充足的股票测试高级压力支撑分析功能
"""
import asyncio
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.kline_data_service import KlineDataService

async def test_advanced_support_with_data(stock_id, stock_name, test_date):
    print(f"\n测试高级压力支撑分析 - {stock_name}({stock_id}) - {test_date}")
    print("=" * 80)

    # 创建服务实例
    service = KlineDataService()

    # 测试高级支撑分析
    print("1. 高级压力支撑分析 (analyze_advanced_support):")
    print("-" * 40)

    advanced_result = await service.analyze_advanced_support(stock_id, test_date, lookback_days=60)

    if not advanced_result.get('has_advanced_analysis', False):
        print(f"  错误: {advanced_result.get('error', '未知错误')}")
        await service.close()
        return False

    # 斐波那契分析结果
    fib_levels = advanced_result.get('fibonacci_levels', {})
    if fib_levels.get('has_fibonacci', False):
        print("  ✅ 斐波那契分析:")
        print(f"    波动范围: {fib_levels.get('swing_low', 0):.2f} - {fib_levels.get('swing_high', 0):.2f}")
        print(f"    当前价格: {fib_levels.get('current_price', 0):.2f}")

        nearest_support = fib_levels.get('nearest_support')
        nearest_resistance = fib_levels.get('nearest_resistance')

        if nearest_support:
            print(f"    最近支撑: {nearest_support['price']:.2f} ({nearest_support['level']}, 距离{nearest_support['distance_pct']:.1f}%)")
        if nearest_resistance:
            print(f"    最近阻力: {nearest_resistance['price']:.2f} ({nearest_resistance['level']}, 距离{nearest_resistance['distance_pct']:.1f}%)")

        # 打印关键回撤位
        levels = fib_levels.get('levels', {})
        print("    关键回撤位:")
        for key, fib_info in sorted(levels.items()):
            if fib_info['type'] == 'retracement':
                print(f"      {key}: {fib_info['price']:.2f} ({fib_info['level']:.1f}%)")
    else:
        print("  ❌ 斐波那契分析失败")

    # 成交量分布分析
    volume_profile = advanced_result.get('volume_profile', {})
    if volume_profile.get('has_volume_profile', False):
        print("\n  ✅ 成交量分布分析:")
        high_volume_nodes = volume_profile.get('high_volume_nodes', [])
        if high_volume_nodes:
            print("    高成交量节点 (前3个):")
            for i, node in enumerate(high_volume_nodes[:3], 1):
                print(f"      {i}. 价格区间: {node['price_range']}, 中点: {node['mid_price']:.2f}, 成交量强度: {node['strength']:.2f}")

        volume_signals = volume_profile.get('volume_profile_signals', [])
        if volume_signals:
            print("    成交量信号:")
            for signal in volume_signals:
                print(f"      - {signal}")
    else:
        print("\n  ⚠️  成交量分布分析不可用")

    # 枢轴点分析
    pivot_points = advanced_result.get('pivot_points', {})
    if pivot_points.get('has_pivot_points', False):
        print("\n  ✅ 枢轴点分析:")

        daily_pivots = pivot_points.get('daily_pivots', {})
        if daily_pivots:
            print("    日线枢轴点:")
            print(f"      枢轴点(P): {daily_pivots.get('pivot', 0):.2f}")
            print(f"      支撑位: S1={daily_pivots.get('support1', 0):.2f}, S2={daily_pivots.get('support2', 0):.2f}")
            print(f"      阻力位: R1={daily_pivots.get('resistance1', 0):.2f}, R2={daily_pivots.get('resistance2', 0):.2f}")

        weekly_pivots = pivot_points.get('weekly_pivots', {})
        if weekly_pivots:
            print("    周线枢轴点:")
            print(f"      枢轴点: {weekly_pivots.get('pivot', 0):.2f}")
            print(f"      支撑位: S1={weekly_pivots.get('support1', 0):.2f}")
            print(f"      阻力位: R1={weekly_pivots.get('resistance1', 0):.2f}")
    else:
        print("\n  ⚠️  枢轴点分析不可用")

    # 多时间框架分析
    multi_timeframe = advanced_result.get('multi_timeframe_levels', {})
    if multi_timeframe.get('has_multi_timeframe', False):
        print("\n  ✅ 多时间框架分析:")

        daily_levels = multi_timeframe.get('daily_levels', {})
        if daily_levels:
            print(f"    日线关键位: 支撑={daily_levels.get('support', 0):.2f}, 阻力={daily_levels.get('resistance', 0):.2f}")

        weekly_levels = multi_timeframe.get('weekly_levels', {})
        if weekly_levels:
            print(f"    周线关键位: 支撑={weekly_levels.get('support', 0):.2f}, 阻力={weekly_levels.get('resistance', 0):.2f}")

        monthly_levels = multi_timeframe.get('monthly_levels', {})
        if monthly_levels:
            print(f"    月线关键位: 支撑={monthly_levels.get('support', 0):.2f}, 阻力={monthly_levels.get('resistance', 0):.2f}")
    else:
        print("\n  ⚠️  多时间框架分析不可用")

    # 综合信号
    advanced_signals = advanced_result.get('advanced_signals', [])
    if advanced_signals:
        print("\n  📊 综合技术信号:")
        for signal in advanced_signals:
            print(f"    • {signal}")
    else:
        print("\n  ⚠️  无综合技术信号")

    await service.close()
    return True

async def main():
    print("测试高级压力支撑分析功能（使用数据充足的股票）")
    print("=" * 80)

    # 测试几只数据充足的股票
    test_cases = [
        ("002335", "科华数据", date(2026, 4, 7)),  # 315条数据
        ("301236", "软通动力", date(2026, 4, 7)),  # 280条数据
        ("000034", "神州数码", date(2026, 4, 7)),  # 273条数据
    ]

    success_count = 0
    total_count = len(test_cases)

    for stock_id, stock_name, test_date in test_cases:
        try:
            success = await test_advanced_support_with_data(stock_id, stock_name, test_date)
            if success:
                success_count += 1
        except Exception as e:
            print(f"\n❌ 测试{stock_name}({stock_id})时出现错误: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("测试总结:")
    print(f"  总测试股票数: {total_count}")
    print(f"  成功测试数: {success_count}")
    print(f"  成功率: {success_count/total_count*100:.1f}%")

    if success_count == total_count:
        print("  ✅ 所有股票高级分析测试成功！")
    else:
        print(f"  ⚠️  {total_count-success_count}只股票测试失败")

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
测试高级压力支撑分析功能
"""
import asyncio
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.kline_data_service import KlineDataService

async def test_advanced_support():
    stock_id = "002361"
    test_date = date(2026, 4, 7)

    print(f"测试高级压力支撑分析 - 神剑股份({stock_id}) - {test_date}")
    print("=" * 80)

    # 创建服务实例
    service = KlineDataService()

    # 测试高级支撑分析
    print("1. 高级压力支撑分析 (analyze_advanced_support):")
    print("-" * 40)

    advanced_result = await service.analyze_advanced_support(stock_id, test_date, lookback_days=60)

    if not advanced_result.get('has_advanced_analysis', False):
        print(f"  错误: {advanced_result.get('error', '未知错误')}")
        # 仍然继续普通支撑分析测试
        advanced_result = {'has_advanced_analysis': False}

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

    # 对比测试：与普通缺口支撑分析比较
    print("\n2. 对比测试 - 普通缺口支撑分析 (analyze_gap_support):")
    print("-" * 40)

    gap_result = await service.analyze_gap_support(stock_id, test_date)

    print(f"  是否有支撑: {gap_result.get('has_support', False)}")
    print(f"  支撑强度: {gap_result.get('support_strength', 0):.2f}")
    print(f"  支撑类型: {gap_result.get('support_type', 'unknown')}")
    print(f"  支撑位: {gap_result.get('support_level', 0):.2f}")

    technical_signals = gap_result.get('technical_signals', [])
    if technical_signals:
        print("  技术信号:")
        for signal in technical_signals:
            print(f"    - {signal}")

    print("\n3. 对比分析总结:")
    print("-" * 40)

    # 高级分析的主要支撑位
    primary_support = None
    if fib_levels.get('nearest_support'):
        fib_support = fib_levels['nearest_support']['price']
        fib_distance = fib_levels['nearest_support']['distance_pct']
        primary_support = (fib_support, f"斐波那契支撑位 ({fib_distance:.1f}%)")
        print(f"  斐波那契最近支撑: {fib_support:.2f} (距离{fib_distance:.1f}%)")

    # 普通分析的支撑位
    gap_support = gap_result.get('support_level', 0)
    gap_strength = gap_result.get('support_strength', 0)
    print(f"  普通支撑分析: {gap_support:.2f} (强度{gap_strength:.2f})")

    # 判断是否到达关键支撑
    current_price = fib_levels.get('current_price', 0)
    if current_price > 0:
        print(f"  当前价格: {current_price:.2f}")

        # 检查是否接近关键支撑（3%以内）
        if primary_support:
            support_price, support_desc = primary_support
            distance_pct = abs(current_price - support_price) / current_price * 100
            if distance_pct < 3:
                print(f"  🎯 价格接近关键支撑位 {support_price:.2f} ({support_desc}, 距离{distance_pct:.1f}%)")
            else:
                print(f"  ⚠️  价格距离关键支撑位较远 (距离{distance_pct:.1f}%)")

    await service.close()

    return advanced_result, gap_result

async def main():
    try:
        results = await test_advanced_support()
        if results is None:
            print("\n❌ 测试提前终止")
            return

        advanced_result, gap_result = results

        print("\n" + "=" * 80)
        print("高级压力支撑分析测试完成!")
        print(f"  高级分析可用: {advanced_result.get('has_advanced_analysis', False)}")
        print(f"  普通支撑分析可用: {gap_result.get('has_support', False)}")

    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
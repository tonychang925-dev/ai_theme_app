#!/usr/bin/env python3
"""
测试缺口分析方法
"""
import asyncio
import sys
import os
from datetime import date

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.kline_data_service import KlineDataService

async def test_gap_analysis():
    stock_id = "002361"
    test_date = date(2026, 4, 7)

    print(f"测试缺口分析方法 - {stock_id} - {test_date}")
    print("=" * 80)

    service = KlineDataService()

    # 1. 测试analyze_gap_support
    print("1. 测试analyze_gap_support (只检查前5天):")
    gap_result = await service.analyze_gap_support(stock_id, test_date)

    print(f"  has_gap: {gap_result.get('has_gap', False)}")
    print(f"  gap_type: {gap_result.get('gap_type', '')}")
    print(f"  gap_size: {gap_result.get('gap_size', 0.0):.2f}%")
    print(f"  has_support: {gap_result.get('has_support', False)}")
    print(f"  support_strength: {gap_result.get('support_strength', 0.0):.1f}")
    print(f"  is_gap_support: {gap_result.get('is_gap_support', False)}")
    print(f"  support_type: {gap_result.get('support_type', '')}")
    print(f"  gap_support_level: {gap_result.get('gap_support_level', 0.0):.2f}")

    # 显示技术信号
    signals = gap_result.get('technical_signals', [])
    if signals:
        print(f"  技术信号:")
        for signal in signals:
            print(f"    • {signal}")

    # 2. 获取原始K线数据
    print(f"\n2. 原始K线数据 (前5天):")
    kline_data = await service.get_kline_data(stock_id, test_date, days_before=5, days_after=0)

    print(f"  获取到{len(kline_data)}条数据")
    for i, kline in enumerate(kline_data):
        trade_date = kline['trade_date']
        open_price = kline.get('open_price', 0)
        close_price = kline.get('close_price', 0)
        pct_chg = kline.get('pct_chg', 0)
        print(f"  {i+1}. {trade_date}: 开盘{open_price:.2f}, 收盘{close_price:.2f}, 涨跌幅{pct_chg:.1f}%")

    # 3. 手动分析缺口
    print(f"\n3. 手动分析缺口:")
    if len(kline_data) >= 2:
        # 找到分析日
        target_kline = None
        prev_kline = None

        for kline in kline_data:
            if kline['trade_date'] == test_date:
                target_kline = kline
            elif target_kline is None and kline['trade_date'] < test_date:
                prev_kline = kline

        if target_kline and prev_kline:
            current_low = target_kline.get('low_price', 0)
            current_open = target_kline.get('open_price', 0)
            prev_high = prev_kline.get('high_price', 0)
            prev_low = prev_kline.get('low_price', 0)
            prev_close = prev_kline.get('close_price', 0)

            print(f"  分析日: {test_date}, 最低价: {current_low:.2f}")
            print(f"  前一日: {prev_kline['trade_date']}, 最高价: {prev_high:.2f}, 收盘价: {prev_close:.2f}")

            # 检查缺口
            gap_threshold = 0.001  # 0.1%
            if current_low > prev_high * (1 + gap_threshold):
                print(f"  ✅ 检测到向上缺口: {current_low:.2f} > {prev_high:.2f}")
            elif current_open < prev_low * (1 - gap_threshold):
                print(f"  ✅ 检测到向下缺口: {current_open:.2f} < {prev_low:.2f}")
            else:
                print(f"  ❌ 未检测到缺口 (当前最低价{current_low:.2f}, 前一日最高价{prev_high:.2f})")

    await service.close()

async def main():
    try:
        await test_gap_analysis()
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
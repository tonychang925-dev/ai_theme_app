#!/usr/bin/env python3
"""
测试神剑股份的缺口支撑分析
"""
import asyncio
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.kline_data_service import KlineDataService

async def test_gap_analysis():
    stock_id = "002361"
    dates = [date(2026, 4, 3), date(2026, 4, 7)]

    service = KlineDataService()

    for analysis_date in dates:
        print(f"\n测试神剑股份缺口支撑分析 - {analysis_date}")
        print("=" * 70)

        # 使用KlineDataService的analyze_gap_support方法
        result = await service.analyze_gap_support(stock_id, analysis_date)
        print(f"has_gap: {result.get('has_gap')}")
        print(f"gap_type: {result.get('gap_type')}")
        print(f"has_support: {result.get('has_support')}")
        print(f"support_type: {result.get('support_type')}")
        print(f"support_strength: {result.get('support_strength')}")
        print(f"is_gap_support: {result.get('is_gap_support')}")
        print(f"technical_signals: {result.get('technical_signals')}")

        # 获取更多历史数据（20天），以检测3/31的缺口
        print(f"\n获取{stock_id}的历史K线数据...")
        kline_data = await service.get_kline_data(stock_id, analysis_date, days_before=20, days_after=0)

        print(f"获取到{len(kline_data)}条K线数据:")
        for kline in sorted(kline_data, key=lambda x: x['trade_date'])[-5:]:  # 只显示最近5天
            date_str = kline['trade_date'].strftime("%Y-%m-%d")
            print(f"  {date_str}: O{kline['open_price']:.2f} H{kline['high_price']:.2f} "
                  f"L{kline['low_price']:.2f} C{kline['close_price']:.2f} ({kline['pct_chg']:.1f}%)")

    # 找到3/31和4/1的数据
    data_by_date = {k['trade_date']: k for k in kline_data}

    date_0331 = date(2026, 3, 31)
    date_0401 = date(2026, 4, 1)

    if date_0331 in data_by_date and date_0401 in data_by_date:
        kline_0331 = data_by_date[date_0331]
        kline_0401 = data_by_date[date_0401]

        print(f"  3/31: 收盘价 {kline_0331['close_price']:.2f}")
        print(f"  4/1: 开盘价 {kline_0401['open_price']:.2f}")

        # 计算缺口
        gap = kline_0401['open_price'] - kline_0331['close_price']
        gap_pct = gap / kline_0331['close_price'] * 100

        print(f"  缺口大小: {gap:.2f} ({gap_pct:.2f}%)")
        print(f"  缺口区间: [{kline_0331['close_price']:.2f}, {kline_0401['open_price']:.2f}]")

        # 检查4/7是否回补缺口
        kline_0407 = data_by_date.get(analysis_date)
        if kline_0407:
            print(f"\n  4/7数据:")
            print(f"    最低价: {kline_0407['low_price']:.2f}")
            print(f"    是否低于缺口下沿({kline_0331['close_price']:.2f}): {'✅是' if kline_0407['low_price'] < kline_0331['close_price'] else '❌否'}")
            print(f"    是否在缺口区间内: {'✅是' if kline_0331['close_price'] <= kline_0407['low_price'] <= kline_0401['open_price'] else '❌否'}")

            # 真正的回补：价格跌破缺口下沿
            if kline_0407['low_price'] < kline_0331['close_price']:
                print(f"  ✅ 价格已回补缺口（跌破缺口下沿）")
            elif kline_0331['close_price'] <= kline_0407['low_price'] <= kline_0401['open_price']:
                print(f"  ⚠️  价格在缺口区间内")
            else:
                print(f"  ❌ 价格未回补缺口")

    # 使用服务分析缺口支撑
    print(f"\n使用KlineDataService.analyze_gap_support分析:")
    gap_analysis = await service.analyze_gap_support(stock_id, analysis_date)

    print(f"  结果:")
    for key, value in gap_analysis.items():
        if key == 'technical_signals':
            print(f"    {key}:")
            for signal in value:
                print(f"      - {signal}")
        else:
            print(f"    {key}: {value}")

    await service.close()

if __name__ == "__main__":
    asyncio.run(test_gap_analysis())
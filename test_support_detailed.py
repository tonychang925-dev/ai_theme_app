#!/usr/bin/env python3
"""
详细测试支撑位检测逻辑
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_shenjian_detailed():
    """详细测试神剑股份支撑位检测"""
    print("详细测试神剑股份(002361)支撑位检测逻辑")
    print("=" * 70)

    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)
    stock_id = "002361"

    try:
        # 获取K线数据
        kline_data = await builder.kline_service.get_kline_data(stock_id, test_date, days_before=5, days_after=0)
        print(f"获取到 {len(kline_data)} 条K线数据:")
        for i, kline in enumerate(kline_data):
            print(f"  {i}. {kline.get('trade_date')}: "
                  f"O:{kline.get('open_price', 0):.2f} H:{kline.get('high_price', 0):.2f} "
                  f"L:{kline.get('low_price', 0):.2f} C:{kline.get('close_price', 0):.2f} "
                  f"涨跌幅:{kline.get('pct_chg', 0):.2f}%")

        # 手动执行支撑检测逻辑
        if len(kline_data) >= 2:
            target_kline = None
            prev_kline = None

            for kline in kline_data:
                if kline['trade_date'] == test_date:
                    target_kline = kline
                elif target_kline is None and kline['trade_date'] < test_date:
                    prev_kline = kline

            print(f"\ntarget_kline: {target_kline is not None}")
            print(f"prev_kline: {prev_kline is not None}")

            if target_kline and prev_kline:
                current_low = target_kline.get('low_price', 0)
                prev_low = prev_kline.get('low_price', 0)

                print(f"\n价格数据:")
                print(f"  当前最低价: {current_low:.2f}")
                print(f"  前一日最低价: {prev_low:.2f}")

                # 检查前一日低点支撑
                if prev_low > 0 and current_low > 0:
                    distance_pct = abs(current_low - prev_low) / prev_low * 100
                    print(f"  距离前一日低点: {distance_pct:.2f}%")
                    print(f"  是否<7%: {distance_pct < 7.0}")

                # 检查整数关口支撑
                if current_low > 0:
                    print(f"\n整数关口检查:")
                    integer_levels = [1.00, 2.00, 5.00, 10.00, 20.00, 50.00]
                    for base in integer_levels:
                        for multiplier in [0.5, 1.0, 1.5, 2.0]:
                            level = base * multiplier
                            distance = abs(current_low - level) / level * 100
                            if distance < 2.0:
                                print(f"  检测到整数关口: {level:.2f} (距离: {distance:.2f}%)")

                # 检查缺口支撑
                print(f"\n缺口支撑检查:")
                gap_analysis = await builder.kline_service.analyze_gap_support(stock_id, test_date)
                print(f"  gap_analysis结果: {gap_analysis}")

        # 调用原始的analyze_strict_support方法
        print(f"\n调用analyze_strict_support方法:")
        result = await builder.analyze_strict_support(stock_id, 0.0, test_date)
        print(f"  结果: {result}")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def main():
    """主测试函数"""
    await test_shenjian_detailed()

if __name__ == "__main__":
    asyncio.run(main())
#!/usr/bin/env python3
"""
直接测试神剑股份(002361)的缺口支撑分析
"""
import asyncio
from datetime import date
from stock_service.services.kline_data_service import KlineDataService
from stock_service.config import StockServiceConfig

async def test_shenjian_gap_support():
    """测试神剑股份缺口支撑分析"""
    config = StockServiceConfig()
    service = KlineDataService({
        "host": config.postgres_host,
        "port": config.postgres_port,
        "database": config.postgres_database,
        "user": config.postgres_user,
        "password": config.postgres_password
    })

    test_date = date(2026, 4, 7)
    stock_id = "002361"

    print(f"测试神剑股份({stock_id})缺口支撑分析 - {test_date}")
    print("=" * 70)

    try:
        # 直接调用缺口支撑分析
        result = await service.analyze_gap_support(stock_id, test_date)

        print(f"缺口分析结果:")
        print(f"  has_gap: {result.get('has_gap')}")
        print(f"  gap_type: {result.get('gap_type')}")
        print(f"  gap_size: {result.get('gap_size')}")
        print(f"  has_support: {result.get('has_support')}")
        print(f"  support_type: {result.get('support_type')}")
        print(f"  support_strength: {result.get('support_strength')}")
        print(f"  is_gap_support: {result.get('is_gap_support')}")
        print(f"  gap_support_level: {result.get('gap_support_level')}")

        print(f"\n技术信号:")
        for signal in result.get('technical_signals', []):
            print(f"  - {signal}")

        # 获取K线数据
        kline_data = await service.get_kline_data(stock_id, test_date, days_before=5, days_after=0)
        print(f"\nK线数据 ({len(kline_data)} 条):")
        for i, kline in enumerate(kline_data):
            print(f"  {i}. {kline.get('trade_date')}: "
                  f"O:{kline.get('open_price', 0):.2f} H:{kline.get('high_price', 0):.2f} "
                  f"L:{kline.get('low_price', 0):.2f} C:{kline.get('close_price', 0):.2f} "
                  f"涨跌幅:{kline.get('pct_chg', 0):.2f}%")

        # 检查是否有缺口支撑的条件
        if len(kline_data) >= 2:
            target_kline = None
            prev_kline = None

            for kline in kline_data:
                if kline['trade_date'] == test_date:
                    target_kline = kline
                elif target_kline is None and kline['trade_date'] < test_date:
                    prev_kline = kline

            if target_kline and prev_kline:
                print(f"\n详细缺口分析:")
                print(f"  当前日: {target_kline.get('trade_date')}")
                print(f"    最低价: {target_kline.get('low_price', 0):.2f}")
                print(f"    开盘价: {target_kline.get('open_price', 0):.2f}")
                print(f"  前一日: {prev_kline.get('trade_date')}")
                print(f"    最高价: {prev_kline.get('high_price', 0):.2f}")
                print(f"    最低价: {prev_kline.get('low_price', 0):.2f}")

                # 检查向上缺口条件
                gap_threshold = 0.001  # 0.1%
                current_low = target_kline.get('low_price', 0)
                prev_high = prev_kline.get('high_price', 0)

                print(f"\n缺口检查:")
                print(f"  当前最低价: {current_low:.2f}")
                print(f"  前一日最高价: {prev_high:.2f}")
                print(f"  阈值: {gap_threshold*100}%")
                print(f"  缺口条件: current_low > prev_high * (1 + {gap_threshold})")
                print(f"           {current_low:.2f} > {prev_high:.2f} * {1 + gap_threshold:.4f}")
                print(f"           {current_low:.2f} > {prev_high * (1 + gap_threshold):.2f}")
                print(f"           {current_low > prev_high * (1 + gap_threshold)}")

                # 检查是否在缺口支撑附近
                if result.get('gap_support_level', 0) > 0:
                    gap_support = result['gap_support_level']
                    print(f"\n缺口支撑检查:")
                    print(f"  缺口支撑位: {gap_support:.2f}")
                    print(f"  当前最低价: {current_low:.2f}")
                    print(f"  是否在1%范围内: {current_low >= gap_support * 0.99 and current_low <= gap_support * 1.01}")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await service.close()

async def main():
    """主测试函数"""
    print("开始测试神剑股份缺口支撑分析...")
    print("=" * 70)
    await test_shenjian_gap_support()

if __name__ == "__main__":
    asyncio.run(main())
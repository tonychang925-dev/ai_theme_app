#!/usr/bin/env python3
"""
检查新候选股票的K线数据
"""
import asyncio
from datetime import date
from stock_service.services.kline_data_service import KlineDataService

async def test_new_candidates():
    """测试新候选股票的K线数据"""
    service = KlineDataService()

    candidates = [
        ("603151", date(2026, 4, 10), "邦基科技"),
        ("301667", date(2026, 4, 10), "纳百川"),
        ("603758", date(2026, 4, 10), "秦安股份"),
    ]

    print("新候选股票K线数据分析")
    print("=" * 70)

    for stock_id, analysis_date, stock_name in candidates:
        print(f"\n{stock_name} ({stock_id}) - {analysis_date}")

        try:
            # 检查股票是否存在
            exists = await service.check_stock_exists(stock_id)
            print(f"  股票存在: {exists}")

            if exists:
                # 获取K线数据
                kline_data = await service.get_kline_data(stock_id, analysis_date, days_before=3, days_after=0)
                print(f"  K线数据条数: {len(kline_data)}")

                if kline_data:
                    for kline in kline_data:
                        print(f"    {kline['trade_date']}: O{kline.get('open_price', 0):.2f} "
                              f"H{kline.get('high_price', 0):.2f} L{kline.get('low_price', 0):.2f} "
                              f"C{kline.get('close_price', 0):.2f} ({kline.get('pct_chg', 0):.2f}%)")

                # 分析缺口支撑
                gap_analysis = await service.analyze_gap_support(stock_id, analysis_date)

                print(f"  缺口分析:")
                print(f"    has_gap: {gap_analysis.get('has_gap', False)}")
                print(f"    gap_type: {gap_analysis.get('gap_type', '')}")
                print(f"    gap_size: {gap_analysis.get('gap_size', 0.0):.2f}%")
                print(f"    has_support: {gap_analysis.get('has_support', False)}")
                print(f"    support_type: {gap_analysis.get('support_type', '')}")
                print(f"    support_strength: {gap_analysis.get('support_strength', 0.0):.2f}")
                print(f"    is_gap_support: {gap_analysis.get('is_gap_support', False)}")

                if gap_analysis.get('technical_signals'):
                    print(f"    技术信号:")
                    for signal in gap_analysis['technical_signals']:
                        print(f"      - {signal}")
                else:
                    print(f"    技术信号: 无")
            else:
                print(f"  未找到股票数据")

        except Exception as e:
            print(f"  分析失败: {e}")

    await service.close()
    print("\n" + "=" * 70)
    print("分析完成")

if __name__ == "__main__":
    asyncio.run(test_new_candidates())
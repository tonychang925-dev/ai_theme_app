#!/usr/bin/env python3
"""
测试KlineDataService与WeakToStrongService的集成
验证WeakToStrongService现在可以从数据库获取真实K线数据进行缺口支撑分析
"""

import asyncio
import sys
import os
from datetime import date, datetime, timedelta

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongDetectionInputs
from stock_service.models import ThemeCycleJudgement, StockAbnormalSignal
from stock_service.services.kline_data_service import KlineDataService

async def test_kline_data_service():
    """测试KlineDataService"""
    print("=" * 70)
    print("测试KlineDataService数据库连接和K线数据获取")
    print("=" * 70)

    service = KlineDataService()

    # 测试股票：神剑股份（数据库中是002361，不带后缀）
    stock_id = "002361"
    test_date = date(2026, 4, 10)

    print(f"测试股票: {stock_id}")
    print(f"测试日期: {test_date}")

    try:
        # 1. 检查股票是否存在
        exists = await service.check_stock_exists(stock_id)
        print(f"股票存在: {exists}")

        if exists:
            # 2. 获取K线数据
            kline_data = await service.get_kline_data(stock_id, test_date, days_before=3, days_after=0)
            print(f"获取到{len(kline_data)}条K线数据")

            if kline_data:
                for kline in kline_data:
                    print(f"  {kline['trade_date']}: O{kline.get('open_price', 0):.2f} "
                          f"H{kline.get('high_price', 0):.2f} L{kline.get('low_price', 0):.2f} "
                          f"C{kline.get('close_price', 0):.2f} ({kline.get('pct_chg', 0):.2f}%)")

            # 3. 分析缺口支撑
            print(f"\n分析缺口支撑...")
            gap_analysis = await service.analyze_gap_support(stock_id, test_date)

            print(f"缺口分析结果:")
            print(f"  has_gap: {gap_analysis.get('has_gap', False)}")
            print(f"  gap_type: {gap_analysis.get('gap_type', '')}")
            print(f"  gap_size: {gap_analysis.get('gap_size', 0.0):.2f}%")
            print(f"  has_support: {gap_analysis.get('has_support', False)}")
            print(f"  support_type: {gap_analysis.get('support_type', '')}")
            print(f"  is_gap_support: {gap_analysis.get('is_gap_support', False)}")

            if gap_analysis.get('technical_signals'):
                print(f"  技术信号:")
                for signal in gap_analysis['technical_signals']:
                    print(f"    - {signal}")

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await service.close()

    print("\n" + "=" * 70)
    print("KlineDataService测试完成")
    print("=" * 70)

async def test_weak_to_strong_integration():
    """测试WeakToStrongService与KlineDataService的集成"""
    print("\n" + "=" * 70)
    print("测试WeakToStrongService与KlineDataService集成")
    print("=" * 70)

    # 创建带有KlineDataService的WeakToStrongService
    kline_service = KlineDataService()
    weak_to_strong_service = WeakToStrongService(kline_data_service=kline_service)

    print(f"WeakToStrongService已初始化，kline_data_service: {weak_to_strong_service.kline_data_service is not None}")

    # 创建模拟输入，但包含真实的股票ID和日期
    stock_id = "002361"
    trade_date = date(2026, 4, 10)

    # 创建模拟cycle_judgement，包含股票ID
    cycle_judgement = ThemeCycleJudgement(
        trade_date=trade_date.isoformat(),
        subject_key=stock_id,  # 使用股票ID作为subject_key
        theme_name="神剑股份",
        is_main_theme=True,
        is_start=False,
        is_fermentation=False,
        is_divergence=True,
        is_rebound=True,
        is_climax=False,
        is_fade=False,
        primary_cycle_stage="rebound",
        limit_up_count=0,
        leader_status="none",
        board_effect_status="weak",
        action_bias="弱转强",
        confidence=75.0,
        conclusion="分歧后回流，弱转强信号"
    )

    # 创建模拟inputs，包含前一日和当日数据（但可能为空，因为我们会使用数据库数据）
    inputs = WeakToStrongDetectionInputs(
        cycle_judgement=cycle_judgement,
        abnormal_signal=None,
        prev_day_data={'trade_date': '2026-04-09'},  # 只提供日期字段
        current_day_data={'trade_date': '2026-04-10'},
        market_environment={"mode": "offensive", "position_limit": 1.0}
    )

    try:
        # 检测弱转强信号
        print(f"\n检测股票{stock_id}在{trade_date}的弱转强信号...")
        signals = await weak_to_strong_service.detect_weak_to_strong_signals(trade_date, inputs)

        print(f"检测到{len(signals)}个弱转强信号")

        if signals:
            for signal in signals:
                print(f"\n弱转强信号:")
                print(f"  股票: {signal.stock_name} ({signal.stock_id})")
                print(f"  信号类型: {signal.signal_type}")
                print(f"  信号强度: {signal.signal_strength:.1f}")
                print(f"  置信度: {signal.confidence_score:.1f}")
                print(f"  是否有支撑: {signal.has_support}")
                print(f"  支撑类型: {signal.support_type}")
                print(f"  是否缺口支撑: {signal.is_gap_support}")

                # 检查证据中是否有数据库技术信号
                if signal.evidence:
                    db_signals = [e for e in signal.evidence if '缺口' in e or '支撑' in e]
                    if db_signals:
                        print(f"  数据库技术信号:")
                        for sig in db_signals:
                            print(f"    - {sig}")

        # 测试_analyze_support_and_gaps方法直接调用
        print(f"\n直接测试_analyze_support_and_gaps方法...")
        support_analysis = await weak_to_strong_service._analyze_support_and_gaps(
            prev_day_data={'trade_date': '2026-04-09'},
            current_day_data={'trade_date': '2026-04-10'},
            stock_id=stock_id,
            analysis_date=trade_date
        )

        print(f"支撑缺口分析结果:")
        print(f"  has_gap: {support_analysis.get('has_gap', False)}")
        print(f"  gap_type: {support_analysis.get('gap_type', '')}")
        print(f"  has_support: {support_analysis.get('has_support', False)}")
        print(f"  support_type: {support_analysis.get('support_type', '')}")
        print(f"  技术信号数量: {len(support_analysis.get('technical_signals', []))}")

    except Exception as e:
        print(f"集成测试失败: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await kline_service.close()

    print("\n" + "=" * 70)
    print("集成测试完成")
    print("=" * 70)

async def main():
    """主测试函数"""
    print("开始测试KlineDataService与WeakToStrongService集成")
    print(f"当前时间: {datetime.now()}")

    # 运行KlineDataService测试
    await test_kline_data_service()

    # 运行集成测试
    await test_weak_to_strong_integration()

    print("\n所有测试完成!")

if __name__ == "__main__":
    asyncio.run(main())
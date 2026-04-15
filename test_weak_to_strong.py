#!/usr/bin/env python3
"""
测试弱转强策略
重点测试神剑股份（002361）在2026-04-07的弱转强信号
"""

import asyncio
import sys
import os
from datetime import date

# 添加stock_service到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongDetectionInputs
from stock_service.services.strategy_decision_service import StrategyDecisionService


def test_weak_to_strong_service():
    """测试弱转强服务基本功能"""
    print("=== 测试弱转强服务 ===")

    # 创建服务实例
    service = WeakToStrongService()

    # 模拟神剑股份（002361）在4/7的数据
    # 根据用户描述：4/7下跌到缺口位置，4/8强势涨停
    # 这是一个典型的弱转强案例

    # 模拟周期判断数据
    cycle_judgement = {
        "is_divergence": True,      # 4/7处于分歧状态
        "is_rebound": False,        # 尚未反弹（4/7）
        "action_bias": "分歧",      # 分歧阶段
        "stage_label": "decline",   # 下跌阶段
        "confidence_score": 75.0,
        "reasoning": "股价下跌到缺口位置，面临支撑"
    }

    # 模拟前一日（4/6）数据
    prev_day_data = {
        "close": 10.50,     # 4/6收盘价
        "high": 10.80,
        "low": 10.30,
        "open": 10.40,
        "volume": 5000000,
        "pct_chg": -1.5     # 下跌1.5%
    }

    # 模拟当日（4/7）数据
    current_day_data = {
        "close": 10.20,     # 4/7收盘价，继续下跌
        "high": 10.45,
        "low": 10.00,       # 跌到缺口位置
        "open": 10.35,
        "volume": 6000000,  # 放量
        "pct_chg": -2.8     # 下跌2.8%
    }

    # 模拟K线历史数据（用于分析支撑位）
    historical_data = [
        # 假设前几日数据，用于计算移动平均线
        {"close": 10.80, "low": 10.50},
        {"close": 10.70, "low": 10.45},
        {"close": 10.60, "low": 10.40},
        {"close": 10.50, "low": 10.30},  # 4/6
        {"close": 10.20, "low": 10.00},  # 4/7
    ]

    # 构建检测输入
    inputs = WeakToStrongDetectionInputs(
        stock_id="002361.SZ",
        stock_name="神剑股份",
        trade_date=date(2026, 4, 7),
        cycle_judgement=cycle_judgement,
        prev_day_data=prev_day_data,
        current_day_data=current_day_data,
        historical_data=historical_data,
        market_state="cautious",  # 谨慎模式
        main_theme_count=1        # 有主线题材
    )

    # 检测弱转强信号
    result = service.detect_weak_to_strong_signals(inputs)

    print(f"股票: {result.stock_name} ({result.stock_id})")
    print(f"交易日: {result.trade_date}")
    print(f"弱转强判断: {result.judgement}")
    print(f"置信度: {result.confidence_score:.1f}")
    print(f"信号强度: {result.signal_strength:.1f}")

    # 打印检测到的信号
    print("\n检测到的弱转强信号:")
    for signal in result.signals:
        print(f"  - {signal.signal_type}: 强度={signal.signal_strength:.1f}, 置信度={signal.confidence_score:.1f}")
        if hasattr(signal, 'support_type') and signal.has_support:
            print(f"    支撑位类型: {signal.support_type}, 强度={signal.support_strength:.1f}")

    # 打印操作建议
    print(f"\n操作建议: {result.operation_advice}")
    print(f"风险评估: {result.risk_assessment}")
    if result.stop_loss_position:
        print(f"止损位: {result.stop_loss_position:.2f}")

    # 验证是否检测到弱转强信号
    expected_signals = ["支撑反弹", "放量转强", "分歧回流"]
    detected_types = [s.signal_type for s in result.signals]

    print(f"\n预期信号: {expected_signals}")
    print(f"实际检测到: {detected_types}")

    # 检查关键信号
    has_support_bounce = any(s.signal_type == "支撑反弹" for s in result.signals)
    has_volume_breakout = any(s.signal_type == "放量转强" for s in result.signals)

    print(f"支撑反弹信号: {'是' if has_support_bounce else '否'}")
    print(f"放量转强信号: {'是' if has_volume_breakout else '否'}")

    # 检查支撑位分析
    support_signals = [s for s in result.signals if hasattr(s, 'has_support') and s.has_support]
    print(f"支撑位分析: {len(support_signals)}个信号包含支撑位信息")

    if support_signals:
        for s in support_signals:
            print(f"  - {s.signal_type}: {s.support_type} (强度={s.support_strength:.1f}, 水平={s.support_level:.2f})")

    return result


async def test_strategy_decision():
    """测试策略决策服务"""
    print("\n=== 测试策略决策服务 ===")

    service = StrategyDecisionService()
    trade_date = date(2026, 4, 7)

    market_state = await service.assess_market_state(trade_date)

    print(f"市场状态: {market_state.mode}")
    print(f"操作建议: {market_state.action_bias}")
    print(f"仓位限制: {market_state.position_limit:.0%}")
    print(f"理由: {market_state.reason}")
    print(f"市场健康度: {market_state.market_health_score:.1f}")
    print(f"主线题材数量: {market_state.main_theme_count}")

    return market_state


def main():
    """主测试函数"""
    print("弱转强策略测试脚本")
    print("=" * 50)

    # 测试弱转强服务
    weak_to_strong_result = test_weak_to_strong_service()

    # 测试策略决策服务
    market_state = asyncio.run(test_strategy_decision())

    print("\n" + "=" * 50)
    print("测试总结:")
    print(f"1. 弱转强检测: {weak_to_strong_result.judgement}")
    print(f"2. 市场状态: {market_state.mode}")
    print(f"3. 仓位建议: {market_state.position_limit:.0%}")

    # 检查是否符合弱转强策略条件
    if weak_to_strong_result.judgement == "弱转强明确" and market_state.mode != "standby":
        print("\n✅ 符合弱转强策略条件: 有弱转强信号且市场非观望状态")
    else:
        print(f"\n⚠️  不符合弱转强策略条件: 弱转强信号={weak_to_strong_result.judgement}, 市场状态={market_state.mode}")


if __name__ == "__main__":
    main()
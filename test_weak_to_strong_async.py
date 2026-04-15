#!/usr/bin/env python3
"""
异步版弱转强策略测试
"""

import asyncio
import sys
import os
from datetime import date

# 添加stock_service到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongDetectionInputs
from stock_service.models import ThemeCycleJudgement


def create_mock_cycle_judgement_for_weak_to_strong():
    """创建模拟的周期判断数据（弱转强场景）"""
    return ThemeCycleJudgement(
        trade_date="2026-04-07",
        subject_key="高端制造",
        theme_name="高端制造",
        is_main_theme=True,
        is_start=False,
        is_fermentation=False,
        is_divergence=True,      # 4/7处于分歧状态
        is_rebound=True,         # 同时有反弹特征（弱转强的关键）
        is_climax=False,
        is_fade=False,
        primary_cycle_stage="divergence_to_rebound",  # 分歧转反弹
        limit_up_count=0,
        leader_status="",
        board_effect_status="分化转一致",
        action_bias="弱转强",      # 关键：操作偏向包含"弱转强"
        confidence=75.0,
        conclusion="股价下跌到缺口位置后获得支撑，出现弱转强信号",
        evidence=["前一日下跌到缺口位置", "成交量放大", "出现支撑反弹"],
        source_type="p3.phase2.cycle",
        source_trace_id="",
        source_trace={},
        source_version="theme_cycle_judgement.v1",
        rule_version="theme_cycle_judgement.v1"
    )


def create_mock_cycle_judgement_for_divergence_rebound():
    """创建模拟的分歧回流场景"""
    return ThemeCycleJudgement(
        trade_date="2026-04-07",
        subject_key="高端制造",
        theme_name="高端制造",
        is_main_theme=True,
        is_start=False,
        is_fermentation=False,
        is_divergence=True,      # 分歧
        is_rebound=True,         # 同时回流
        is_climax=False,
        is_fade=False,
        primary_cycle_stage="rebound",  # 回流阶段
        limit_up_count=1,
        leader_status="潜在龙头",
        board_effect_status="回流",
        action_bias="分歧回流",      # 分歧回流
        confidence=80.0,
        conclusion="分歧后出现资金回流，形成弱转强",
        evidence=["分歧后放量回流", "资金净流入转正"],
        source_type="p3.phase2.cycle",
        source_trace_id="",
        source_trace={},
        source_version="theme_cycle_judgement.v1",
        rule_version="theme_cycle_judgement.v1"
    )


async def test_detect_weak_to_strong_signals():
    """测试弱转强信号检测"""
    print("=== 测试弱转强信号检测 ===")

    service = WeakToStrongService()
    trade_date = date(2026, 4, 7)

    # 测试场景1：弱转强明确（action_bias包含"弱转强"）
    print("\n场景1: action_bias包含'弱转强'")
    cycle_judgement1 = create_mock_cycle_judgement_for_weak_to_strong()

    inputs1 = WeakToStrongDetectionInputs(
        cycle_judgement=cycle_judgement1,
        prev_day_data={
            "open": 10.40,
            "high": 10.80,
            "low": 10.30,
            "close": 10.20,  # 阴线
            "volume": 5000000,
            "pct_chg": -1.5
        },
        current_day_data={
            "open": 10.35,
            "high": 10.45,
            "low": 10.00,   # 跌到支撑位
            "close": 10.25,  # 小幅反弹
            "volume": 6000000,  # 放量
            "pct_chg": 0.5   # 微涨
        }
    )

    signals1 = await service.detect_weak_to_strong_signals(trade_date, inputs1)
    print(f"检测到 {len(signals1)} 个信号")

    for i, signal in enumerate(signals1):
        print(f"  信号 #{i+1}: {signal.signal_type} (强度: {signal.signal_strength:.1f})")

    # 测试场景2：分歧回流
    print("\n场景2: 分歧回流")
    cycle_judgement2 = create_mock_cycle_judgement_for_divergence_rebound()

    inputs2 = WeakToStrongDetectionInputs(
        cycle_judgement=cycle_judgement2,
        prev_day_data={
            "open": 10.40,
            "high": 10.80,
            "low": 10.30,
            "close": 10.20,
            "volume": 5000000,
            "pct_chg": -1.5
        },
        current_day_data={
            "open": 10.25,
            "high": 10.60,
            "low": 10.20,
            "close": 10.50,  # 反弹
            "volume": 8000000,  # 明显放量
            "pct_chg": 2.9    # 接近涨停
        }
    )

    signals2 = await service.detect_weak_to_strong_signals(trade_date, inputs2)
    print(f"检测到 {len(signals2)} 个信号")

    for i, signal in enumerate(signals2):
        print(f"  信号 #{i+1}: {signal.signal_type} (强度: {signal.signal_strength:.1f})")
        if hasattr(signal, 'is_divergence_rebound'):
            print(f"    是否分歧回流: {signal.is_divergence_rebound}")

    return signals1 + signals2


def test_support_analysis_with_better_data():
    """用更好的数据测试支撑位分析"""
    print("\n=== 测试支撑位分析（优化数据）===")

    service = WeakToStrongService()

    # 优化数据以更好地触发支撑检测
    # 前一日：大阴线
    prev_day_data = {
        "open": 10.50,
        "high": 10.60,
        "low": 10.00,   # 低点
        "close": 10.05, # 阴线，收盘接近低点
        "volume": 5000000,
        "pct_chg": -4.5  # 大幅下跌
    }

    # 当日：在支撑位附近反弹
    current_day_data = {
        "open": 10.00,   # 正好在前一日低点开盘
        "high": 10.30,
        "low": 9.98,     # 轻微跌破支撑位
        "close": 10.25,  # 反弹收阳
        "volume": 6000000,
        "pct_chg": 2.0   # 上涨
    }

    # 添加向上缺口场景
    print("\n场景A: 支撑位反弹（前一日低点）")
    analysis_a = service._analyze_support_and_gaps(prev_day_data, current_day_data)
    print(f"  是否有支撑位: {analysis_a.get('has_support', False)}")
    print(f"  支撑位类型: {analysis_a.get('support_type', '')}")
    print(f"  技术信号: {analysis_a.get('technical_signals', [])}")

    # 测试缺口支撑场景
    print("\n场景B: 缺口支撑")
    prev_day_data_b = {
        "open": 10.00,
        "high": 10.30,   # 高点
        "low": 9.80,
        "close": 10.10,
        "volume": 5000000,
        "pct_chg": 1.0
    }

    # 当日有向上缺口
    current_day_data_b = {
        "open": 10.35,   # 向上缺口：开盘高于前一日高点
        "high": 10.60,
        "low": 10.30,    # 低点正好在缺口下沿（前一日高点）
        "close": 10.50,
        "volume": 6000000,
        "pct_chg": 3.0
    }

    analysis_b = service._analyze_support_and_gaps(prev_day_data_b, current_day_data_b)
    print(f"  是否有缺口: {analysis_b.get('has_gap', False)}")
    print(f"  缺口类型: {analysis_b.get('gap_type', '')}")
    print(f"  是否缺口支撑: {analysis_b.get('is_gap_support', False)}")
    print(f"  技术信号: {analysis_b.get('technical_signals', [])}")

    return analysis_a, analysis_b


async def test_weak_to_strong_integration():
    """测试弱转强服务集成"""
    print("\n=== 测试弱转强服务集成 ===")

    service = WeakToStrongService()

    # 创建符合弱转强条件的完整数据
    trade_date = date(2026, 4, 7)

    cycle_judgement = ThemeCycleJudgement(
        trade_date="2026-04-07",
        subject_key="002361.SZ",  # 神剑股份
        theme_name="高端制造",
        is_main_theme=True,
        is_start=False,
        is_fermentation=False,
        is_divergence=True,
        is_rebound=True,
        is_climax=False,
        is_fade=False,
        primary_cycle_stage="rebound",
        limit_up_count=1,
        leader_status="潜在龙头",
        board_effect_status="回流",
        action_bias="弱转强",  # 关键！
        confidence=85.0,
        conclusion="前一日下跌到缺口位置，当日获得支撑反弹，形成弱转强",
        evidence=["前一日下跌-4.5%", "当日放量反弹+2.0%", "缺口支撑有效"],
        source_type="p3.phase2.cycle",
        source_trace_id="",
        source_trace={},
        source_version="theme_cycle_judgement.v1",
        rule_version="theme_cycle_judgement.v1"
    )

    inputs = WeakToStrongDetectionInputs(
        cycle_judgement=cycle_judgement,
        prev_day_data={
            "open": 10.50,
            "high": 10.60,
            "low": 10.00,
            "close": 10.05,
            "volume": 5000000,
            "pct_chg": -4.5
        },
        current_day_data={
            "open": 10.00,
            "high": 10.30,
            "low": 9.98,
            "close": 10.25,
            "volume": 6000000,
            "pct_chg": 2.0
        },
        market_environment={
            "mode": "cautious",
            "position_limit": 0.3
        }
    )

    # 检测信号
    signals = await service.detect_weak_to_strong_signals(trade_date, inputs)

    print(f"检测到 {len(signals)} 个弱转强信号")

    for signal in signals:
        print(f"\n信号详情:")
        print(f"  股票: {signal.stock_name} ({signal.stock_id})")
        print(f"  主题: {signal.theme_name}")
        print(f"  信号类型: {signal.signal_type}")
        print(f"  信号强度: {signal.signal_strength:.1f}/100")
        print(f"  置信度: {signal.confidence_score:.1f}/100")
        print(f"  是否支撑反弹: {signal.is_support_bounce}")
        print(f"  是否分歧回流: {signal.is_divergence_rebound}")
        if hasattr(signal, 'has_support') and signal.has_support:
            print(f"  支撑位类型: {signal.support_type}")
            print(f"  支撑位强度: {signal.support_strength:.2f}")
        print(f"  证据: {signal.evidence[:3]}")  # 显示前3个证据

    # 测试生成判断结果
    if signals:
        print("\n=== 测试生成弱转强判断结果 ===")
        market_state = {
            "mode": "cautious",
            "action_bias": "试错",
            "position_limit": 0.3,
            "market_health_score": 65.0
        }

        judgements = await service.generate_weak_to_strong_judgement(signals, market_state)
        print(f"生成 {len(judgements)} 个判断结果")

        for judgement in judgements:
            print(f"\n判断结果:")
            print(f"  弱转强评分: {judgement.weak_to_strong_score:.1f}/100")
            print(f"  操作建议: {judgement.action_bias}")
            print(f"  仓位建议: {judgement.position_suggestion:.0%}")
            print(f"  止损位: {judgement.stop_loss_level:.1f}%")
            print(f"  风险评估: {judgement.risk_assessment}")

    return signals


async def main():
    """主测试函数"""
    print("弱转强策略异步测试")
    print("=" * 60)
    print("测试目标: 验证弱转强服务核心功能")
    print("重点测试: 神剑股份（002361）的弱转强信号识别")
    print("=" * 60)

    # 测试支撑位分析
    analysis_a, analysis_b = test_support_analysis_with_better_data()

    # 测试信号检测
    signals = await test_detect_weak_to_strong_signals()

    # 测试完整集成
    all_signals = await test_weak_to_strong_integration()

    print("\n" + "=" * 60)
    print("测试总结:")

    # 分析结果
    has_support_a = analysis_a.get('has_support', False)
    has_gap_b = analysis_b.get('has_gap', False)
    has_gap_support = analysis_b.get('is_gap_support', False)

    print(f"1. 支撑位分析: {'✅' if has_support_a else '❌'}")
    print(f"2. 缺口分析: {'✅' if has_gap_b else '❌'}")
    print(f"3. 缺口支撑: {'✅' if has_gap_support else '❌'}")
    print(f"4. 弱转强信号检测: {len(signals) + len(all_signals)}个信号")

    # 检查神剑股份的特征
    print("\n神剑股份弱转强特征验证:")
    print("1. 前一日下跌到支撑位: ✅ (模拟数据-4.5%下跌到前一日低点)")
    print("2. 当日获得支撑反弹: ✅ (模拟数据+2.0%反弹)")
    print("3. 成交量配合: ✅ (模拟数据放量20%)")
    print("4. 周期阶段转换（分歧→回流）: ✅ (is_divergence=True, is_rebound=True)")
    print("5. 操作偏向提示弱转强: ✅ (action_bias='弱转强')")

    if any(s.signal_type == "支撑反弹" for s in all_signals):
        print("\n✅ 成功识别神剑股份的支撑反弹弱转强信号")
        print("   符合PDF文档中的'前一日下跌到短期支撑位'技术形态")
    else:
        print("\n⚠️ 未能识别支撑反弹信号")
        print("   可能需要进一步优化检测逻辑")


if __name__ == "__main__":
    asyncio.run(main())
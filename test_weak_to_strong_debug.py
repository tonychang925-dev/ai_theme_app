#!/usr/bin/env python3
"""
调试弱转强信号检测
"""

import sys
import os

# 添加stock_service到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_service import WeakToStrongService
from stock_service.models import ThemeCycleJudgement


def test_check_weak_to_strong_stage():
    """测试弱转强阶段检查逻辑"""
    print("=== 测试弱转强阶段检查 ===")

    service = WeakToStrongService()

    # 测试不同场景
    test_cases = [
        {
            "name": "action_bias包含'弱转强'",
            "data": ThemeCycleJudgement(
                trade_date="2026-04-07",
                subject_key="test",
                theme_name="test",
                is_main_theme=True,
                is_start=False,
                is_fermentation=False,
                is_divergence=False,
                is_rebound=False,
                is_climax=False,
                is_fade=False,
                primary_cycle_stage="start",
                limit_up_count=0,
                leader_status="",
                board_effect_status="",
                action_bias="弱转强",  # 关键
                confidence=75.0,
                conclusion="",
                evidence=[],
                source_type="p3.phase2.cycle",
                source_trace_id="",
                source_trace={},
                source_version="theme_cycle_judgement.v1",
                rule_version="theme_cycle_judgement.v1"
            )
        },
        {
            "name": "分歧后回流 (is_divergence=True, is_rebound=True)",
            "data": ThemeCycleJudgement(
                trade_date="2026-04-07",
                subject_key="test",
                theme_name="test",
                is_main_theme=True,
                is_start=False,
                is_fermentation=False,
                is_divergence=True,   # 分歧
                is_rebound=True,      # 回流
                is_climax=False,
                is_fade=False,
                primary_cycle_stage="rebound",
                limit_up_count=0,
                leader_status="",
                board_effect_status="",
                action_bias="分歧回流",
                confidence=75.0,
                conclusion="",
                evidence=[],
                source_type="p3.phase2.cycle",
                source_trace_id="",
                source_trace={},
                source_version="theme_cycle_judgement.v1",
                rule_version="theme_cycle_judgement.v1"
            )
        },
        {
            "name": "阶段从divergence转为rebound",
            "data": ThemeCycleJudgement(
                trade_date="2026-04-07",
                subject_key="test",
                theme_name="test",
                is_main_theme=True,
                is_start=False,
                is_fermentation=False,
                is_divergence=True,
                is_rebound=True,
                is_climax=False,
                is_fade=False,
                primary_cycle_stage="rebound",
                limit_up_count=0,
                leader_status="",
                board_effect_status="",
                action_bias="分歧后走强",
                confidence=75.0,
                conclusion="",
                evidence=[],
                source_type="p3.phase2.cycle",
                source_trace_id="",
                source_trace={},
                source_version="theme_cycle_judgement.v1",
                rule_version="theme_cycle_judgement.v1"
            )
        },
        {
            "name": "不符合条件 (只有分歧没有回流)",
            "data": ThemeCycleJudgement(
                trade_date="2026-04-07",
                subject_key="test",
                theme_name="test",
                is_main_theme=True,
                is_start=False,
                is_fermentation=False,
                is_divergence=True,   # 只有分歧
                is_rebound=False,     # 没有回流
                is_climax=False,
                is_fade=False,
                primary_cycle_stage="divergence",
                limit_up_count=0,
                leader_status="",
                board_effect_status="",
                action_bias="分歧",
                confidence=75.0,
                conclusion="",
                evidence=[],
                source_type="p3.phase2.cycle",
                source_trace_id="",
                source_trace={},
                source_version="theme_cycle_judgement.v1",
                rule_version="theme_cycle_judgement.v1"
            )
        }
    ]

    for i, test_case in enumerate(test_cases):
        result = service._check_weak_to_strong_stage(test_case["data"])
        print(f"测试 {i+1}: {test_case['name']}")
        print(f"  action_bias: {test_case['data'].action_bias}")
        print(f"  is_divergence: {test_case['data'].is_divergence}")
        print(f"  is_rebound: {test_case['data'].is_rebound}")
        print(f"  primary_cycle_stage: {test_case['data'].primary_cycle_stage}")
        print(f"  结果: {'✅ 弱转强' if result else '❌ 非弱转强'}")
        print()


def test_determine_signal_type():
    """测试信号类型确定逻辑"""
    print("\n=== 测试信号类型确定 ===")

    service = WeakToStrongService()

    # 需要mock一些数据
    class MockCycleJudgement:
        def __init__(self):
            self.is_divergence = True
            self.is_rebound = True
            self.action_bias = "弱转强"
            self.primary_cycle_stage = "rebound"

    cycle_judgement = MockCycleJudgement()

    # 这个方法可能是私有的，我们尝试调用
    try:
        signal_type = service._determine_signal_type(cycle_judgement, None)
        print(f"信号类型: {signal_type}")
    except Exception as e:
        print(f"无法测试_determine_signal_type: {e}")
        print("可能方法是私有的或需要更多参数")


def test_weak_to_strong_service_flow():
    """测试服务完整流程"""
    print("\n=== 测试完整流程 ===")

    service = WeakToStrongService()

    # 创建一个简单的周期判断
    cycle_judgement = ThemeCycleJudgement(
        trade_date="2026-04-07",
        subject_key="002361.SZ",
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
        action_bias="弱转强",
        confidence=85.0,
        conclusion="弱转强信号",
        evidence=["测试证据"],
        source_type="p3.phase2.cycle",
        source_trace_id="",
        source_trace={},
        source_version="theme_cycle_judgement.v1",
        rule_version="theme_cycle_judgement.v1"
    )

    # 测试阶段检查
    is_weak_to_strong = service._check_weak_to_strong_stage(cycle_judgement)
    print(f"阶段检查结果: {is_weak_to_strong}")

    # 检查ThemeCycleJudgement是否有stock_id属性
    print(f"\n检查ThemeCycleJudgement属性:")
    print(f"  hasattr 'stock_id': {hasattr(cycle_judgement, 'stock_id')}")
    print(f"  hasattr 'stock_name': {hasattr(cycle_judgement, 'stock_name')}")
    print(f"  subject_key: {cycle_judgement.subject_key}")

    # 查看detect_weak_to_strong_signals方法的可能问题
    print("\n可能的问题:")
    print("1. ThemeCycleJudgement没有stock_id属性")
    print("2. detect_weak_to_strong_signals中需要stock_id")
    print("3. _build_weak_to_strong_signal可能返回None")


def main():
    """主函数"""
    print("弱转强服务调试")
    print("=" * 50)

    test_check_weak_to_strong_stage()
    test_determine_signal_type()
    test_weak_to_strong_service_flow()

    print("\n" + "=" * 50)
    print("调试总结:")
    print("1. 检查_check_weak_to_strong_stage逻辑")
    print("2. 检查ThemeCycleJudgement是否包含必要字段")
    print("3. 查看detect_weak_to_strong_signals中的错误处理")


if __name__ == "__main__":
    main()
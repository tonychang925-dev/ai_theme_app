#!/usr/bin/env python3
"""
简化版弱转强策略测试
重点测试神剑股份（002361）在2026-04-07的弱转强信号
"""

import sys
import os
from datetime import date

# 添加stock_service到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongDetectionInputs
from stock_service.models import ThemeCycleJudgement


def create_mock_cycle_judgement():
    """创建模拟的周期判断数据"""
    return ThemeCycleJudgement(
        trade_date="2026-04-07",
        subject_key="高端制造",  # 假设主题
        theme_name="高端制造",
        is_main_theme=True,
        is_start=False,
        is_fermentation=False,
        is_divergence=True,      # 4/7处于分歧状态
        is_rebound=False,        # 尚未反弹（4/7）
        is_climax=False,
        is_fade=False,
        primary_cycle_stage="divergence",  # 分歧阶段
        limit_up_count=0,
        leader_status="",
        board_effect_status="分化",
        action_bias="分歧",      # 分歧阶段
        confidence=75.0,
        conclusion="股价下跌到缺口位置，面临支撑",
        evidence=["前一日下跌到缺口位置", "成交量放大"],
        source_type="p3.phase2.cycle",
        source_trace_id="",
        source_trace={},
        source_version="theme_cycle_judgement.v1",
        rule_version="theme_cycle_judgement.v1"
    )


def test_support_and_gap_analysis():
    """测试支撑位和缺口分析功能"""
    print("=== 测试支撑位和缺口分析 ===")

    service = WeakToStrongService()

    # 模拟神剑股份的K线数据
    # 4/6: 下跌
    prev_day_data = {
        "open": 10.40,
        "high": 10.80,
        "low": 10.30,
        "close": 10.20,  # 阴线
        "volume": 5000000,
        "pct_chg": -1.5
    }

    # 4/7: 继续下跌到缺口位置
    current_day_data = {
        "open": 10.35,
        "high": 10.45,
        "low": 10.00,   # 跌到缺口位置（假设缺口在10.10-10.30）
        "close": 10.20,  # 收在缺口上沿附近
        "volume": 6000000,  # 放量
        "pct_chg": 0.0   # 平盘
    }

    # 历史数据（用于计算移动平均线）
    historical_data = []
    # 生成20个交易日的数据
    base_price = 11.0
    for i in range(20):
        day_data = {
            "open": base_price - i*0.05,
            "high": base_price - i*0.03,
            "low": base_price - i*0.07,
            "close": base_price - i*0.05,
            "volume": 4000000 + i*100000
        }
        historical_data.append(day_data)

    # 调用分析方法
    analysis = service._analyze_support_and_gaps(prev_day_data, current_day_data, historical_data)

    print("技术分析结果:")
    print(f"  是否有支撑位: {analysis.get('has_support', False)}")
    if analysis.get('has_support'):
        print(f"  支撑位类型: {analysis.get('support_type', '')}")
        print(f"  支撑位强度: {analysis.get('support_strength', 0):.2f}")
        print(f"  支撑位价格: {analysis.get('support_level', 0):.2f}")

    print(f"  是否有缺口: {analysis.get('has_gap', False)}")
    if analysis.get('has_gap'):
        print(f"  缺口类型: {analysis.get('gap_type', '')}")
        print(f"  缺口大小: {analysis.get('gap_size', 0):.2f}%")

    print(f"  技术信号: {analysis.get('technical_signals', [])}")

    # 验证是否检测到支撑位
    if analysis.get('has_support'):
        print("✅ 成功检测到支撑位")
    else:
        print("⚠️ 未检测到支撑位，可能参数需要调整")

    return analysis


def test_weak_to_strong_detection():
    """测试弱转强信号检测"""
    print("\n=== 测试弱转强信号检测 ===")

    service = WeakToStrongService()
    trade_date = date(2026, 4, 7)

    # 创建模拟数据
    cycle_judgement = create_mock_cycle_judgement()

    # 创建检测输入
    inputs = WeakToStrongDetectionInputs(
        cycle_judgement=cycle_judgement,
        prev_day_data={
            "open": 10.40,
            "high": 10.80,
            "low": 10.30,
            "close": 10.20,
            "volume": 5000000,
            "pct_chg": -1.5
        },
        current_day_data={
            "open": 10.35,
            "high": 10.45,
            "low": 10.00,
            "close": 10.20,
            "volume": 6000000,
            "pct_chg": 0.0
        }
    )

    # 检测信号
    signals = service.detect_weak_to_strong_signals(trade_date, inputs)

    print(f"检测到 {len(signals)} 个弱转强信号")

    for i, signal in enumerate(signals):
        print(f"\n信号 #{i+1}:")
        print(f"  信号类型: {signal.signal_type}")
        print(f"  信号强度: {signal.signal_strength:.1f}")
        print(f"  置信度: {signal.confidence_score:.1f}")
        print(f"  是否分歧回流: {signal.is_divergence_rebound}")
        print(f"  是否支撑反弹: {signal.is_support_bounce}")
        if hasattr(signal, 'has_support') and signal.has_support:
            print(f"  支撑位类型: {signal.support_type}")
            print(f"  支撑位强度: {signal.support_strength:.2f}")
        print(f"  证据: {signal.evidence}")

    # 验证是否检测到关键信号
    has_support_signal = any(s.signal_type == "支撑反弹" for s in signals)
    has_divergence_signal = any(s.signal_type == "分歧回流" for s in signals)

    print(f"\n信号验证:")
    print(f"  支撑反弹信号: {'✅' if has_support_signal else '❌'}")
    print(f"  分歧回流信号: {'✅' if has_divergence_signal else '❌'}")

    if has_support_signal:
        print("\n✅ 成功检测到神剑股份的支撑反弹弱转强信号")
        print("   符合用户描述的'前一日下跌到短期支撑位（缺口位置）'特征")
    else:
        print("\n⚠️ 未检测到预期的支撑反弹信号")
        print("   可能需要调整检测参数或模拟数据")

    return signals


def test_ta_lib_availability():
    """测试TA-Lib库是否可用"""
    print("\n=== 测试TA-Lib库 ===")

    # 重新导入服务以检查TA_LIB_AVAILABLE
    from stock_service.services.weak_to_strong_service import TA_LIB_AVAILABLE

    if TA_LIB_AVAILABLE:
        print("✅ TA-Lib库已安装并可用")
        print("   可以进行高级技术分析（移动平均线、MACD等）")
        return True
    else:
        print("⚠️ TA-Lib库未安装或不可用")
        print("   支撑位分析将使用简化算法")
        print("   建议安装: pip install TA-Lib")
        return False


def main():
    """主测试函数"""
    print("弱转强策略简化测试")
    print("=" * 60)
    print("测试目标: 神剑股份（002361）在2026-04-07的弱转强信号")
    print("用户描述: 4/7下跌到缺口位置，4/8强势涨停")
    print("=" * 60)

    # 测试TA-Lib可用性
    ta_lib_available = test_ta_lib_availability()

    # 测试支撑位和缺口分析
    analysis_result = test_support_and_gap_analysis()

    # 测试弱转强信号检测
    signals = test_weak_to_strong_detection()

    print("\n" + "=" * 60)
    print("测试总结:")
    print(f"1. TA-Lib库: {'可用' if ta_lib_available else '不可用'}")
    print(f"2. 支撑位分析: {'成功' if analysis_result.get('has_support', False) else '未检测到'}")
    print(f"3. 弱转强信号: {len(signals)}个")

    if signals:
        signal_types = [s.signal_type for s in signals]
        print(f"   信号类型: {signal_types}")

    # 检查是否符合PDF中的弱转强特征
    print("\nPDF弱转强买入法特征验证:")
    print("1. 前一日下跌: ✅ (模拟数据中4/6下跌-1.5%)")
    print("2. 到达支撑位: ✅ (模拟数据中低点10.00在缺口支撑附近)")
    print("3. 成交量配合: ✅ (模拟数据中成交量放大20%)")
    print("4. 周期阶段转换: ⚠️ (需要实际数据验证分歧→反弹转换)")

    if any(s.signal_type == "支撑反弹" for s in signals):
        print("\n✅ 成功识别神剑股份的弱转强信号特征")
        print("   符合'前一日下跌到短期支撑位（缺口位置）'的技术形态")
    else:
        print("\n⚠️ 未能完全识别弱转强信号")
        print("   可能需要更精确的模拟数据或实际数据测试")


if __name__ == "__main__":
    main()
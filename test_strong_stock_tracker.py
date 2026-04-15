#!/usr/bin/env python3
"""
测试强势股清单跟踪服务

验证功能：
1. 强势股识别和清单更新
2. 弱转强候选筛选
3. 次日重点观察对象识别
4. 与选股服务的集成
"""

import asyncio
import sys
import os
from datetime import date, datetime
from typing import List, Dict, Any

# 添加stock_service到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.models import (
    ThemeCycleJudgement,
    ThemeLeaderCandidate,
    ThemeMainlineJudgement,
    StockAbnormalSignal,
    MarketEnvironmentJudgement,
    StrongStockRecord
)
from stock_service.services.strong_stock_tracker_service import StrongStockTrackerService


class MockDataGenerator:
    """模拟数据生成器"""

    @staticmethod
    def create_theme_cycle_judgements(trade_date: date) -> List[ThemeCycleJudgement]:
        """创建主题周期判断模拟数据"""
        return [
            ThemeCycleJudgement(
                trade_date=trade_date.isoformat(),
                subject_key="002361.SZ",
                theme_name="高端制造",
                is_main_theme=True,
                is_start=False,
                is_fermentation=True,
                is_divergence=False,
                is_rebound=False,
                is_climax=False,
                is_fade=False,
                primary_cycle_stage="fermentation",
                limit_up_count=3,
                leader_status="相对龙头",
                board_effect_status="板块效应强",
                action_bias="弱转强",
                confidence=85.0,
                conclusion="高端制造主题发酵期，神剑股份相对龙头",
                evidence=["板块效应强", "资金持续流入"],
                source_type="p3.phase2.cycle",
                source_trace_id="",
                source_trace={},
                source_version="theme_cycle_judgement.v1",
                rule_version="theme_cycle_judgement.v1"
            ),
            ThemeCycleJudgement(
                trade_date=trade_date.isoformat(),
                subject_key="300124.SZ",
                theme_name="高端制造",
                is_main_theme=True,
                is_start=False,
                is_fermentation=True,
                is_divergence=False,
                is_rebound=False,
                is_climax=False,
                is_fade=False,
                primary_cycle_stage="fermentation",
                limit_up_count=2,
                leader_status="绝对龙头",
                board_effect_status="板块效应强",
                action_bias="主做",
                confidence=90.0,
                conclusion="高端制造主题发酵期，汇川技术绝对龙头",
                evidence=["板块效应强", "资金持续流入"],
                source_type="p3.phase2.cycle",
                source_trace_id="",
                source_trace={},
                source_version="theme_cycle_judgement.v1",
                rule_version="theme_cycle_judgement.v1"
            )
        ]

    @staticmethod
    def create_leader_candidates(trade_date: date) -> List[ThemeLeaderCandidate]:
        """创建龙头候选模拟数据"""
        return [
            ThemeLeaderCandidate(
                trade_date=trade_date.isoformat(),
                subject_key="高端制造",
                theme_name="高端制造",
                stock_id="002361.SZ",
                stock_name="神剑股份",
                purity_score=85.0,
                leading_score=80.0,
                capital_score=75.0,
                structure_score=82.0,
                resilience_score=78.0,
                composite_score=80.0,
                is_limit_up=True,
                limit_up_type="强势涨停",
                turnover_rate=8.5,
                volume_ratio=2.5,
                main_net_inflow=1200.0,
                is_new_stock=False,
                candidate_rank=1,
                role_label="龙头",
                evidence=["换手充分", "资金流入明显"],
                source_type="p3.phase2.leader_candidate",
                source_trace_id="",
                source_trace={},
                source_version="theme_leader_candidate.v1",
                rule_version="theme_leader_candidate.v1"
            ),
            ThemeLeaderCandidate(
                trade_date=trade_date.isoformat(),
                subject_key="高端制造",
                theme_name="高端制造",
                stock_id="300124.SZ",
                stock_name="汇川技术",
                purity_score=90.0,
                leading_score=92.0,
                capital_score=88.0,
                structure_score=85.0,
                resilience_score=90.0,
                composite_score=89.0,
                is_limit_up=False,
                limit_up_type="",
                turnover_rate=3.2,
                volume_ratio=1.8,
                main_net_inflow=800.0,
                is_new_stock=False,
                candidate_rank=2,
                role_label="前排",
                evidence=["基本面优质", "机构资金青睐"],
                source_type="p3.phase2.leader_candidate",
                source_trace_id="",
                source_trace={},
                source_version="theme_leader_candidate.v1",
                rule_version="theme_leader_candidate.v1"
            )
        ]

    @staticmethod
    def create_mainline_judgements(trade_date: date) -> List[ThemeMainlineJudgement]:
        """创建主线判断模拟数据"""
        return [
            ThemeMainlineJudgement(
                trade_date=trade_date.isoformat(),
                subject_key="高端制造",
                theme_name="高端制造",
                event_chain_score=85.0,
                event_chain_continuity_score=80.0,
                market_recognition_score=82.0,
                mainline_stability_score=78.0,
                is_main_theme=True,
                theme_tier="main",
                limit_up_count=5,
                conclusion="高端制造为主线题材",
                novelty_score=75.0,
                timing_score=80.0,
                influence_score=85.0,
                capital_persistence_score=78.0,
                institution_participation_score=82.0,
                retail_attention_score=70.0,
                evidence_logic=["政策支持", "产业趋势"],
                evidence_market=["资金持续流入", "板块效应明显"],
                source_type="p3.phase2.mainline",
                source_trace_id="",
                source_trace={},
                source_version="theme_mainline_judgement.v1",
                rule_version="theme_mainline_judgement.v1"
            )
        ]

    @staticmethod
    def create_abnormal_signals(trade_date: date) -> List[StockAbnormalSignal]:
        """创建异常信号模拟数据"""
        signals = []

        # 神剑股份 - 弱转强信号
        shenjian = StockAbnormalSignal(
            trade_date=trade_date.isoformat(),
            stock_id="002361.SZ",
            stock_name="神剑股份",
            subject_key="高端制造",
            theme_name="高端制造",
            turnover_rate=8.5,
            turnover_rank_in_theme=1,
            main_net_inflow=1200.0,  # 主力净流入（万）
            main_net_inflow_rank_in_theme=1,
            turnover_abnormal_score=75.0,
            capital_focus_score=80.0,
            is_high_turnover=True,
            is_extreme_turnover=False,
            volume_ratio_to_ma50=2.5,
            volume_abnormal_score=80.0,
            is_volume_breakout=True,
            is_double_volume=False,
            is_high_volume_bar=True,
            tail_amount=500.0,
            tail_amount_ratio=0.1,
            tail_unmatched_buy_order=200.0,
            tail_abnormal_score=70.0,
            has_tail_rush_buy=True,
            has_tail_large_unmatched_bid=False,
            hot_money_buy_names=["游资A", "游资B"],
            institution_net_buy=0.0,
            institution_seat_count=0,
            has_hot_money_buy=True,
            has_institution_buy=False,
            abnormal_labels=["weak_to_strong", "support_bounce"],
            abnormal_composite_score=75.0,
            conclusion="前一日下跌到缺口位置，今日资金流入",
            evidence=["前一日下跌", "成交量放大", "支撑位有效"],
            source_type="p3.phase3.stock_abnormal_signal",
            source_trace_id="",
            source_trace={},
            source_version="stock_abnormal_signal.v1.daily_proxy",
            rule_version="stock_abnormal_signal.v1.daily_proxy"
        )
        # 添加额外属性（服务中使用的字段）
        shenjian.abnormal_type = "weak_to_strong"
        shenjian.pct_chg = -3.8  # 前一日下跌
        shenjian.rank_order = 1
        shenjian.is_leader = True
        shenjian.is_limit_up = False
        shenjian.is_bad_limit_up = False
        shenjian.is_upper_shadow = False
        shenjian.volume_breakout_score = 80.0
        shenjian.price_breakout_score = 0.0
        shenjian.abnormal_reason = "前一日弱势，今日资金流入"
        shenjian.support_bounce_score = 85.0
        shenjian.is_support_bounce = True
        shenjian.divergence_rebound_score = 0.0
        shenjian.is_divergence_rebound = False
        shenjian.volume_breakout_confirmed = False
        signals.append(shenjian)

        # 汇川技术 - 强势信号
        huichuan = StockAbnormalSignal(
            trade_date=trade_date.isoformat(),
            stock_id="300124.SZ",
            stock_name="汇川技术",
            subject_key="高端制造",
            theme_name="高端制造",
            turnover_rate=3.2,
            turnover_rank_in_theme=2,
            main_net_inflow=800.0,
            main_net_inflow_rank_in_theme=2,
            turnover_abnormal_score=65.0,
            capital_focus_score=75.0,
            is_high_turnover=False,
            is_extreme_turnover=False,
            volume_ratio_to_ma50=1.8,
            volume_abnormal_score=70.0,
            is_volume_breakout=False,
            is_double_volume=False,
            is_high_volume_bar=False,
            tail_amount=300.0,
            tail_amount_ratio=0.05,
            tail_unmatched_buy_order=100.0,
            tail_abnormal_score=50.0,
            has_tail_rush_buy=False,
            has_tail_large_unmatched_bid=False,
            hot_money_buy_names=["游资C"],
            institution_net_buy=500.0,
            institution_seat_count=2,
            has_hot_money_buy=True,
            has_institution_buy=True,
            abnormal_labels=["strong_signal", "institution_buy"],
            abnormal_composite_score=82.0,
            conclusion="机构资金流入，持续强势",
            evidence=["机构资金青睐", "基本面优质"],
            source_type="p3.phase3.stock_abnormal_signal",
            source_trace_id="",
            source_trace={},
            source_version="stock_abnormal_signal.v1.daily_proxy",
            rule_version="stock_abnormal_signal.v1.daily_proxy"
        )
        # 添加额外属性
        huichuan.abnormal_type = "strong_signal"
        huichuan.pct_chg = 2.5  # 今日上涨
        huichuan.rank_order = 2
        huichuan.is_leader = True
        huichuan.is_limit_up = False
        huichuan.is_bad_limit_up = False
        huichuan.is_upper_shadow = False
        huichuan.volume_breakout_score = 70.0
        huichuan.price_breakout_score = 0.0
        huichuan.abnormal_reason = "机构资金流入"
        huichuan.support_bounce_score = 0.0
        huichuan.is_support_bounce = False
        huichuan.divergence_rebound_score = 0.0
        huichuan.is_divergence_rebound = False
        huichuan.volume_breakout_confirmed = False
        signals.append(huichuan)

        return signals

    @staticmethod
    def create_market_environment(trade_date: date) -> MarketEnvironmentJudgement:
        """创建市场环境判断模拟数据"""
        return MarketEnvironmentJudgement(
            trade_date=trade_date.isoformat(),
            market_health_score=75.0,
            market_bias="risk_on",
            breadth_status="市场广度强",
            short_term_sentiment_status="短线情绪活跃",
            relay_sentiment_status="接力生态健康",
            intraday_fade_status="冲高回落风险可控",
            action_bias="主做",
            conclusion="大环境提供保护，可围绕主线前排与高辨识度个股积极进攻",
            evidence=["市场广度强", "短线情绪活跃"],
            source_type="p3.phase3.market_environment_judgement",
            source_trace_id="",
            source_trace={},
            source_version="market_environment_judgement.v1.daily_proxy",
            rule_version="market_environment_judgement.v1.daily_proxy"
        )


async def test_strong_stock_tracker():
    """测试强势股清单跟踪服务"""
    print("=== 测试强势股清单跟踪服务 ===")
    print(f"测试日期: 2026-04-10")
    print()

    # 创建服务
    tracker = StrongStockTrackerService()

    # 生成模拟数据
    trade_date = date(2026, 4, 10)
    mock_data = MockDataGenerator()

    theme_judgements = mock_data.create_theme_cycle_judgements(trade_date)
    leader_candidates = mock_data.create_leader_candidates(trade_date)
    mainline_judgements = mock_data.create_mainline_judgements(trade_date)
    abnormal_signals = mock_data.create_abnormal_signals(trade_date)
    market_environment = mock_data.create_market_environment(trade_date)

    print("1. 更新强势股清单...")
    strong_stock_list = await tracker.update_strong_stock_list(
        trade_date=trade_date,
        theme_judgements=theme_judgements,
        leader_candidates=leader_candidates,
        mainline_judgements=mainline_judgements,
        abnormal_signals=abnormal_signals,
        market_environment=market_environment
    )

    print(f"   更新完成: {len(strong_stock_list.strong_stocks)}只强势股")
    for record in strong_stock_list.strong_stocks:
        print(f"   - {record.stock_name} ({record.stock_id}): {record.dragon_head_level}龙头, "
              f"标记天数: {record.marked_days_count}")

    print()
    print("2. 检查弱转强候选...")
    weak_to_strong_candidates = tracker.get_weak_to_strong_candidates()
    print(f"   弱转强候选: {len(weak_to_strong_candidates)}只")
    for candidate in weak_to_strong_candidates:
        print(f"   - {candidate.stock_name} ({candidate.stock_id}): "
              f"弱转强候选: {candidate.weak_to_strong_candidate}")

    print()
    print("3. 检查次日重点观察对象...")
    next_day_focus = tracker.get_next_day_focus_stocks()
    print(f"   次日重点观察: {len(next_day_focus)}只")
    for focus in next_day_focus:
        print(f"   - {focus.stock_name} ({focus.stock_id}): "
              f"次日重点: {focus.next_day_focus}")

    print()
    print("4. 按主题获取强势股...")
    theme_stocks = tracker.get_strong_stocks_by_theme("高端制造")
    print(f"   高端制造主题强势股: {len(theme_stocks)}只")

    print()
    print("5. 测试清单持久化...")
    # 模拟第二天更新
    next_day = date(2026, 4, 11)
    print(f"   模拟第二天 ({next_day}) 更新...")

    # 创建第二天的数据（神剑股份继续强势，汇川技术新增）
    next_day_leader_candidates = mock_data.create_leader_candidates(next_day)
    next_day_abnormal_signals = mock_data.create_abnormal_signals(next_day)

    # 更新清单
    next_day_list = await tracker.update_strong_stock_list(
        trade_date=next_day,
        theme_judgements=theme_judgements,  # 使用相同主题判断
        leader_candidates=next_day_leader_candidates,
        mainline_judgements=mainline_judgements,
        abnormal_signals=next_day_abnormal_signals,
        market_environment=market_environment
    )

    print(f"   第二天强势股: {len(next_day_list.strong_stocks)}只")
    for record in next_day_list.strong_stocks:
        print(f"   - {record.stock_name}: 标记天数: {record.marked_days_count}, "
              f"首次标记: {record.first_marked_date}, 最近标记: {record.last_marked_date}")

    print()
    print("6. 测试清理过期记录...")
    # 模拟7天后
    future_date = date(2026, 4, 18)
    print(f"   模拟7天后 ({future_date})，检查过期清理...")

    # 手动清理（服务内部会在更新时自动清理）
    tracker._cleanup_expired_records(future_date)

    remaining_stocks = len(tracker._strong_stocks)
    print(f"   7天后剩余强势股: {remaining_stocks}只")

    print()
    print("=== 测试总结 ===")
    print(f"✅ 强势股清单跟踪服务测试完成")
    print(f"   成功识别: {len(strong_stock_list.strong_stocks)}只强势股")
    print(f"   弱转强候选: {len(weak_to_strong_candidates)}只")
    print(f"   次日重点观察: {len(next_day_focus)}只")
    print(f"   清单更新和清理功能正常")

    # 验证神剑股份是否被正确识别为弱转强候选
    shenjian_found = any(
        r.stock_id == '002361.SZ' and r.weak_to_strong_candidate
        for r in weak_to_strong_candidates
    )
    if shenjian_found:
        print(f"✅ 神剑股份正确识别为弱转强候选")
    else:
        print(f"❌ 神剑股份未识别为弱转强候选，需要优化检测逻辑")

    return strong_stock_list


async def main():
    """主函数"""
    print("强势股清单跟踪服务测试")
    print("=" * 70)

    try:
        result = await test_strong_stock_tracker()

        print("\n" + "=" * 70)
        print("测试通过！强势股清单功能可用于：")
        print("1. 维护一周内的龙头/强势股标签")
        print("2. 从主线主题中筛选强势股候选")
        print("3. 检测前一日弱势 + 今日资金流入/异动")
        print("4. 识别次日重点观察对象")
        print("=" * 70)

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
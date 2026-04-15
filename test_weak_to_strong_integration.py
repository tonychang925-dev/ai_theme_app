#!/usr/bin/env python3
"""
弱转强策略集成测试
测试神剑股份（002361）在2026-04-07的弱转强识别
"""

import asyncio
import sys
import os
from datetime import date
from unittest.mock import Mock, AsyncMock

# 添加stock_service到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.stock_screener_service import StockScreenerService, ScreeningConfig
from stock_service.stock_screener_models import ScreeningStrategy, DEFAULT_STRATEGIES
from stock_service.services.weak_to_strong_service import WeakToStrongService, WeakToStrongSignal


class MockScreenerRepository:
    """模拟选股器仓库"""

    def __init__(self):
        self.strategies = {
            "weak_to_strong": next(s for s in DEFAULT_STRATEGIES if s.strategy_id == "weak_to_strong")
        }
        self.pool = None
        self.executions = {}
        self.results = {}

    async def _ensure_pool(self):
        """模拟连接池"""
        if self.pool is None:
            # 模拟连接池
            class MockPool:
                async def acquire(self):
                    class MockConnection:
                        async def __aenter__(self):
                            return self
                        async def __aexit__(self, exc_type, exc_val, exc_tb):
                            pass
                        async def fetch(self, sql, *params):
                            # 模拟查询结果
                            return [
                                {"stock_id": "002361", "stock_name": "神剑股份"},
                                {"stock_id": "000001", "stock_name": "平安银行"}
                            ]
                    return MockConnection()
            self.pool = MockPool()
        return self.pool

    async def get_strategy(self, strategy_id):
        return self.strategies.get(strategy_id)

    async def get_stocks_for_screening(self, trade_date):
        # 返回模拟股票列表，包括神剑股份
        return [
            {
                "stock_id": "002361",
                "stock_name": "神剑股份",
                "trade_date": trade_date.isoformat()
            },
            {
                "stock_id": "000001",
                "stock_name": "平安银行",
                "trade_date": trade_date.isoformat()
            }
        ]

    async def create_execution(self, execution):
        self.executions[execution.execution_id] = execution
        return execution

    async def save_execution(self, execution):
        return execution

    async def save_results(self, results, execution_id=None):
        self.results[execution_id] = results
        return results

    async def update_execution(self, execution_id, **kwargs):
        if execution_id in self.executions:
            execution = self.executions[execution_id]
            for key, value in kwargs.items():
                setattr(execution, key, value)
            return True
        return False

    async def get_result(self, result_id):
        # 简单实现
        return None


def create_mock_weak_to_strong_service():
    """创建模拟的弱转强服务"""
    mock_service = Mock(spec=WeakToStrongService)

    # 模拟检测信号方法
    async def mock_detect_signals(trade_date, inputs):
        # 只对神剑股份返回弱转强信号
        stock_id = inputs.cycle_judgement.subject_key if hasattr(inputs.cycle_judgement, 'subject_key') else ""

        if "002361" in stock_id:
            # 返回模拟的弱转强信号
            signal = WeakToStrongSignal(
                trade_date=trade_date.isoformat(),
                stock_id="002361.SZ",
                stock_name="神剑股份",
                subject_key="高端制造",
                theme_name="高端制造",
                signal_type="支撑反弹",
                signal_strength=85.0,
                confidence_score=80.0,
                prev_stage="divergence",
                current_stage="rebound",
                action_bias="弱转强",
                volume_ratio=1.5,
                turnover_rate=8.5,
                pct_chg=2.0,
                main_net_inflow=5000000,
                is_limit_up=False,
                is_divergence_rebound=True,
                is_support_bounce=True,
                is_volume_breakout=True,
                has_capital_inflow=True,
                is_dragon_head=True,
                dragon_head_level="relative",
                has_plate_support=True,
                plate_support_strength=0.7,
                weak_type="big_negative_line",
                weak_intensity=0.6,
                intraday_pattern="early",
                bid_weak_to_strong=False,
                early_weak_to_strong=True,
                intraday_weak_to_strong=False,
                is_engulfing=True,
                engulfing_strength=0.8,
                previous_close_pct=-4.5,
                has_support=True,
                support_type="gap",
                support_strength=0.9,
                support_level=10.00,
                is_gap_support=True,
                evidence=["前一日下跌到缺口位置", "当日放量反弹", "缺口支撑有效"],
                conclusion="典型的弱转强信号，符合买入条件",
                risk_level="medium",
                source_type="p3.phase3.weak_to_strong_signal",
                source_trace_id="",
                source_trace={},
                source_version="weak_to_strong_signal.v1",
                rule_version="weak_to_strong_signal.v1"
            )
            return [signal]
        else:
            # 其他股票返回空列表
            return []

    mock_service.detect_weak_to_strong_signals = mock_detect_signals
    return mock_service


def create_mock_db_data_for_stock(stock_id):
    """为特定股票创建模拟数据库数据"""
    if stock_id == "002361":
        # 神剑股份：弱转强数据
        return {
            "theme_info": {
                "subject_key": "高端制造",
                "theme_name": "高端制造",
                "amount": 150000000,
                "limit_up": False,
                "is_leader": True,
                "rank_order": 1,
                "pct_chg": 2.0
            },
            "mainline_data": {
                "event_chain_score": 28.5,
                "market_recognition_score": 25.8,
                "mainline_stability_score": 15.6,
                "limit_up_count": 8,
                "theme_tier": "main",
                "novelty_score": 22.5,
                "timing_score": 18.3,
                "influence_score": 20.1,
                "capital_persistence_score": 10.5,
                "institution_participation_score": 6.8,
                "retail_attention_score": 7.2
            },
            "cycle_data": {
                "primary_cycle_stage": "rebound",
                "confidence": 85.0,
                "action_bias": "弱转强",
                "is_divergence": True,
                "is_rebound": True,
                "is_fermentation": False,
                "is_start": False,
                "is_climax": False,
                "is_fade": False,
                "limit_up_count": 1,
                "leader_status": "潜在龙头",
                "board_effect_status": "回流",
                "is_main_theme": True
            },
            "leader_data": {
                "candidate_rank": 1,
                "composite_score": 85.0,
                "role_label": "龙头候选"
            },
            "technical_data": {
                "turnover_rate": 8.5,
                "volume_ratio": 1.5,
                "pct_chg": 2.0,
                "current_flag": 3,
                "trend_strength_score": 25.0,
                "pattern_labels": "支撑反弹"
            }
        }
    else:
        # 其他股票：普通数据
        return {
            "theme_info": {
                "subject_key": "金融",
                "theme_name": "金融",
                "amount": 100000000,
                "limit_up": False,
                "is_leader": False,
                "rank_order": 5,
                "pct_chg": 0.5
            },
            "mainline_data": {
                "event_chain_score": 20.0,
                "market_recognition_score": 18.0,
                "mainline_stability_score": 12.0,
                "limit_up_count": 3,
                "theme_tier": "secondary",
                "novelty_score": 15.0,
                "timing_score": 12.0,
                "influence_score": 16.0,
                "capital_persistence_score": 8.0,
                "institution_participation_score": 5.0,
                "retail_attention_score": 4.0
            },
            "cycle_data": {
                "primary_cycle_stage": "fermentation",
                "confidence": 70.0,
                "action_bias": "跟随",
                "is_divergence": False,
                "is_rebound": False,
                "is_fermentation": True,
                "is_start": False,
                "is_climax": False,
                "is_fade": False,
                "limit_up_count": 2,
                "leader_status": "",
                "board_effect_status": "一般",
                "is_main_theme": True
            },
            "leader_data": {
                "candidate_rank": 3,
                "composite_score": 65.0,
                "role_label": "跟风"
            },
            "technical_data": {
                "turnover_rate": 3.5,
                "volume_ratio": 0.8,
                "pct_chg": 0.5,
                "current_flag": 1,
                "trend_strength_score": 15.0,
                "pattern_labels": ""
            }
        }


async def test_weak_to_strong_strategy():
    """测试弱转强策略"""
    print("=== 测试弱转强选股策略 ===")

    # 创建模拟仓库
    mock_repo = MockScreenerRepository()

    # 创建模拟弱转强服务
    mock_weak_to_strong_service = create_mock_weak_to_strong_service()

    # 创建选股器服务
    screener_service = StockScreenerService(
        screener_repo=mock_repo,
        weak_to_strong_service=mock_weak_to_strong_service
    )

    # 模拟数据加载
    original_load_data = screener_service._load_stock_data
    async def mock_load_data(context):
        # 模拟数据加载
        stock_id = context.stock_id
        mock_data = create_mock_db_data_for_stock(stock_id)

        context.theme_info = mock_data["theme_info"]
        context.mainline_data = mock_data["mainline_data"]
        context.cycle_data = mock_data["cycle_data"]
        context.leader_data = mock_data["leader_data"]
        context.technical_data = mock_data["technical_data"]

    screener_service._load_stock_data = mock_load_data

    # 测试配置
    trade_date = date(2026, 4, 7)
    config = ScreeningConfig(
        strategy_id="weak_to_strong",
        trade_date=trade_date,
        min_composite_score=65,
        limit=10,
        weak_to_strong_required=True,  # 关键：要求弱转强信号
        only_main_theme=True
    )

    print(f"测试日期: {trade_date}")
    print(f"策略: {config.strategy_id}")
    print(f"要求弱转强信号: {config.weak_to_strong_required}")
    print()

    # 执行选股
    results = await screener_service.execute_screening(config)

    print(f"选股结果数量: {len(results)}")
    print()

    # 分析结果
    shenjian_results = [r for r in results if "002361" in r.stock_id]
    other_results = [r for r in results if "002361" not in r.stock_id]

    print(f"神剑股份结果: {len(shenjian_results)}个")
    print(f"其他股票结果: {len(other_results)}个")
    print()

    # 打印神剑股份的详细结果
    if shenjian_results:
        result = shenjian_results[0]
        print("神剑股份选股结果:")
        print(f"  股票: {result.stock_name} ({result.stock_id})")
        print(f"  综合得分: {result.composite_score:.1f}")
        print(f"  周期维度得分: {result.dimension_scores.cycle:.1f}")
        print(f"  筛选理由: {result.screening_reason}")
        print()

        # 验证弱转强策略
        if result.composite_score >= config.min_composite_score:
            print("✅ 神剑股份通过弱转强策略筛选")
            print("   符合'前一日下跌到缺口位置，4/8强势涨停'的弱转强案例")
        else:
            print("❌ 神剑股份未通过弱转强策略筛选")
            print(f"   综合得分{result.composite_score:.1f}低于阈值{config.min_composite_score}")

    # 验证弱转强策略是否正确过滤其他股票
    print("\n弱转强策略验证:")
    if len(other_results) == 0:
        print("✅ 弱转强策略正确过滤了无弱转强信号的股票")
    else:
        print(f"⚠️  弱转强策略未能正确过滤所有无弱转强信号的股票")
        print(f"   仍有{len(other_results)}个非弱转强股票通过筛选")

    # 测试非弱转强策略（作为对比）
    print("\n" + "="*60)
    print("对比测试: 使用普通策略（不要求弱转强信号）")

    config_no_requirement = ScreeningConfig(
        strategy_id="default_composite",
        trade_date=trade_date,
        min_composite_score=65,
        limit=10,
        weak_to_strong_required=False,  # 不要求弱转强信号
        only_main_theme=True
    )

    # 临时修改弱转强服务，对平安银行也返回信号
    original_detect = mock_weak_to_strong_service.detect_weak_to_strong_signals
    async def mock_detect_all_signals(trade_date, inputs):
        # 对所有股票都返回信号（用于对比测试）
        stock_id = inputs.cycle_judgement.subject_key if hasattr(inputs.cycle_judgement, 'subject_key') else ""

        if "002361" in stock_id or "000001" in stock_id:
            signal = WeakToStrongSignal(
                trade_date=trade_date.isoformat(),
                stock_id="MOCK.SZ",
                stock_name="模拟股票",
                subject_key="mock",
                theme_name="模拟主题",
                signal_type="支撑反弹",
                signal_strength=70.0,
                confidence_score=65.0,
                prev_stage="divergence",
                current_stage="rebound",
                action_bias="弱转强",
                volume_ratio=1.2,
                turnover_rate=6.5,
                pct_chg=1.5,
                main_net_inflow=3000000,
                is_limit_up=False,
                is_divergence_rebound=True,
                is_support_bounce=True,
                is_volume_breakout=True,
                has_capital_inflow=True,
                evidence=["模拟信号"],
                conclusion="模拟弱转强信号",
                risk_level="medium"
            )
            return [signal]
        return []

    mock_weak_to_strong_service.detect_weak_to_strong_signals = mock_detect_all_signals

    results_all = await screener_service.execute_screening(config_no_requirement)

    print(f"普通策略选股结果数量: {len(results_all)}")
    print(f"弱转强策略选股结果数量: {len(results)}")

    if len(results_all) > len(results):
        print("✅ 弱转强策略正确减少了选股数量（更严格）")
    else:
        print("⚠️  弱转强策略未能有效过滤股票")

    return results


async def main():
    """主测试函数"""
    print("弱转强策略集成测试")
    print("=" * 60)
    print("测试目标: 验证弱转强策略对神剑股份（002361）的识别")
    print("测试日期: 2026-04-07")
    print("测试案例: 神剑股份4/7下跌到缺口位置，4/8强势涨停")
    print("=" * 60)

    try:
        results = await test_weak_to_strong_strategy()

        print("\n" + "=" * 60)
        print("测试总结:")

        if results:
            shenjian_found = any("002361" in r.stock_id for r in results)
            if shenjian_found:
                print("✅ 弱转强策略成功识别神剑股份")
                print("   符合PDF文档中的弱转强买入法特征")

                # 获取神剑股份结果
                shenjian_result = next(r for r in results if "002361" in r.stock_id)
                print(f"   综合得分: {shenjian_result.composite_score:.1f}")
                print(f"   周期维度得分: {shenjian_result.dimension_scores.cycle:.1f}")

                # 检查弱转强特征
                if shenjian_result.dimension_scores.cycle >= 60:
                    print("   ✅ 周期维度得分较高，表明弱转强信号强烈")
                else:
                    print("   ⚠️  周期维度得分一般")
            else:
                print("❌ 弱转强策略未能识别神剑股份")
                print("   可能原因:")
                print("   1. 模拟数据不符合弱转强条件")
                print("   2. 弱转强服务检测逻辑需要优化")
                print("   3. 评分阈值设置过高")
        else:
            print("⚠️  未选出任何股票")
            print("   可能弱转强策略过于严格或模拟数据不足")

    except Exception as e:
        print(f"测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
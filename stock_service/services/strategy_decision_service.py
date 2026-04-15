#!/usr/bin/env python3
"""
策略决策层服务
基于市场环境和主线状态决定操作模式
核心原则：先有主线，再有选股
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Tuple

from stock_service.models import MarketEnvironmentJudgement, ThemeMainlineJudgement


@dataclass
class MarketState:
    """市场状态决策结果"""
    mode: str  # "offensive"/"defensive"/"cautious"/"standby"
    action_bias: str  # "主做"/"试错"/"防守"/"放弃"
    position_limit: float  # 仓位限制 (0.0-1.0)
    market_health_score: float
    main_theme_count: int
    reason: str

    @classmethod
    def offensive(cls, health_score: float, main_count: int) -> "MarketState":
        return cls(
            mode="offensive",
            action_bias="主做",
            position_limit=1.0,
            market_health_score=health_score,
            main_theme_count=main_count,
            reason=f"市场健康度{health_score:.1f}≥70且主线题材{main_count}≥1，可积极进攻"
        )

    @classmethod
    def defensive(cls, health_score: float, main_count: int) -> "MarketState":
        return cls(
            mode="defensive",
            action_bias="防守",
            position_limit=0.5,
            market_health_score=health_score,
            main_theme_count=main_count,
            reason=f"市场健康度{health_score:.1f}≥50且主线题材{main_count}≥1，防守为主"
        )

    @classmethod
    def cautious(cls, health_score: float, main_count: int) -> "MarketState":
        return cls(
            mode="cautious",
            action_bias="试错",
            position_limit=0.3,
            market_health_score=health_score,
            main_theme_count=main_count,
            reason=f"市场健康度{health_score:.1f}≥40，主线题材{main_count}，谨慎试错"
        )

    @classmethod
    def standby(cls, health_score: float, main_count: int) -> "MarketState":
        return cls(
            mode="standby",
            action_bias="放弃",
            position_limit=0.0,
            market_health_score=health_score,
            main_theme_count=main_count,
            reason=f"市场健康度{health_score:.1f}<40或主线题材{main_count}=0，暂停操作"
        )


class StrategyDecisionService:
    """策略决策服务：基于市场环境和主线状态决定操作模式"""

    def __init__(self, db_manager=None):
        self.db_manager = db_manager

    async def get_market_environment_judgement(self, trade_date: date) -> Optional[MarketEnvironmentJudgement]:
        """
        获取市场环境判断
        返回：MarketEnvironmentJudgement对象，如果不存在则返回None
        """
        # TODO: 实现数据库查询，目前返回模拟数据
        # 模拟数据：假设市场健康度75分
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
            evidence=[],
            source_type="p3.phase3.market_environment_judgement",
            source_trace_id="",
            source_trace={},
            source_version="market_environment_judgement.v1.daily_proxy",
            rule_version="market_environment_judgement.v1.daily_proxy"
        )

    async def get_theme_mainline_judgements(self, trade_date: date) -> list[ThemeMainlineJudgement]:
        """
        获取主线题材判断结果
        返回：ThemeMainlineJudgement列表
        """
        # TODO: 实现数据库查询，目前返回模拟数据
        # 模拟数据：假设有2个主线题材
        return [
            ThemeMainlineJudgement(
                trade_date=trade_date.isoformat(),
                subject_key="AI芯片",
                theme_name="人工智能芯片国产替代",
                event_chain_score=28.5,
                event_chain_continuity_score=25.6,
                market_recognition_score=25.8,
                mainline_stability_score=15.6,
                is_main_theme=True,
                theme_tier="main",
                limit_up_count=8,
                novelty_score=22.5,
                timing_score=18.3,
                influence_score=20.1,
                capital_persistence_score=10.5,
                institution_participation_score=6.8,
                retail_attention_score=7.2,
                conclusion="具备主线潜力，事件连续性良好，市场关注度提升",
                evidence_logic=[],
                evidence_market=[],
                source_type="p3.phase2.mainline",
                source_trace_id="",
                source_trace={},
                source_version="theme_mainline_judgement.v1",
                rule_version="theme_mainline_judgement.v1"
            ),
            ThemeMainlineJudgement(
                trade_date=trade_date.isoformat(),
                subject_key="新能源",
                theme_name="新能源汽车产业链",
                event_chain_score=24.3,
                event_chain_continuity_score=22.1,
                market_recognition_score=23.5,
                mainline_stability_score=14.2,
                is_main_theme=True,
                theme_tier="main",
                limit_up_count=6,
                novelty_score=18.5,
                timing_score=16.8,
                influence_score=22.3,
                capital_persistence_score=8.5,
                institution_participation_score=7.2,
                retail_attention_score=6.5,
                conclusion="具备主线潜力，事件连续性良好，市场关注度提升",
                evidence_logic=[],
                evidence_market=[],
                source_type="p3.phase2.mainline",
                source_trace_id="",
                source_trace={},
                source_version="theme_mainline_judgement.v1",
                rule_version="theme_mainline_judgement.v1"
            )
        ]

    async def assess_market_state(self, trade_date: date) -> MarketState:
        """
        评估市场状态，返回决策结果

        决策逻辑：
        1. 市场健康度≥70且主线题材≥1 → 进攻模式
        2. 市场健康度≥50且主线题材≥1 → 防守模式
        3. 市场健康度≥40 → 谨慎模式
        4. 其他 → 观望模式
        """
        try:
            # 获取市场环境判断
            market_env = await self.get_market_environment_judgement(trade_date)
            if not market_env:
                # 如果没有市场环境数据，默认保守
                return MarketState.standby(0.0, 0)

            market_health_score = market_env.market_health_score

            # 获取主线判断结果
            mainline_judgements = await self.get_theme_mainline_judgements(trade_date)
            main_theme_count = sum(1 for j in mainline_judgements if j.theme_tier == "main")

            # 决策逻辑
            if market_health_score >= 70 and main_theme_count >= 1:
                return MarketState.offensive(market_health_score, main_theme_count)
            elif market_health_score >= 50 and main_theme_count >= 1:
                return MarketState.defensive(market_health_score, main_theme_count)
            elif market_health_score >= 40:
                return MarketState.cautious(market_health_score, main_theme_count)
            else:
                return MarketState.standby(market_health_score, main_theme_count)

        except Exception as e:
            # 异常情况，保守处理
            return MarketState.standby(0.0, 0)


# 示例用法
async def example_usage():
    service = StrategyDecisionService()
    trade_date = date(2026, 4, 10)

    market_state = await service.assess_market_state(trade_date)
    print(f"市场状态: {market_state.mode}")
    print(f"操作建议: {market_state.action_bias}")
    print(f"仓位限制: {market_state.position_limit}")
    print(f"理由: {market_state.reason}")
    print(f"市场健康度: {market_state.market_health_score}")
    print(f"主线题材数量: {market_state.main_theme_count}")


if __name__ == "__main__":
    asyncio.run(example_usage())
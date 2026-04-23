#!/usr/bin/env python3
"""
策略决策层服务
基于市场环境和主线状态决定操作模式
核心原则：先有主线，再有选股
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import asyncpg

from stock_service.config import StockServiceConfig
from stock_service.models import MarketEnvironmentJudgement, ThemeMainlineStateV2


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

    def __init__(self, db_manager=None, config: Optional[StockServiceConfig] = None):
        self.db_manager = db_manager
        self.config = config or StockServiceConfig()

    async def _open_conn(self):
        return await asyncpg.connect(
            host=self.config.postgres_host,
            port=self.config.postgres_port,
            database=self.config.postgres_database,
            user=self.config.postgres_user,
            password=self.config.postgres_password,
        )

    async def get_market_environment_judgement(self, trade_date: date) -> Optional[MarketEnvironmentJudgement]:
        """
        获取市场环境判断
        返回：MarketEnvironmentJudgement对象，如果不存在则返回None
        """
        sql = """
        SELECT
            trade_date,
            market_health_score,
            market_bias,
            breadth_status,
            short_term_sentiment_status,
            relay_sentiment_status,
            intraday_fade_status,
            action_bias,
            conclusion,
            evidence,
            source_type,
            source_trace_id,
            source_trace,
            source_version,
            rule_version
        FROM market_environment_judgement
        WHERE trade_date = $1::date
        LIMIT 1
        """
        conn = await self._open_conn()
        try:
            row = await conn.fetchrow(sql, trade_date)
        finally:
            await conn.close()
        if not row:
            return None
        evidence = row["evidence"]
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except Exception:
                evidence = []
        if not isinstance(evidence, list):
            evidence = []
        source_trace = row["source_trace"]
        if isinstance(source_trace, str):
            try:
                source_trace = json.loads(source_trace)
            except Exception:
                source_trace = {}
        if not isinstance(source_trace, dict):
            source_trace = {}
        return MarketEnvironmentJudgement(
            trade_date=row["trade_date"].isoformat() if row.get("trade_date") else trade_date.isoformat(),
            market_health_score=float(row.get("market_health_score") or 0.0),
            market_bias=str(row.get("market_bias") or ""),
            breadth_status=str(row.get("breadth_status") or ""),
            short_term_sentiment_status=str(row.get("short_term_sentiment_status") or ""),
            relay_sentiment_status=str(row.get("relay_sentiment_status") or ""),
            intraday_fade_status=str(row.get("intraday_fade_status") or ""),
            action_bias=str(row.get("action_bias") or ""),
            conclusion=str(row.get("conclusion") or ""),
            evidence=evidence,
            source_type=str(row.get("source_type") or "p3.phase3.market_environment_judgement"),
            source_trace_id=str(row.get("source_trace_id") or ""),
            source_trace=source_trace,
            source_version=str(row.get("source_version") or "market_environment_judgement.v1.daily_proxy"),
            rule_version=str(row.get("rule_version") or "market_environment_judgement.v1.daily_proxy"),
        )

    async def get_mainline_theme_states(self, trade_date: date) -> list[ThemeMainlineStateV2]:
        """
        获取主线题材判断结果（统一口径：theme_cycle_judgement_v2）
        """
        sql = """
        SELECT
            v2.trade_date,
            v2.subject_key,
            COALESCE(NULLIF(v2.theme_name, ''), v2.subject_key) AS theme_name,
            COALESCE(msd.is_mainline, FALSE) AS mainline_alive,
            COALESCE(msd.state, v2.final_cycle_state, '') AS final_cycle_state,
            COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) AS mainline_strength_score,
            COALESCE(v2.fade_risk_score, 0) AS fade_risk_score,
            COALESCE(v2.confidence_score, 0) AS confidence_score,
            COALESCE(v2.rule_reasons, '[]'::jsonb) AS rule_reasons,
            COALESCE(e.event_count_3d, 0) AS event_count_3d,
            COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
            COALESCE(e.limit_up_count, 0) AS limit_up_count
        FROM theme_cycle_judgement_v2 v2
        JOIN mainline_state_daily msd
          ON msd.trade_date = v2.trade_date
         AND msd.subject_key = v2.subject_key
        LEFT JOIN theme_cycle_evidence_daily e
          ON e.trade_date = v2.trade_date
         AND e.subject_key = v2.subject_key
        WHERE v2.trade_date = $1::date
          AND COALESCE(msd.is_mainline, FALSE) = TRUE
          AND COALESCE(msd.state, '') <> 'fade_confirmed'
        ORDER BY
            COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) DESC,
            COALESCE(v2.confidence_score, 0) DESC,
            v2.subject_key
        """
        conn = await self._open_conn()
        try:
            rows = await conn.fetch(sql, trade_date)
        finally:
            await conn.close()
        results: list[ThemeMainlineStateV2] = []
        for row in rows:
            reasons = row["rule_reasons"]
            if isinstance(reasons, str):
                try:
                    reasons = json.loads(reasons)
                except Exception:
                    reasons = []
            if not isinstance(reasons, list):
                reasons = []
            results.append(
                ThemeMainlineStateV2(
                    trade_date=row["trade_date"].isoformat() if row.get("trade_date") else trade_date.isoformat(),
                    subject_key=str(row["subject_key"]),
                    theme_name=str(row["theme_name"]),
                    mainline_alive=bool(row.get("mainline_alive") or False),
                    mainline_bucket=(
                        "main"
                        if float(row.get("mainline_strength_score") or 0.0) >= 75.0
                        else "strong_branch"
                    ),
                    event_count_3d=float(row.get("event_count_3d") or 0.0),
                    event_continuity_score=float(row.get("event_continuity_score") or 0.0),
                    confidence_score=float(row.get("confidence_score") or 0.0),
                    mainline_strength_score=float(row.get("mainline_strength_score") or 0.0),
                    limit_up_count=int(row.get("limit_up_count") or 0),
                    final_cycle_state=str(row.get("final_cycle_state") or ""),
                    fade_risk_score=float(row.get("fade_risk_score") or 0.0),
                    conclusion=f"状态={row.get('final_cycle_state') or '--'}；主线强度={float(row.get('mainline_strength_score') or 0):.2f}",
                    rule_reasons=[str(x) for x in reasons[:4]],
                    source_type="theme_cycle_judgement_v2",
                    source_trace_id="",
                    source_trace={},
                    source_version="theme_cycle_judgement.v2",
                    rule_version="theme_cycle_judgement.v2",
                )
            )
        return results

    async def get_theme_mainline_judgements(self, trade_date: date) -> list[ThemeMainlineStateV2]:
        """兼容旧方法名：返回主线状态列表（v2语义）。"""
        return await self.get_mainline_theme_states(trade_date)

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
            mainline_states = await self.get_mainline_theme_states(trade_date)
            main_theme_count = sum(1 for j in mainline_states if j.mainline_alive)

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

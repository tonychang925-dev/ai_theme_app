#!/usr/bin/env python3
"""
主线题材判断增强服务
实现PDF交易体系理论中的逻辑维度和市场维度增强评分

Phase 2: 数据计算模块
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from stock_service.models import ThemeMainlineJudgement


@dataclass
class NoveltyScoreInputs:
    """新颖度评分输入数据"""
    first_appear_date: Optional[date]  # 题材首次出现日期
    media_coverage_frequency: float    # 媒体报道频率（0-1）
    concept_novelty: str               # 概念新颖性：'new'/'extension'/'traditional'
    media_reports_last_7d: int        # 近7天媒体报道次数
    

@dataclass
class TimingScoreInputs:
    """时机评分输入数据"""
    market_health_score: float        # 市场健康度评分（0-100）
    limit_up_count_market: int        # 全市场涨停家数
    days_since_last_main_theme: int   # 距离上个主线题材结束天数
    market_sentiment_score: float     # 市场情绪得分（0-100）
    

@dataclass
class InfluenceScoreInputs:
    """影响广度评分输入数据"""
    related_stock_count: int          # 关联股票数量
    industry_count: int               # 涉及行业数量
    policy_level: str                 # 政策级别：'national'/'provincial'/'industry'/'none'
    market_cap_total: float           # 总市值（亿元）
    

@dataclass
class CapitalPersistenceInputs:
    """资金流入持续性输入数据"""
    net_inflow_days: int              # 连续净流入天数
    net_inflow_amount_avg: float      # 日均净流入金额（亿元）
    net_inflow_trend: str             # 流入趋势：'strong'/'moderate'/'weak'/'outflow'
    

@dataclass
class InstitutionParticipationInputs:
    """机构参与度输入数据"""
    institution_seat_count: int       # 龙虎榜机构席位出现次数
    institution_research_count: int   # 机构调研次数
    fund_holding_ratio: float         # 基金持股比例
    

@dataclass
class RetailAttentionInputs:
    """散户关注度输入数据"""
    search_index_score: float         # 搜索指数得分（0-100）
    community_discussion_score: float # 社区讨论热度得分（0-100）
    social_media_mentions: int        # 社交媒体提及次数
    

class ThemeMainlineEnhancementService:
    """
    主线题材判断增强服务
    实现PDF交易体系理论中的逻辑维度和市场维度评分
    """
    
    def compute_novelty_score(self, inputs: NoveltyScoreInputs) -> float:
        """
        计算新颖度评分（0-30分）
        算法：
        1. base_score: 基于首次出现时间（0-15分）
        2. media_score: 媒体报道频率（0-10分）
        3. concept_score: 概念新颖性（0-5分）
        """
        # 1. base_score: 基于首次出现时间（0-15分）
        base_score = 0.0
        if inputs.first_appear_date:
            days_diff = (date.today() - inputs.first_appear_date).days
            if days_diff <= 7:
                base_score = 15.0
            elif days_diff <= 30:
                base_score = 10.0
            elif days_diff <= 90:
                base_score = 5.0
            else:
                base_score = 0.0

        # 2. media_score: 媒体报道频率（0-10分）
        # 基于media_reports_last_7d计算报道频率
        media_score = 0.0
        if inputs.media_reports_last_7d >= 7:
            media_score = 10.0  # 高频报道（日均有报道）
        elif inputs.media_reports_last_7d >= 3:
            media_score = 6.0   # 中频报道（周均有报道）
        elif inputs.media_reports_last_7d > 0:
            media_score = 3.0   # 低频报道（月均有报道）
        else:
            media_score = 0.0   # 无报道

        # 3. concept_score: 概念新颖性（0-5分）
        concept_score = {
            'new': 5.0,        # 全新概念/技术
            'extension': 3.0,   # 现有概念延伸
            'traditional': 1.0, # 传统概念
        }.get(inputs.concept_novelty, 0.0)

        total = base_score + media_score + concept_score
        return min(total, 30.0)
    
    def compute_timing_score(self, inputs: TimingScoreInputs) -> float:
        """
        计算时机评分（0-25分）
        算法：
        1. market_env_score: 市场环境（0-10分）
        2. sentiment_score: 市场情绪（0-10分）
        3. gap_score: 题材荒间隙（0-5分）
        """
        # TODO: 实现具体算法
        market_env_score = inputs.market_health_score * 0.1  # 转换到0-10分
        
        sentiment_score = 0.0
        if inputs.limit_up_count_market > 50:
            sentiment_score = 10.0
        elif inputs.limit_up_count_market >= 20:
            sentiment_score = 7.0
        elif inputs.limit_up_count_market >= 10:
            sentiment_score = 4.0
        else:
            sentiment_score = 1.0
        
        gap_score = 0.0
        if inputs.days_since_last_main_theme > 30:
            gap_score = 5.0
        elif inputs.days_since_last_main_theme >= 15:
            gap_score = 3.0
        else:
            gap_score = 1.0
        
        total = market_env_score + sentiment_score + gap_score
        return min(total, 25.0)
    
    def compute_influence_score(self, inputs: InfluenceScoreInputs) -> float:
        """
        计算影响广度评分（0-25分）
        算法：
        1. stock_count_score: 关联股票数量（0-10分）
        2. industry_score: 行业覆盖面（0-10分）
        3. policy_score: 政策级别（0-5分）
        """
        # TODO: 实现具体算法
        stock_count_score = 0.0
        if inputs.related_stock_count > 50:
            stock_count_score = 10.0
        elif inputs.related_stock_count >= 20:
            stock_count_score = 7.0
        elif inputs.related_stock_count >= 10:
            stock_count_score = 4.0
        else:
            stock_count_score = 1.0
        
        industry_score = 0.0
        if inputs.industry_count > 5:
            industry_score = 10.0
        elif inputs.industry_count >= 3:
            industry_score = 7.0
        elif inputs.industry_count >= 2:
            industry_score = 4.0
        else:
            industry_score = 1.0
        
        policy_score = {
            'national': 5.0,
            'provincial': 3.0,
            'industry': 1.0,
            'none': 0.0
        }.get(inputs.policy_level, 0.0)
        
        total = stock_count_score + industry_score + policy_score
        return min(total, 25.0)
    
    def compute_capital_persistence_score(self, inputs: CapitalPersistenceInputs) -> float:
        """
        计算资金流入持续性评分（0-15分）
        算法：
        1. flow_trend_score: 流入趋势（0-8分）
        2. flow_amount_score: 流入金额（0-7分）
        """
        # TODO: 实现具体算法
        flow_trend_score = 0.0
        if inputs.net_inflow_trend == 'strong' and inputs.net_inflow_days >= 5:
            flow_trend_score = 8.0
        elif inputs.net_inflow_trend == 'moderate' and inputs.net_inflow_days >= 3:
            flow_trend_score = 5.0
        elif inputs.net_inflow_trend == 'weak':
            flow_trend_score = 2.0
        else:
            flow_trend_score = 0.0
        
        flow_amount_score = 0.0
        if inputs.net_inflow_amount_avg > 10.0:
            flow_amount_score = 7.0
        elif inputs.net_inflow_amount_avg >= 1.0:
            flow_amount_score = 4.0
        elif inputs.net_inflow_amount_avg > 0:
            flow_amount_score = 1.0
        
        total = flow_trend_score + flow_amount_score
        return min(total, 15.0)
    
    def compute_institution_participation_score(self, inputs: InstitutionParticipationInputs) -> float:
        """
        计算机构参与度评分（0-10分）
        算法：
        1. seat_score: 龙虎榜机构席位（0-6分）
        2. research_score: 机构调研（0-4分）
        """
        # TODO: 实现具体算法
        seat_score = min(inputs.institution_seat_count * 2.0, 6.0)
        
        research_score = 4.0 if inputs.institution_research_count > 0 else 0.0
        
        total = seat_score + research_score
        return min(total, 10.0)
    
    def compute_retail_attention_score(self, inputs: RetailAttentionInputs) -> float:
        """
        计算散户关注度评分（0-10分）
        算法：
        1. search_score: 搜索指数（0-5分）
        2. community_score: 社区讨论（0-5分）
        """
        # 1. search_score: 搜索指数（0-5分）
        # 假定search_index_score是0-100分
        search_score = 0.0
        if inputs.search_index_score >= 70:
            search_score = 5.0  # 搜索指数高位: 5分
        elif inputs.search_index_score >= 30:
            search_score = 3.0  # 搜索指数中位: 3分
        elif inputs.search_index_score > 0:
            search_score = 1.0  # 搜索指数低位: 1分
        else:
            search_score = 0.0  # 无搜索数据

        # 2. community_score: 社区讨论（0-5分）
        # 假定community_discussion_score是0-100分
        community_score = 0.0
        if inputs.community_discussion_score >= 70:
            community_score = 5.0  # 讨论热度高: 5分
        elif inputs.community_discussion_score >= 30:
            community_score = 3.0  # 讨论热度中: 3分
        elif inputs.community_discussion_score > 0:
            community_score = 1.0  # 讨论热度低: 1分
        else:
            community_score = 0.0  # 无讨论数据

        total = search_score + community_score
        return min(total, 10.0)
    
    def compute_all_scores_from_inputs(
        self,
        novelty_inputs: NoveltyScoreInputs,
        timing_inputs: TimingScoreInputs,
        influence_inputs: InfluenceScoreInputs,
        capital_inputs: CapitalPersistenceInputs,
        institution_inputs: InstitutionParticipationInputs,
        retail_inputs: RetailAttentionInputs,
    ) -> Dict[str, float]:
        """
        从输入数据计算所有增强评分
        返回字典包含6个评分维度
        """
        novelty_score = self.compute_novelty_score(novelty_inputs)
        timing_score = self.compute_timing_score(timing_inputs)
        influence_score = self.compute_influence_score(influence_inputs)
        capital_persistence_score = self.compute_capital_persistence_score(capital_inputs)
        institution_participation_score = self.compute_institution_participation_score(institution_inputs)
        retail_attention_score = self.compute_retail_attention_score(retail_inputs)

        return {
            'novelty_score': novelty_score,
            'timing_score': timing_score,
            'influence_score': influence_score,
            'capital_persistence_score': capital_persistence_score,
            'institution_participation_score': institution_participation_score,
            'retail_attention_score': retail_attention_score
        }

    async def compute_all_scores(self,
                                trade_date: str,
                                subject_key: str) -> Dict[str, float]:
        """
        计算所有增强评分
        从数据库获取数据，然后计算评分
        TODO: 实现数据获取逻辑
        """
        # TODO: 实现从数据库获取所有输入数据
        # 目前返回占位值
        return {
            'novelty_score': 0.0,
            'timing_score': 0.0,
            'influence_score': 0.0,
            'capital_persistence_score': 0.0,
            'institution_participation_score': 0.0,
            'retail_attention_score': 0.0
        }
    
    def enhance_judgement_with_inputs(
        self,
        judgement: ThemeMainlineJudgement,
        novelty_inputs: NoveltyScoreInputs,
        timing_inputs: TimingScoreInputs,
        influence_inputs: InfluenceScoreInputs,
        capital_inputs: CapitalPersistenceInputs,
        institution_inputs: InstitutionParticipationInputs,
        retail_inputs: RetailAttentionInputs,
    ) -> ThemeMainlineJudgement:
        """
        使用输入数据增强现有主线判断结果
        计算所有增强评分并更新judgement对象
        """
        scores = self.compute_all_scores_from_inputs(
            novelty_inputs,
            timing_inputs,
            influence_inputs,
            capital_inputs,
            institution_inputs,
            retail_inputs,
        )

        # 创建增强后的judgement对象
        enhanced = ThemeMainlineJudgement(
            trade_date=judgement.trade_date,
            subject_key=judgement.subject_key,
            theme_name=judgement.theme_name,
            event_chain_score=judgement.event_chain_score,
            event_chain_continuity_score=judgement.event_chain_continuity_score,
            market_recognition_score=judgement.market_recognition_score,
            mainline_stability_score=judgement.mainline_stability_score,
            is_main_theme=judgement.is_main_theme,
            theme_tier=judgement.theme_tier,
            limit_up_count=judgement.limit_up_count,
            novelty_score=scores['novelty_score'],
            timing_score=scores['timing_score'],
            influence_score=scores['influence_score'],
            capital_persistence_score=scores['capital_persistence_score'],
            institution_participation_score=scores['institution_participation_score'],
            retail_attention_score=scores['retail_attention_score'],
            conclusion=judgement.conclusion,
            evidence_logic=judgement.evidence_logic,
            evidence_market=judgement.evidence_market,
            source_type=judgement.source_type,
            source_trace_id=judgement.source_trace_id,
            source_trace=judgement.source_trace,
            source_version=judgement.source_version,
            rule_version=judgement.rule_version,
        )
        return enhanced

    async def enhance_judgement(self,
                               judgement: ThemeMainlineJudgement) -> ThemeMainlineJudgement:
        """
        增强现有主线判断结果
        计算所有增强评分并更新judgement对象
        """
        scores = await self.compute_all_scores(
            judgement.trade_date,
            judgement.subject_key
        )

        # 创建增强后的judgement对象
        enhanced = ThemeMainlineJudgement(
            trade_date=judgement.trade_date,
            subject_key=judgement.subject_key,
            theme_name=judgement.theme_name,
            event_chain_score=judgement.event_chain_score,
            event_chain_continuity_score=judgement.event_chain_continuity_score,
            market_recognition_score=judgement.market_recognition_score,
            mainline_stability_score=judgement.mainline_stability_score,
            is_main_theme=judgement.is_main_theme,
            theme_tier=judgement.theme_tier,
            limit_up_count=judgement.limit_up_count,
            novelty_score=scores['novelty_score'],
            timing_score=scores['timing_score'],
            influence_score=scores['influence_score'],
            capital_persistence_score=scores['capital_persistence_score'],
            institution_participation_score=scores['institution_participation_score'],
            retail_attention_score=scores['retail_attention_score'],
            conclusion=judgement.conclusion,
            evidence_logic=judgement.evidence_logic,
            evidence_market=judgement.evidence_market,
            source_type=judgement.source_type,
            source_trace_id=judgement.source_trace_id,
            source_trace=judgement.source_trace,
            source_version=judgement.source_version,
            rule_version=judgement.rule_version,
        )
        return enhanced


# 示例用法
async def example_usage():
    service = ThemeMainlineEnhancementService()
    
    # 示例输入
    novelty_inputs = NoveltyScoreInputs(
        first_appear_date=date(2026, 4, 1),
        media_coverage_frequency=0.8,
        concept_novelty='new',
        media_reports_last_7d=5
    )
    
    score = service.compute_novelty_score(novelty_inputs)
    print(f"新颖度评分: {score:.2f}")


if __name__ == "__main__":
    asyncio.run(example_usage())

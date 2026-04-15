from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional
from datetime import date

from stock_service.services.mainline_judgement_service import (
    MainlineJudgementService,
    ThemeEventStats,
    ThemeMarketStats,
)
from stock_service.models import ThemeMainlineJudgement


@dataclass(frozen=True)
class ThemeEvidenceLayers:
    """四层证据数据"""
    event_driven: Dict[str, Any]
    leader_relay: Dict[str, Any]
    board_structure: Dict[str, Any]
    theme_kline: Dict[str, Any]


@dataclass(frozen=True)
class EnhancedMainlineInputs:
    """增强版主线判定输入"""
    event_stats: ThemeEventStats
    market_stats: ThemeMarketStats
    evidence_layers: ThemeEvidenceLayers


class EnhancedMainlineJudgementService(MainlineJudgementService):
    """
    增强版主线判定服务
    在原有事件链+市场承认基础上，集成四层证据体系
    保持原有接口兼容，新增增强功能
    """

    def compute_evidence_layers(self, trade_date: date, subject_key: str,
                               event_stats: ThemeEventStats,
                               market_stats: ThemeMarketStats) -> ThemeEvidenceLayers:
        """
        计算四层证据评分
        注意：这是简化实现，实际需要从数据库获取详细数据
        """
        # 1. 事件驱动层
        event_driven = {
            "event_count_3d": self._estimate_event_count_3d(event_stats),
            "event_count_7d": event_stats.recent_event_count,
            "strong_event_count_7d": event_stats.key_event_count,
            "event_recency_days": self._compute_event_recency(event_stats),
            "event_continuity_score": self.compute_event_chain_continuity_score(event_stats),
            "event_strength_score": self.compute_event_chain_score(event_stats),
        }

        # 2. 龙头/接力层
        leader_relay = {
            "leader_alive_score": self._compute_leader_alive_score(market_stats),
            "relay_strength_score": self._compute_relay_strength_score(market_stats),
            "front_row_survival_ratio": self._estimate_front_row_survival(market_stats),
        }

        # 3. 板块结构层
        board_structure = {
            "board_stock_count": market_stats.member_count,
            "limit_up_count": market_stats.limit_up_count,
            "red_ratio": self._compute_red_ratio(market_stats),
            "front_row_strength_score": self._compute_front_row_strength(market_stats),
        }

        # 4. 板块K线技术层
        theme_kline = {
            "theme_ret_3d": self._estimate_theme_return_3d(trade_date, subject_key),
            "theme_support_score": self._compute_theme_support_score(trade_date, subject_key),
        }

        return ThemeEvidenceLayers(
            event_driven=event_driven,
            leader_relay=leader_relay,
            board_structure=board_structure,
            theme_kline=theme_kline
        )

    def compute_mainline_strength_score(self, evidence_layers: ThemeEvidenceLayers) -> float:
        """
        计算主线强度评分（0-100）
        基于四层证据加权计算
        """
        weights = {
            "event_driven": 0.3,
            "leader_relay": 0.3,
            "board_structure": 0.25,
            "theme_kline": 0.15
        }

        # 各层评分（简化计算，实际需归一化）
        event_score = min(evidence_layers.event_driven.get("event_strength_score", 0) * 1.2, 100)
        leader_score = min(evidence_layers.leader_relay.get("leader_alive_score", 0) * 1.5, 100)
        board_score = min(evidence_layers.board_structure.get("front_row_strength_score", 0) * 1.3, 100)
        kline_score = min(evidence_layers.theme_kline.get("theme_support_score", 0) * 1.1, 100)

        # 加权总分
        total_score = (
            event_score * weights["event_driven"] +
            leader_score * weights["leader_relay"] +
            board_score * weights["board_structure"] +
            kline_score * weights["theme_kline"]
        )

        return min(max(total_score, 0.0), 100.0)

    def determine_mainline_alive(self, is_main_theme: bool,
                                evidence_layers: ThemeEvidenceLayers,
                                strength_score: float) -> bool:
        """
        判断主线是否存活
        基于设计方案中的公式：主线存活 = 主线题材 + 强度≥60 + 龙头存活≥40 + 3日内有事件
        """
        if not is_main_theme:
            return False

        if strength_score < 60:
            return False

        leader_alive = evidence_layers.leader_relay.get("leader_alive_score", 0)
        if leader_alive < 40:
            return False

        event_count_3d = evidence_layers.event_driven.get("event_count_3d", 0)
        if event_count_3d < 1:
            return False

        return True

    def build_enhanced_judgement(self, trade_date: str,
                                 event_stats: ThemeEventStats,
                                 market_stats: ThemeMarketStats,
                                 evidence_layers: Optional[ThemeEvidenceLayers] = None) -> ThemeMainlineJudgement:
        """
        构建增强版主线判定结果
        保持原有接口，增加增强字段
        """
        # 1. 使用原有逻辑构建基础判定
        base_judgement = super().build_judgement(trade_date, event_stats, market_stats)

        # 2. 计算证据层（如果未提供）
        if evidence_layers is None:
            trade_date_obj = date.fromisoformat(trade_date)
            evidence_layers = self.compute_evidence_layers(trade_date_obj, event_stats.subject_key,
                                                          event_stats, market_stats)

        # 3. 计算增强评分
        strength_score = self.compute_mainline_strength_score(evidence_layers)
        mainline_alive = self.determine_mainline_alive(
            base_judgement.is_main_theme, evidence_layers, strength_score
        )

        # 4. 构建增强结果
        enhanced_dict = base_judgement.__dict__.copy()

        # 添加增强字段（通过source_trace存储，保持模型兼容）
        enhanced_trace = enhanced_dict.get("source_trace", {}).copy()
        enhanced_trace.update({
            "evidence_layers": {
                "event_driven": evidence_layers.event_driven,
                "leader_relay": evidence_layers.leader_relay,
                "board_structure": evidence_layers.board_structure,
                "theme_kline": evidence_layers.theme_kline,
            },
            "mainline_strength_score": strength_score,
            "mainline_alive": mainline_alive,
        })

        enhanced_dict["source_trace"] = enhanced_trace
        enhanced_dict["source_version"] = "theme_mainline_judgement.enhanced.v1"

        return ThemeMainlineJudgement(**enhanced_dict)

    # ===== 辅助方法（简化实现，实际需从数据库获取） =====

    def _estimate_event_count_3d(self, event_stats: ThemeEventStats) -> int:
        """估计3日内事件数量（简化：假设每日平均）"""
        if event_stats.distinct_event_days == 0:
            return 0
        avg_per_day = event_stats.recent_event_count / max(event_stats.distinct_event_days, 1)
        return min(int(avg_per_day * 3), event_stats.recent_event_count)

    def _compute_event_recency(self, event_stats: ThemeEventStats) -> int:
        """计算事件最近性（最近事件距离今天天数）"""
        # 简化：如果有当日事件，则最近性为0
        return 0 if event_stats.today_event_count > 0 else 1

    def _compute_leader_alive_score(self, market_stats: ThemeMarketStats) -> float:
        """计算龙头存活评分"""
        score = 0.0
        if market_stats.leader_limit_up:
            score += 60.0
        if market_stats.leader_pct_chg >= 5:
            score += 30.0
        if market_stats.leader_pct_chg >= 0:
            score += 10.0
        return min(score, 100.0)

    def _compute_relay_strength_score(self, market_stats: ThemeMarketStats) -> float:
        """计算接力强度评分"""
        if market_stats.strong_stock_count >= 3:
            return 70.0
        elif market_stats.strong_stock_count >= 1:
            return 40.0
        else:
            return 20.0

    def _estimate_front_row_survival(self, market_stats: ThemeMarketStats) -> float:
        """估计前排存活率（简化）"""
        if market_stats.member_count == 0:
            return 0.0
        strong_ratio = market_stats.strong_stock_count / market_stats.member_count
        return min(strong_ratio, 1.0)

    def _compute_red_ratio(self, market_stats: ThemeMarketStats) -> float:
        """计算红盘率（简化：假设强势股占比）"""
        if market_stats.member_count == 0:
            return 0.0
        # 简化：涨停和强势股视为红盘
        red_count = market_stats.limit_up_count + max(0, market_stats.strong_stock_count - market_stats.limit_up_count)
        return min(red_count / market_stats.member_count, 1.0)

    def _compute_front_row_strength(self, market_stats: ThemeMarketStats) -> float:
        """计算前排强度"""
        score = 0.0
        score += min(market_stats.limit_up_count * 15.0, 60.0)
        score += min(market_stats.strong_stock_count * 5.0, 30.0)
        if market_stats.leader_limit_up:
            score += 10.0
        return min(score, 100.0)

    def _estimate_theme_return_3d(self, trade_date: date, subject_key: str) -> float:
        """估计主题3日收益率（简化：返回0，实际需查数据库）"""
        # TODO: 从数据库查询主题K线数据
        return 0.0

    def _compute_theme_support_score(self, trade_date: date, subject_key: str) -> float:
        """计算主题支撑评分（简化）"""
        # TODO: 从数据库查询支撑压力数据
        return 50.0


# 兼容性包装器
def build_mainline_judgement(trade_date: str,
                             event_stats: ThemeEventStats,
                             market_stats: ThemeMarketStats,
                             enhanced: bool = False) -> ThemeMainlineJudgement:
    """
    兼容性包装函数
    enhanced=True时使用增强版，否则使用原版
    """
    if enhanced:
        service = EnhancedMainlineJudgementService()
        return service.build_enhanced_judgement(trade_date, event_stats, market_stats)
    else:
        service = MainlineJudgementService()
        return service.build_judgement(trade_date, event_stats, market_stats)
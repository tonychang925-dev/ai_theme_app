from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import date

from stock_service.services.four_layer_evidence_system import (
    EventLayerEvidence,
    LeaderLayerEvidence,
    BoardStructureEvidence,
    KLineEvidence,
    FourLayerEvidence
)


@dataclass
class SubScores:
    """子评分计算结果"""
    leader_alive_score: float = 0.0  # 龙头存活评分（0-100）
    support_score: float = 0.0       # 支撑评分（0-100）
    event_continuity_score: float = 0.0  # 事件连续性评分（0-100）
    board_collapse_score: float = 0.0    # 板块崩盘评分（0-100）
    leader_dead_score: float = 0.0       # 龙头已死评分（0-100）
    successor_vacuum_score: float = 0.0  # 接力真空评分（0-100）
    event_chain_broken_score: float = 0.0  # 事件链断裂评分（0-100）
    repair_window_score: float = 0.0    # 修复窗口评分（0-100）


class FourLayerScoringService:
    """四层评分服务
    实现用户提供的统一score公式
    """

    @staticmethod
    def calculate_leader_alive_score(leader_evidence: LeaderLayerEvidence) -> float:
        """计算龙头存活评分（0-100）"""
        score = 0.0

        if leader_evidence.leader_limit_up:
            score += 60.0
        elif leader_evidence.leader_pct_chg >= 5.0:
            score += 40.0
        elif leader_evidence.leader_pct_chg >= 0.0:
            score += 20.0
        elif leader_evidence.leader_pct_chg >= -5.0:
            score += 10.0

        if leader_evidence.has_successor:
            score += 20.0

        score += min(leader_evidence.successor_limit_up_count * 10.0, 20.0)
        score += min(leader_evidence.leader_consecutive_days * 5.0, 20.0)

        return min(score, 100.0)

    @staticmethod
    def calculate_support_score(kline_evidence: KLineEvidence) -> float:
        """计算支撑评分（0-100）"""
        score = 0.0

        # 技术支撑
        if kline_evidence.has_support:
            score += 40.0

        # 成交量支撑
        if kline_evidence.board_volume_ratio >= 1.2:
            score += 30.0
        elif kline_evidence.board_volume_ratio >= 0.8:
            score += 15.0

        # 连续红盘支撑
        score += min(kline_evidence.board_red_days * 10.0, 30.0)

        # 过热扣分
        if kline_evidence.is_overheated:
            score -= 20.0

        return max(0.0, min(score, 100.0))

    @staticmethod
    def calculate_event_continuity_score(event_evidence: EventLayerEvidence) -> float:
        """计算事件连续性评分（0-100）"""
        score = 0.0

        # 事件链连续性
        score += event_evidence.event_chain_continuity_score * 0.6

        # 当日是否有新事件
        if event_evidence.has_new_event:
            score += 30.0

        # 事件重要性
        score += event_evidence.event_importance * 0.1

        # 媒体报道热度
        score += event_evidence.media_coverage * 0.1

        return min(score, 100.0)

    @staticmethod
    def calculate_board_collapse_score(board_evidence: BoardStructureEvidence) -> float:
        """计算板块崩盘评分（0-100）"""
        score = 0.0

        # 涨停数量极少
        if board_evidence.limit_up_count == 0:
            score += 40.0
        elif board_evidence.limit_up_count <= 2:
            score += 20.0

        # 强势股数量极少
        if board_evidence.strong_stock_count <= 2:
            score += 30.0
        elif board_evidence.strong_stock_count <= 5:
            score += 15.0

        # 无涨停梯队
        if not board_evidence.has_limit_up_梯队:
            score += 15.0

        # 无跟风股
        if not board_evidence.has_followers:
            score += 15.0

        return min(score, 100.0)

    @staticmethod
    def calculate_leader_dead_score(leader_evidence: LeaderLayerEvidence) -> float:
        """计算龙头已死评分（0-100）"""
        score = 0.0

        # 龙头大幅下跌
        if leader_evidence.leader_pct_chg <= -5.0:
            score += 60.0
        elif leader_evidence.leader_pct_chg <= 0.0:
            score += 30.0

        # 龙头跌停状态
        if leader_evidence.leader_status == "跌停":
            score += 40.0
        elif leader_evidence.leader_status == "走弱":
            score += 20.0

        return min(score, 100.0)

    @staticmethod
    def calculate_successor_vacuum_score(leader_evidence: LeaderLayerEvidence) -> float:
        """计算接力真空评分（0-100）"""
        score = 0.0

        # 无接力卡位
        if not leader_evidence.has_successor:
            score += 70.0

        # 接力涨停数量极少
        if leader_evidence.successor_limit_up_count == 0:
            score += 30.0

        return min(score, 100.0)

    @staticmethod
    def calculate_event_chain_broken_score(event_evidence: EventLayerEvidence) -> float:
        """计算事件链断裂评分（0-100）"""
        score = 0.0

        # 事件链分数低
        if event_evidence.event_chain_score < 20.0:
            score += 60.0
        elif event_evidence.event_chain_score < 40.0:
            score += 30.0

        # 事件连续性分数低
        if event_evidence.event_chain_continuity_score < 20.0:
            score += 40.0
        elif event_evidence.event_chain_continuity_score < 40.0:
            score += 20.0

        return min(score, 100.0)

    @staticmethod
    def calculate_repair_window_score(evidence: FourLayerEvidence) -> float:
        """计算修复窗口评分（0-100）
        基于用户提供的公式：修复窗口评分 = (主线强度评分 * 0.6) + (修复窗口评分 * 0.4)
        注意：这里的修复窗口评分是一个子评分，用于计算repair_score
        """
        # 先计算基础评分
        score = 0.0

        # 检查是否在分歧状态
        if evidence.is_mainline_alive():
            score += 40.0

        # 检查是否有活口
        if evidence.board_layer.limit_up_count >= 1:
            score += 30.0

        # 检查是否有支撑
        if evidence.kline_layer.has_support:
            score += 30.0

        return min(score, 100.0)

    def calculate_all_sub_scores(self, evidence: FourLayerEvidence) -> SubScores:
        """计算所有子评分"""
        return SubScores(
            leader_alive_score=self.calculate_leader_alive_score(evidence.leader_layer),
            support_score=self.calculate_support_score(evidence.kline_layer),
            event_continuity_score=self.calculate_event_continuity_score(evidence.event_layer),
            board_collapse_score=self.calculate_board_collapse_score(evidence.board_layer),
            leader_dead_score=self.calculate_leader_dead_score(evidence.leader_layer),
            successor_vacuum_score=self.calculate_successor_vacuum_score(evidence.leader_layer),
            event_chain_broken_score=self.calculate_event_chain_broken_score(evidence.event_layer),
            repair_window_score=self.calculate_repair_window_score(evidence)
        )

    def calculate_mainline_strength_score(self,
                                         is_main_theme: bool,
                                         sub_scores: SubScores) -> float:
        """计算主线强度评分（0-100）
        用户公式：
        主线题材 = (is_main_theme ? 60 : 20) + (leader_alive_score * 0.6) + (support_score * 0.15) + (event_continuity_score * 0.25)
        支线题材 = 20 + (leader_alive_score * 0.4) + (support_score * 0.2) + (event_continuity_score * 0.4)
        """
        if is_main_theme:
            score = 60.0
            score += sub_scores.leader_alive_score * 0.6
            score += sub_scores.support_score * 0.15
            score += sub_scores.event_continuity_score * 0.25
        else:
            score = 20.0
            score += sub_scores.leader_alive_score * 0.4
            score += sub_scores.support_score * 0.2
            score += sub_scores.event_continuity_score * 0.4

        return min(score, 100.0)

    def calculate_fade_watch_score(self, sub_scores: SubScores) -> float:
        """计算退潮观察评分（0-100）
        用户公式：fade_watch_score = (板块崩盘评分) + (龙头已死评分) + (接力真空评分) + (事件链断裂评分)
        注意：这里应该是加权平均，而不是简单相加，防止超过100
        """
        # 用户公式中的四项，取平均值
        score = (
            sub_scores.board_collapse_score * 0.25 +
            sub_scores.leader_dead_score * 0.25 +
            sub_scores.successor_vacuum_score * 0.25 +
            sub_scores.event_chain_broken_score * 0.25
        )
        return min(score, 100.0)

    def calculate_fade_confirmed_score(self,
                                      fade_watch_score: float,
                                      previous_state: Optional[str] = None) -> float:
        """计算退潮确认评分（0-100）
        用户公式：fade_confirmed_score = fade_watch_score + (前一日previous_state是fade_watch则+10)
        """
        score = fade_watch_score
        if previous_state == "fade_watch":
            score += 10.0

        return min(score, 100.0)

    def calculate_divergence_score(self,
                                  mainline_strength_score: float,
                                  repair_window_score: float) -> float:
        """计算分歧评分（0-100）
        用户公式：divergence_score = (主线强度评分 * 0.6) + (修复窗口评分 * 0.4)
        """
        score = mainline_strength_score * 0.6 + repair_window_score * 0.4
        return min(score, 100.0)

    def calculate_repair_score(self,
                              divergence_score: float,
                              previous_strength_score: float) -> float:
        """计算修复评分（0-100）
        用户公式：repair_score = (分歧评分 * 0.7) + (分歧前强度 * 0.3)
        """
        score = divergence_score * 0.7 + previous_strength_score * 0.3
        return min(score, 100.0)

    def determine_cycle_state(self,
                             evidence: FourLayerEvidence,
                             previous_state: Optional[str] = None,
                             previous_strength_score: float = 50.0) -> Dict[str, float]:
        """基于四层证据和评分确定周期状态
        返回所有评分结果
        """
        # 计算所有子评分
        sub_scores = self.calculate_all_sub_scores(evidence)

        # 计算主线强度评分
        is_main_theme = evidence.is_mainline_alive()
        mainline_strength_score = self.calculate_mainline_strength_score(is_main_theme, sub_scores)

        # 计算退潮相关评分
        fade_watch_score = self.calculate_fade_watch_score(sub_scores)
        fade_confirmed_score = self.calculate_fade_confirmed_score(fade_watch_score, previous_state)

        # 计算分歧和修复评分
        divergence_score = self.calculate_divergence_score(mainline_strength_score, sub_scores.repair_window_score)
        repair_score = self.calculate_repair_score(divergence_score, previous_strength_score)

        # 确定周期状态（简化版，基于证据的状态机）
        if fade_confirmed_score >= 80.0:
            final_cycle_state = "fade_confirmed"
        elif fade_watch_score >= 60.0:
            final_cycle_state = "fade_watch"
        elif repair_score >= 70.0 and is_main_theme:
            final_cycle_state = "repair"
        elif divergence_score >= 60.0 and is_main_theme:
            final_cycle_state = "divergence"
        elif mainline_strength_score >= 80.0 and is_main_theme:
            final_cycle_state = "fermentation"
        elif mainline_strength_score >= 60.0 and is_main_theme:
            final_cycle_state = "acceleration"
        else:
            final_cycle_state = "start" if is_main_theme else "divergence"

        # ── final_mainline_alive ──
        # 设计文档 §25.3：final_mainline_alive = NOT fade_confirmed
        # 不等于 is_main_theme。强度不够 ≠ 主线死亡。
        final_mainline_alive = (final_cycle_state != "fade_confirmed")

        return {
            "final_mainline_alive": final_mainline_alive,
            "mainline_strength_score": mainline_strength_score,
            "final_cycle_state": final_cycle_state,
            "fade_watch_score": fade_watch_score,
            "fade_confirmed_score": fade_confirmed_score,
            "divergence_score": divergence_score,
            "repair_score": repair_score,
            "leader_alive_score": sub_scores.leader_alive_score,
            "support_score": sub_scores.support_score,
            "event_continuity_score": sub_scores.event_continuity_score,
            "board_collapse_score": sub_scores.board_collapse_score,
            "leader_dead_score": sub_scores.leader_dead_score,
            "successor_vacuum_score": sub_scores.successor_vacuum_score,
            "event_chain_broken_score": sub_scores.event_chain_broken_score,
            "repair_window_score": sub_scores.repair_window_score,
        }
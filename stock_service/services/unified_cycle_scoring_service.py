from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class CycleEvidenceInput:
    """周期证据输入（对应 theme_cycle_evidence_daily 表）"""
    # 基础信息
    trade_date: str
    subject_key: str
    theme_name: str

    # 事件层
    event_strength_score: float = 0.0        # 事件强度评分（0-100）
    event_continuity_score: float = 0.0      # 事件连续性评分（0-100）
    strong_event_count_7d: int = 0           # 7日内强事件数量
    event_recency_days: Optional[int] = None # 最近事件天数（None表示无事件）

    # 龙头/接力层
    leader_alive_score: float = 0.0          # 龙头存活评分（0-100）
    leader_breakdown_flag: bool = False      # 龙头破位标志
    relay_strength_score: float = 0.0        # 接力强度评分（0-100）
    front_row_survival_ratio: float = 0.0    # 前排存活率（0-1）

    # 板块结构层
    limit_up_count: int = 0                  # 涨停数量
    limit_down_count: int = 0                # 跌停数量
    red_ratio: float = 0.0                   # 红盘比例（0-1）
    big_drop_ratio: float = 0.0              # 大跌比例（0-1）
    front_row_strength_score: float = 0.0    # 前排强度评分（0-100）

    # 板块K线技术层
    theme_support_score: float = 0.0         # 板块技术支撑评分（0-100）
    break_start_pivot: bool = False          # 是否跌破启动枢轴

    # 前一日状态（用于状态转换）
    previous_cycle_state: Optional[str] = None  # 前一日最终周期状态


class UnifiedCycleScoringService:
    """统一周期评分服务
    严格按照设计文档15.2节的公式实现
    """

    @staticmethod
    def calculate_mainline_strength_score(evidence: CycleEvidenceInput) -> float:
        """计算主线强度评分（15.2.2节公式）

        mainline_strength_score = round(
            min(event_strength_score * 0.25, 25)
            + min(event_continuity_score * 0.20, 20)
            + min(leader_alive_score * 0.20, 20)
            + min(relay_strength_score * 0.15, 15)
            + min(front_row_strength_score * 0.10, 10)
            + min(theme_support_score * 0.10, 10),
            2,
        )
        """
        score = 0.0
        score += min(evidence.event_strength_score * 0.25, 25)
        score += min(evidence.event_continuity_score * 0.20, 20)
        score += min(evidence.leader_alive_score * 0.20, 20)
        score += min(evidence.relay_strength_score * 0.15, 15)
        score += min(evidence.front_row_strength_score * 0.10, 10)
        score += min(evidence.theme_support_score * 0.10, 10)

        return round(min(score, 100.0), 2)

    @staticmethod
    def calculate_fade_watch_score(evidence: CycleEvidenceInput) -> float:
        """计算退潮观察评分（15.2.2节公式）

        fade_watch_score = round(
            (20 if strong_event_count_7d == 0 else 0)
            + (10 if (event_recency_days or 999) >= 3 else 0)
            + (20 if leader_alive_score < 50 else 0)
            + (15 if relay_strength_score < 40 else 0)
            + (15 if front_row_survival_ratio < 0.5 else 0)
            + (10 if big_drop_ratio >= 0.25 else 0)
            + (10 if theme_support_score < 50 else 0),
            2,
        )
        """
        score = 0.0

        # 事件层
        if evidence.strong_event_count_7d == 0:
            score += 20.0

        event_recency = evidence.event_recency_days if evidence.event_recency_days is not None else 999
        if event_recency >= 3:
            score += 10.0

        # 龙头层
        if evidence.leader_alive_score < 50:
            score += 20.0

        if evidence.relay_strength_score < 40:
            score += 15.0

        if evidence.front_row_survival_ratio < 0.5:
            score += 15.0

        # 结构层
        if evidence.big_drop_ratio >= 0.25:
            score += 10.0

        # K线层
        if evidence.theme_support_score < 50:
            score += 10.0

        return round(min(score, 100.0), 2)

    @staticmethod
    def calculate_fade_confirmed_score(evidence: CycleEvidenceInput) -> float:
        """计算退潮确认评分（15.2.2节公式）

        fade_confirmed_score = round(
            (25 if strong_event_count_7d == 0 and (event_recency_days or 999) >= 3 else 0)
            + (25 if leader_alive_score < 30 and leader_breakdown_flag else 0)
            + (20 if relay_strength_score < 30 and front_row_survival_ratio < 0.3 else 0)
            + (15 if limit_down_count >= 2 or big_drop_ratio >= 0.4 else 0)
            + (15 if break_start_pivot and theme_support_score < 40 else 0),
            2,
        )
        """
        score = 0.0

        # 事件层
        event_recency = evidence.event_recency_days if evidence.event_recency_days is not None else 999
        if evidence.strong_event_count_7d == 0 and event_recency >= 3:
            score += 25.0

        # 龙头层
        if evidence.leader_alive_score < 30 and evidence.leader_breakdown_flag:
            score += 25.0

        # 接力层
        if evidence.relay_strength_score < 30 and evidence.front_row_survival_ratio < 0.3:
            score += 20.0

        # 结构层
        if evidence.limit_down_count >= 2 or evidence.big_drop_ratio >= 0.4:
            score += 15.0

        # K线层
        if evidence.break_start_pivot and evidence.theme_support_score < 40:
            score += 15.0

        return round(min(score, 100.0), 2)

    @staticmethod
    def calculate_fade_risk_score(evidence: CycleEvidenceInput) -> float:
        """计算退潮风险评分（设计文档要求的字段）

        fade_risk_score 衡量主题退潮的风险程度，基于四层证据：
        1. 事件层：事件时效性差、连续性低
        2. 龙头层：龙头破位、存活度低
        3. 结构层：跌停多、大跌比例高
        4. K线层：跌破启动枢轴、支撑弱
        """
        score = 0.0

        # 事件层风险（0-25分）
        event_recency = evidence.event_recency_days if evidence.event_recency_days is not None else 999
        if evidence.strong_event_count_7d == 0:
            score += 15.0  # 无强事件
        if event_recency >= 2:  # 事件时效性差（≥2天）
            score += 10.0 * min(event_recency / 5.0, 1.0)  # 最多10分

        # 龙头层风险（0-25分）
        if evidence.leader_breakdown_flag:
            score += 15.0  # 龙头破位
        if evidence.leader_alive_score < 50:
            score += (50 - evidence.leader_alive_score) * 0.2  # 最多10分

        # 接力层风险（0-20分）
        if evidence.relay_strength_score < 40:
            score += (40 - evidence.relay_strength_score) * 0.25  # 最多10分
        if evidence.front_row_survival_ratio < 0.4:
            score += 10.0  # 前排存活率低

        # 结构层风险（0-20分）
        score += min(evidence.limit_down_count * 5.0, 10.0)  # 每个跌停5分，最多10分
        score += min(evidence.big_drop_ratio * 25.0, 10.0)  # 大跌比例贡献，最多10分

        # K线层风险（0-10分）
        if evidence.break_start_pivot:
            score += 5.0
        if evidence.theme_support_score < 60:
            score += (60 - evidence.theme_support_score) * 0.1  # 最多5分

        return round(min(score, 100.0), 2)

    @staticmethod
    def calculate_divergence_score(evidence: CycleEvidenceInput,
                                  final_mainline_alive: bool) -> float:
        """计算分歧评分（15.2.4节公式）

        divergence_score = round(
            (25 if final_mainline_alive else 0)
            + min(max(leader_alive_score - 40, 0) * 0.5, 15)
            + min(relay_strength_score * 0.15, 15)
            + (10 if limit_down_count == 0 else 0)
            + (10 if big_drop_ratio < 0.3 else 0)
            + min(theme_support_score * 0.25, 25),
            2,
        )
        """
        score = 0.0

        if final_mainline_alive:
            score += 25.0

        # 龙头层
        score += min(max(evidence.leader_alive_score - 40, 0) * 0.5, 15)

        # 接力层
        score += min(evidence.relay_strength_score * 0.15, 15)

        # 结构层
        if evidence.limit_down_count == 0:
            score += 10.0

        if evidence.big_drop_ratio < 0.3:
            score += 10.0

        # K线层
        score += min(evidence.theme_support_score * 0.25, 25)

        return round(min(score, 100.0), 2)

    @staticmethod
    def calculate_repair_score(evidence: CycleEvidenceInput) -> float:
        """计算修复评分（15.2.4节公式）

        repair_score = round(
            min(leader_alive_score * 0.25, 25)
            + min(relay_strength_score * 0.20, 20)
            + min(red_ratio * 20, 20)  # red_ratio: 0~1
            + min(front_row_strength_score * 0.15, 15)
            + min(theme_support_score * 0.20, 20),
            2,
        )
        """
        score = 0.0

        # 龙头层
        score += min(evidence.leader_alive_score * 0.25, 25)

        # 接力层
        score += min(evidence.relay_strength_score * 0.20, 20)

        # 结构层
        score += min(evidence.red_ratio * 20, 20)  # red_ratio: 0~1

        # 前排强度
        score += min(evidence.front_row_strength_score * 0.15, 15)

        # K线层
        score += min(evidence.theme_support_score * 0.20, 20)

        return round(min(score, 100.0), 2)

    def determine_mainline_alive_rule(self, evidence: CycleEvidenceInput,
                                     mainline_strength_score: float) -> bool:
        """确定主线存活规则（15.2.1节公式）

        mainline_alive_rule = (
            mainline_strength_score >= 60
            and leader_alive_score >= 40
            and (strong_event_count_7d > 0 or event_continuity_score >= 40)
        )
        """
        return (
            mainline_strength_score >= 60
            and evidence.leader_alive_score >= 40
            and (evidence.strong_event_count_7d > 0 or evidence.event_continuity_score >= 40)
        )

    def can_transition_to_repair(self, repair_score: float,
                                previous_state: Optional[str]) -> bool:
        """检查是否可以转换到repair状态（15.2.5节规则）

        repair 仅允许从 divergence 或 fade_watch 转入
        """
        if previous_state is None:
            return False  # 无历史记录时不得成立

        allowed_previous_states = {"divergence", "fade_watch"}
        return (
            repair_score >= 65
            and previous_state in allowed_previous_states
        )

    def determine_final_cycle_state(self,
                                   evidence: CycleEvidenceInput,
                                   mainline_strength_score: float,
                                   fade_watch_score: float,
                                   fade_confirmed_score: float,
                                   divergence_score: float,
                                   repair_score: float,
                                   final_mainline_alive: bool) -> str:
        """确定最终周期状态（15.2.6节状态机顺序）"""

        # 1. 退潮确认（最高优先级）
        if fade_confirmed_score >= 60:
            return "fade_confirmed"

        # 2. 修复状态（有条件转换）
        if (repair_score >= 65 and
            self.can_transition_to_repair(repair_score, evidence.previous_cycle_state)):
            return "repair"

        # 3. 分歧状态
        if divergence_score >= 60:
            return "divergence"

        # 4. 退潮观察
        if fade_watch_score >= 50:
            return "fade_watch"

        # 5. 加速状态
        if mainline_strength_score >= 75 and evidence.limit_up_count >= 3:
            return "acceleration"

        # 6. 发酵状态
        if mainline_strength_score >= 60:
            return "fermentation"

        # 7. 启动状态
        return "start"

    def calculate_all_scores(self, evidence: CycleEvidenceInput) -> Dict[str, float]:
        """计算所有评分"""
        # 计算基础评分
        mainline_strength_score = self.calculate_mainline_strength_score(evidence)
        fade_watch_score = self.calculate_fade_watch_score(evidence)
        fade_confirmed_score = self.calculate_fade_confirmed_score(evidence)
        fade_risk_score = self.calculate_fade_risk_score(evidence)

        # 确定主线存活规则
        mainline_alive_rule = self.determine_mainline_alive_rule(evidence, mainline_strength_score)

        # 计算分歧和修复评分（需要主线存活状态）
        divergence_score = self.calculate_divergence_score(evidence, mainline_alive_rule)
        repair_score = self.calculate_repair_score(evidence)

        # 确定最终周期状态
        final_cycle_state = self.determine_final_cycle_state(
            evidence, mainline_strength_score, fade_watch_score, fade_confirmed_score,
            divergence_score, repair_score, mainline_alive_rule
        )

        # 确定退潮相关状态
        fade_watch = fade_watch_score >= 50 and fade_confirmed_score < 60
        fade_confirmed = fade_confirmed_score >= 60

        return {
            "mainline_strength_score": mainline_strength_score,
            "fade_watch_score": fade_watch_score,
            "fade_confirmed_score": fade_confirmed_score,
            "fade_risk_score": fade_risk_score,
            "divergence_score": divergence_score,
            "repair_score": repair_score,
            "mainline_alive_rule": mainline_alive_rule,
            "final_cycle_state": final_cycle_state,
            "fade_watch": fade_watch,
            "fade_confirmed": fade_confirmed,
            "leader_alive_score": evidence.leader_alive_score,
            "event_continuity_score": evidence.event_continuity_score,
            "theme_support_score": evidence.theme_support_score,
        }

    def classify_pool_entry_type(self,
                                judgement: Dict[str, float],
                                stock_support_score: float) -> str:
        """分类候选池进入类型（15.3.3节公式）

        formal_allow = (
            final_mainline_alive is True
            and fade_confirmed is False
            and mainline_strength_score >= 60
        )

        observe_only_allow = (
            fade_confirmed is False
            and leader_alive_score >= 70
            and support_score >= 75
            and event_continuity_score >= 40
            and mainline_strength_score >= 40
        )
        """
        # 注意：judgement中的final_mainline_alive对应mainline_alive_rule
        final_mainline_alive = judgement.get("mainline_alive_rule", False)
        fade_confirmed = judgement.get("fade_confirmed", False)
        mainline_strength_score = judgement.get("mainline_strength_score", 0)
        leader_alive_score = judgement.get("leader_alive_score", 0)
        event_continuity_score = judgement.get("event_continuity_score", 0)

        # 正式准入
        formal_allow = (
            final_mainline_alive is True
            and fade_confirmed is False
            and mainline_strength_score >= 60
        )

        # 观察准入
        observe_only_allow = (
            fade_confirmed is False
            and leader_alive_score >= 70
            and stock_support_score >= 75
            and event_continuity_score >= 40
            and mainline_strength_score >= 40
        )

        if formal_allow:
            return "formal"
        if observe_only_allow:
            return "observe_only"
        return "reject"
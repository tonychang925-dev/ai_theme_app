# theme_service/theme_state_builder.py

import uuid
from datetime import date
from typing import List, Dict, Optional

from theme_service.models.theme_state import ThemeState


class ThemeStateBuilder:
    """
    将「事件集合」构建为「题材某日状态 ThemeState」
    """

    def __init__(self, semantic_matcher):
        self.semantic_matcher = semantic_matcher

    # =========================
    # 主入口
    # =========================
    def build(
        self,
        theme: Dict,
        events: List[Dict],
        trade_date: date
    ) -> ThemeState:

        if not events:
            raise ValueError("ThemeStateBuilder: events 不能为空")

        theme_id = theme["theme_id"]
        theme_name = theme["theme_name"]

        # ---------- 事件统计 ----------
        event_count = len(events)
        core_event_id = self._select_core_event(events)

        # ---------- 语义一致性 ----------
        event_consistency = self._calc_event_consistency(
            theme_name, events
        )

        # ---------- 热度 & 强度 ----------
        heat_score = self._calc_heat_score(events)
        strength_score = self._calc_strength_score(
            heat_score, event_consistency
        )

        # ---------- 生命周期 ----------
        lifecycle_stage = self._judge_lifecycle(
            heat_score, strength_score, event_consistency
        )

        # ---------- 行情（占位，后续补） ----------
        avg_stock_return = 0.0
        limit_up_count = 0
        limit_down_count = 0
        capital_inflow = None

        # ---------- 输出控制 ----------
        is_active = lifecycle_stage not in ("decline", "dead")
        is_recommended = self._judge_recommend(
            lifecycle_stage, strength_score, event_consistency
        )

        output_priority = self._calc_output_priority(
            lifecycle_stage, heat_score
        )

        return ThemeState(
            theme_state_id=str(uuid.uuid4()),
            theme_id=theme_id,
            theme_name=theme_name,
            trade_date=trade_date,

            heat_score=round(heat_score, 2),
            strength_score=round(strength_score, 2),
            confidence_score=round(event_consistency, 3),

            lifecycle_stage=lifecycle_stage,

            event_count=event_count,
            core_event_id=core_event_id,
            event_consistency=round(event_consistency, 3),

            avg_stock_return=avg_stock_return,
            limit_up_count=limit_up_count,
            limit_down_count=limit_down_count,
            capital_inflow=capital_inflow,

            leader_stock_code=None,
            leader_strength=None,
            top3_concentration=0.0,

            is_active=is_active,
            is_recommended=is_recommended,
            output_priority=output_priority
        )

    # =========================
    # 内部方法
    # =========================

    def _select_core_event(self, events: List[Dict]) -> Optional[str]:
        """
        选逻辑最强的事件（简单规则版）
        """
        events_sorted = sorted(
            events,
            key=lambda x: x.get("confidence", 0),
            reverse=True
        )
        return events_sorted[0].get("event_id")

    def _calc_event_consistency(
        self,
        theme_name: str,
        events: List[Dict]
    ) -> float:
        """
        使用你已经跑通的 semantic matcher
        """
        scores = []
        for e in events:
            text = e.get("event_text") or e.get("summary", "")
            result = self.semantic_matcher.match(text)
            if result and result["theme"] == theme_name:
                scores.append(result["confidence"])

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    def _calc_heat_score(self, events: List[Dict]) -> float:
        """
        热度 = 事件数量 + 信息源权重（简化版）
        """
        base = len(events) * 10

        bonus = 0
        for e in events:
            if e.get("source") in ("财联社", "新华社"):
                bonus += 3
            if e.get("is_breaking"):
                bonus += 2

        return min(base + bonus, 100.0)

    def _calc_strength_score(
        self,
        heat_score: float,
        event_consistency: float
    ) -> float:
        """
        强度 = 热度 × 一致性
        """
        return heat_score * event_consistency

    def _judge_lifecycle(
        self,
        heat_score: float,
        strength_score: float,
        consistency: float
    ) -> str:
        """
        生命周期规则版（第一阶段够用）
        """
        if heat_score < 20:
            return "incubation"

        if heat_score >= 20 and consistency >= 0.8 and strength_score < 40:
            return "start"

        if strength_score >= 40 and consistency >= 0.85:
            return "acceleration"

        if strength_score >= 70:
            return "peak"

        if consistency < 0.6:
            return "distribution"

        if heat_score < 15:
            return "decline"

        return "incubation"

    def _judge_recommend(
        self,
        lifecycle_stage: str,
        strength_score: float,
        consistency: float
    ) -> bool:
        return (
            lifecycle_stage in ("start", "acceleration", "peak")
            and strength_score >= 30
            and consistency >= 0.75
        )

    def _calc_output_priority(
        self,
        lifecycle_stage: str,
        heat_score: float
    ) -> int:
        if lifecycle_stage == "acceleration":
            return 1
        if lifecycle_stage == "start":
            return 2
        if lifecycle_stage == "peak":
            return 3
        if heat_score >= 30:
            return 4
        return 5

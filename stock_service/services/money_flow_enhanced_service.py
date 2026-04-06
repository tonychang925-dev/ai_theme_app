from __future__ import annotations

from dataclasses import dataclass

from stock_service.models import MoneyFlowEnhanced


def _clip(value: float, upper: float = 100.0) -> float:
    return max(0.0, min(upper, round(value, 2)))


@dataclass(frozen=True)
class MoneyFlowInput:
    trade_date: str
    subject_key: str
    theme_name: str
    stock_id: str
    stock_name: str
    role_label: str
    candidate_rank: int
    composite_score: float
    turnover_rate: float
    volume_ratio: float
    main_net_inflow: float
    is_limit_up: bool
    dragon_tiger_net_amount: float
    institution_seat_count: int
    position_label: str = ""
    pattern_labels: tuple[str, ...] = ()


class MoneyFlowEnhancedService:
    """
    P3.phase2-T02 最小实现：
    - 先生成资金行为增强对象
    - 给出现阶段可解释的资金分层与角色增强标签
    """

    def compute_activity_score(self, row: MoneyFlowInput) -> float:
        score = 0.0
        score += min(max(row.turnover_rate, 0.0), 25.0) * 2.0
        score += min(max(row.volume_ratio, 0.0), 10.0) * 3.0
        if row.is_limit_up:
            score += 15.0
        return _clip(score)

    def compute_capital_flow_score(self, row: MoneyFlowInput) -> float:
        score = 0.0
        score += min(max(row.main_net_inflow, 0.0) / 5e7, 10.0) * 4.0
        score += min(max(row.dragon_tiger_net_amount, 0.0) / 5e7, 10.0) * 4.0
        score += min(max(float(row.institution_seat_count), 0.0), 10.0) * 3.0
        return _clip(score)

    def compute_money_flow_score(self, activity_score: float, capital_flow_score: float, composite_score: float) -> float:
        return _clip(activity_score * 0.35 + capital_flow_score * 0.45 + composite_score * 0.20)

    def derive_money_flow_tier(self, score: float) -> str:
        if score >= 55:
            return "HIGH"
        if score >= 35:
            return "MEDIUM"
        return "LOW"

    def derive_role_enhanced(self, row: MoneyFlowInput, money_flow_tier: str) -> str:
        if row.role_label == "龙头" and money_flow_tier == "HIGH":
            return "龙头/资金共振"
        if row.role_label == "龙头":
            return "龙头观察"
        if row.role_label in {"龙二", "卡位"} and money_flow_tier in {"HIGH", "MEDIUM"}:
            return "前排"
        if row.role_label in {"龙二", "卡位"}:
            return "卡位观察"
        if row.role_label in {"补涨", "强趋势", "套利"} and money_flow_tier in {"HIGH", "MEDIUM"}:
            return "扩散"
        return "跟风"

    def build_explanation(
        self,
        row: MoneyFlowInput,
        activity_score: float,
        capital_flow_score: float,
        money_flow_tier: str,
        role_enhanced: str,
    ) -> list[str]:
        return [
            f"角色 {row.role_label} -> {role_enhanced}",
            f"活跃度 {activity_score:.2f}",
            f"资金流强度 {capital_flow_score:.2f}",
            f"资金分层 {money_flow_tier}",
        ] + (
            [f"K线位置 {row.position_label}"] if row.position_label else []
        ) + (
            [f"K线形态 {'/'.join(row.pattern_labels)}"] if row.pattern_labels else []
        )

    def build_item(self, row: MoneyFlowInput) -> MoneyFlowEnhanced:
        activity_score = self.compute_activity_score(row)
        capital_flow_score = self.compute_capital_flow_score(row)
        money_flow_score = self.compute_money_flow_score(activity_score, capital_flow_score, row.composite_score)
        money_flow_tier = self.derive_money_flow_tier(money_flow_score)
        role_enhanced = self.derive_role_enhanced(row, money_flow_tier)
        return MoneyFlowEnhanced(
            trade_date=row.trade_date,
            subject_key=row.subject_key,
            theme_name=row.theme_name,
            stock_id=row.stock_id,
            stock_name=row.stock_name,
            role_label=row.role_label,
            role_enhanced=role_enhanced,
            candidate_rank=row.candidate_rank,
            composite_score=row.composite_score,
            activity_score=activity_score,
            capital_flow_score=capital_flow_score,
            money_flow_score=money_flow_score,
            money_flow_tier=money_flow_tier,
            turnover_rate=row.turnover_rate,
            volume_ratio=row.volume_ratio,
            main_net_inflow=row.main_net_inflow,
            dragon_tiger_net_amount=row.dragon_tiger_net_amount,
            institution_seat_count=row.institution_seat_count,
            explanation=self.build_explanation(row, activity_score, capital_flow_score, money_flow_tier, role_enhanced),
            sources=["theme_leader_candidate", "dragon_tiger_object"],
        )

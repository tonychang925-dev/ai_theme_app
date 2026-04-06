from __future__ import annotations

from dataclasses import dataclass

from stock_service.models import ThemeEnvironmentJudgement


@dataclass(frozen=True)
class ThemeEnvironmentInput:
    subject_key: str
    theme_name: str
    theme_tier: str
    is_main_theme: bool
    primary_cycle_stage: str
    action_bias: str
    limit_up_count: int
    strong_stock_count: int
    member_count: int
    leader_limit_up: bool
    leader_pct_chg: float


class ThemeEnvironmentJudgementService:
    """
    P3.phase3 小环境层：
    回答题材/板块今天是否健康、是否有板块效应、龙头是否带队、跟风是否跟得上。
    """

    def derive_board_health_status(self, item: ThemeEnvironmentInput) -> str:
        if item.primary_cycle_stage == "climax":
            return "板块过热"
        if item.primary_cycle_stage == "fade":
            return "板块走弱"
        if item.limit_up_count >= 5 and item.strong_stock_count >= 12:
            return "板块健康"
        if item.limit_up_count >= 2 and item.strong_stock_count >= 6:
            return "板块尚可"
        return "板块脆弱"

    def derive_board_effect_status(self, item: ThemeEnvironmentInput) -> str:
        if item.limit_up_count >= 6 or item.strong_stock_count >= 15:
            return "板块联动明显"
        if item.limit_up_count >= 3 or item.member_count >= 8:
            return "板块联动一般"
        return "单点脉冲"

    def derive_leader_support_status(self, item: ThemeEnvironmentInput) -> str:
        if item.leader_limit_up and item.leader_pct_chg >= 9.8:
            return "龙头强带队"
        if item.leader_pct_chg >= 5.0:
            return "龙头仍活跃"
        if item.leader_pct_chg > 0:
            return "龙头偏弱"
        return "龙头失速"

    def derive_follow_strength_status(self, item: ThemeEnvironmentInput) -> str:
        if item.strong_stock_count >= 12:
            return "后排跟随强"
        if item.strong_stock_count >= 6:
            return "后排有跟随"
        if item.member_count >= 4:
            return "后排跟随弱"
        return "后排掉队"

    def derive_action_bias(self, item: ThemeEnvironmentInput, health: str, effect: str, leader: str, follow: str) -> str:
        if health == "板块过热":
            return "警惕高潮"
        if health == "板块走弱" or leader == "龙头失速":
            return "放弃"
        if effect == "板块联动明显" and leader in {"龙头强带队", "龙头仍活跃"} and follow in {"后排跟随强", "后排有跟随"}:
            return "可主做"
        if item.primary_cycle_stage in {"divergence", "rebound"}:
            return "可做弱转强"
        if item.theme_tier in {"main", "strong_branch"}:
            return "可观察"
        return "放弃"

    def build_conclusion(self, item: ThemeEnvironmentInput, health: str, effect: str, leader: str, follow: str, action_bias: str) -> str:
        return (
            f"{health}；{effect}；{leader}；{follow}。"
            f"当前阶段 {item.primary_cycle_stage}，板块动作建议：{action_bias}"
        )

    def build_evidence(self, item: ThemeEnvironmentInput, health: str, effect: str, leader: str, follow: str) -> list[str]:
        return [
            f"题材分层={item.theme_tier}；周期={item.primary_cycle_stage}",
            f"涨停 {item.limit_up_count} 家；强势股 {item.strong_stock_count} 家；成分股 {item.member_count} 家",
            f"龙头涨幅 {item.leader_pct_chg:.2f}%；龙头涨停={item.leader_limit_up}",
            f"{health}；{effect}；{leader}；{follow}",
        ]

    def build_judgement(self, trade_date: str, item: ThemeEnvironmentInput) -> ThemeEnvironmentJudgement:
        health = self.derive_board_health_status(item)
        effect = self.derive_board_effect_status(item)
        leader = self.derive_leader_support_status(item)
        follow = self.derive_follow_strength_status(item)
        action_bias = self.derive_action_bias(item, health, effect, leader, follow)
        return ThemeEnvironmentJudgement(
            trade_date=trade_date,
            subject_key=item.subject_key,
            theme_name=item.theme_name,
            board_health_status=health,
            board_effect_status=effect,
            leader_support_status=leader,
            follow_strength_status=follow,
            action_bias=action_bias,
            conclusion=self.build_conclusion(item, health, effect, leader, follow, action_bias),
            evidence=self.build_evidence(item, health, effect, leader, follow),
        )

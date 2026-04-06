from __future__ import annotations

from dataclasses import dataclass

from stock_service.models import ThemeCycleJudgement


def _clip(value: float, upper: float = 100.0) -> float:
    return max(0.0, min(upper, round(value, 2)))


@dataclass(frozen=True)
class ThemeCycleMainlineInput:
    subject_key: str
    theme_name: str
    is_main_theme: bool
    theme_tier: str
    event_chain_score: float
    event_chain_continuity_score: float
    market_recognition_score: float
    mainline_stability_score: float
    limit_up_count: int


@dataclass(frozen=True)
class ThemeCycleMarketInput:
    subject_key: str
    theme_name: str
    limit_up_count: int
    strong_stock_count: int
    leader_pct_chg: float
    member_count: int
    leader_limit_up: bool


@dataclass(frozen=True)
class ThemeCycleRecentInput:
    subject_key: str
    recent_rank_days: int
    recent_positive_days: int
    recent_red_days: int
    recent_negative_days: int


class CycleJudgementService:
    """
    P3.phase2 模块 2：
    围绕“主线 + 周期位置 + 动作建议”生成题材周期判断。
    """

    def derive_leader_status(self, market: ThemeCycleMarketInput) -> str:
        if market.leader_limit_up and market.leader_pct_chg >= 15:
            return "龙头加强"
        if market.leader_limit_up:
            return "龙头强势"
        if market.leader_pct_chg >= 5:
            return "龙头活跃"
        return "龙头走弱"

    def derive_board_effect_status(self, market: ThemeCycleMarketInput) -> str:
        if market.limit_up_count >= 10 or market.strong_stock_count >= 25:
            return "板块高潮"
        if market.limit_up_count >= 5 or market.strong_stock_count >= 12:
            return "板块健康"
        if market.limit_up_count >= 2 or market.strong_stock_count >= 6:
            return "板块联动"
        return "板块分化"

    def classify_primary_stage(
        self,
        mainline: ThemeCycleMainlineInput,
        market: ThemeCycleMarketInput,
        recent: ThemeCycleRecentInput,
    ) -> tuple[str, str, str]:
        event_total = mainline.event_chain_score + mainline.event_chain_continuity_score

        if mainline.is_main_theme:
            if market.limit_up_count >= 10 or market.strong_stock_count >= 25:
                return "climax", "警惕高潮", "主线过热，需警惕高潮后分歧"
            if market.leader_limit_up and market.limit_up_count <= 2 and market.strong_stock_count < 12:
                return "divergence", "关注弱转强", "龙头仍强但板块分化，重点看弱转强"
            if (
                recent.recent_rank_days >= 1
                and market.leader_limit_up
                and 2 <= market.limit_up_count <= 4
                and mainline.market_recognition_score >= 55
            ):
                return "rebound", "关注弱转强", "主线分歧后存在回流修复，适合观察弱转强"
            if market.leader_limit_up and (market.limit_up_count >= 3 or market.strong_stock_count >= 8):
                return "fermentation", "主做", "主线联动增强，进入发酵/主做区间"
            if event_total >= 30 and mainline.market_recognition_score >= 45:
                return "start", "试错", "逻辑先成立但板块扩散不足，适合轻仓试错"
            return "fade", "放弃", "主线承认减弱，暂不建议参与"

        if (
            event_total >= 25
            and mainline.market_recognition_score >= 45
            and market.limit_up_count <= 2
        ):
            return "start", "试错", "逻辑浮现但板块尚未全面扩散，可低仓试错"
        if (
            recent.recent_rank_days >= 1
            and market.leader_limit_up
            and market.limit_up_count >= 2
            and mainline.market_recognition_score >= 50
        ):
            return "rebound", "关注弱转强", "强支线存在回流迹象，重点看弱转强承接"
        return "fade", "放弃", "非主线且承认不足，暂时放弃"

    def compute_confidence(
        self,
        mainline: ThemeCycleMainlineInput,
        market: ThemeCycleMarketInput,
        recent: ThemeCycleRecentInput,
    ) -> float:
        score = 0.0
        score += min(mainline.market_recognition_score, 100.0) * 0.35
        score += min(mainline.mainline_stability_score, 100.0) * 0.25
        score += min(market.limit_up_count, 10) * 3.0
        score += min(max(market.leader_pct_chg, 0.0), 20.0) * 1.2
        score += min(recent.recent_rank_days, 5) * 4.0
        if market.leader_limit_up:
            score += 8.0
        return _clip(score)

    def build_evidence(
        self,
        mainline: ThemeCycleMainlineInput,
        market: ThemeCycleMarketInput,
        recent: ThemeCycleRecentInput,
        leader_status: str,
        board_effect_status: str,
    ) -> list[str]:
        return [
            f"题材分层={mainline.theme_tier}",
            f"当日涨停 {market.limit_up_count} 家，强势股 {market.strong_stock_count} 家",
            f"龙头状态={leader_status}，龙头涨幅 {market.leader_pct_chg:.2f}%",
            f"板块状态={board_effect_status}",
            f"近端题材活跃 {recent.recent_rank_days} 天，红盘 {recent.recent_red_days} 天",
        ]

    def build_judgement(
        self,
        trade_date: str,
        mainline: ThemeCycleMainlineInput,
        market: ThemeCycleMarketInput,
        recent: ThemeCycleRecentInput,
    ) -> ThemeCycleJudgement:
        leader_status = self.derive_leader_status(market)
        board_effect_status = self.derive_board_effect_status(market)
        primary_cycle_stage, action_bias, conclusion = self.classify_primary_stage(mainline, market, recent)
        confidence = self.compute_confidence(mainline, market, recent)

        return ThemeCycleJudgement(
            trade_date=trade_date,
            subject_key=mainline.subject_key,
            theme_name=mainline.theme_name,
            is_main_theme=mainline.is_main_theme,
            is_start=primary_cycle_stage == "start",
            is_fermentation=primary_cycle_stage == "fermentation",
            is_divergence=primary_cycle_stage == "divergence",
            is_rebound=primary_cycle_stage == "rebound",
            is_climax=primary_cycle_stage == "climax",
            is_fade=primary_cycle_stage == "fade",
            primary_cycle_stage=primary_cycle_stage,
            limit_up_count=market.limit_up_count,
            leader_status=leader_status,
            board_effect_status=board_effect_status,
            action_bias=action_bias,
            confidence=confidence,
            conclusion=conclusion,
            evidence=self.build_evidence(mainline, market, recent, leader_status, board_effect_status),
        )

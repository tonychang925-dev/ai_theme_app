from __future__ import annotations

from dataclasses import dataclass

from stock_service.models import PreMarketExecutionPlan


@dataclass(frozen=True)
class ExecutionMainlineInput:
    subject_key: str
    theme_name: str
    is_main_theme: bool
    theme_tier: str
    conclusion: str


@dataclass(frozen=True)
class ExecutionCycleInput:
    subject_key: str
    primary_cycle_stage: str
    action_bias: str
    leader_status: str
    board_effect_status: str
    conclusion: str


@dataclass(frozen=True)
class ExecutionLeaderInput:
    subject_key: str
    stock_id: str
    stock_name: str
    role_label: str
    candidate_rank: int
    composite_score: float
    position_label: str = ""
    pattern_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionAuctionSignalInput:
    stock_id: str
    stock_name: str
    auction_signal_level: str
    signal_type: str
    action_today: str
    hard_reject_reason: str
    auction_signal_score: float


class PreMarketExecutionService:
    """
    P3.phase2 最后一层：
    盘前不重做主线判断，只承接昨晚三张真源表，生成可执行观察清单。
    """

    def derive_theme_status(self, mainline: ExecutionMainlineInput, cycle: ExecutionCycleInput) -> str:
        if cycle.primary_cycle_stage == "fade":
            return "证伪"
        if mainline.is_main_theme:
            if cycle.primary_cycle_stage in {"fermentation", "rebound", "start"}:
                return "延续"
            if cycle.primary_cycle_stage in {"divergence", "climax"}:
                return "弱化"
        if mainline.theme_tier == "strong_branch" and cycle.primary_cycle_stage in {"start", "rebound"}:
            return "延续"
        return "弱化"

    def derive_leader_status(self, cycle: ExecutionCycleInput, leader: ExecutionLeaderInput | None) -> str:
        if leader is None:
            return "放弃"
        if cycle.primary_cycle_stage == "fade":
            return "放弃"
        if cycle.primary_cycle_stage == "rebound":
            return "弱转强候选"
        if cycle.primary_cycle_stage in {"fermentation", "start"}:
            return "继续成立"
        if cycle.primary_cycle_stage == "divergence":
            return "弱转强候选"
        if cycle.primary_cycle_stage == "climax":
            return "继续成立"
        return "放弃"

    def derive_action_today(
        self,
        theme_status: str,
        cycle: ExecutionCycleInput,
        auction_signal: ExecutionAuctionSignalInput | None = None,
    ) -> str:
        if auction_signal is not None:
            if auction_signal.action_today in {"act", "watch", "avoid"}:
                return auction_signal.action_today
        if theme_status == "证伪" or cycle.action_bias == "放弃":
            return "avoid"
        if cycle.action_bias == "主做" and theme_status == "延续":
            return "act"
        return "watch"

    def build_invalid_conditions(self, cycle: ExecutionCycleInput, leader: ExecutionLeaderInput | None) -> list[str]:
        conditions = []
        if cycle.primary_cycle_stage == "climax":
            conditions.append("若高开一致性过强且无承接，避免追高")
        if cycle.primary_cycle_stage == "divergence":
            conditions.append("若龙头无法回封或板块继续掉队，则取消计划")
        if leader is not None and leader.role_label not in {"龙头", "龙二", "卡位"}:
            conditions.append("若核心股未继续领涨，则放弃后排参与")
        if not conditions:
            conditions.append("若板块未能保持强势联动，则仅观察不参与")
        return conditions

    def build_watch_reason(
        self,
        mainline: ExecutionMainlineInput,
        cycle: ExecutionCycleInput,
        leader: ExecutionLeaderInput | None,
        auction_signal: ExecutionAuctionSignalInput | None = None,
    ) -> str:
        leader_text = leader.stock_name if leader else "无明确龙头"
        kline_parts: list[str] = []
        if leader and leader.position_label:
            kline_parts.append(f"K线位置 {leader.position_label}")
        if leader and leader.pattern_labels:
            kline_parts.append(f"K线形态 {'/'.join(leader.pattern_labels)}")
        kline_suffix = f"；{'；'.join(kline_parts)}" if kline_parts else ""
        base = (
            f"{mainline.theme_name} 当前 {cycle.primary_cycle_stage}，"
            f"{cycle.board_effect_status}，核心观察 {leader_text}{kline_suffix}。"
        )
        if auction_signal is not None and auction_signal.auction_signal_level:
            return (
                f"{base} 竞价确认 {auction_signal.stock_name or leader_text} "
                f"{auction_signal.auction_signal_level} / {auction_signal.signal_type or '--'}。"
            )
        return base

    def build_plan(
        self,
        source_trade_date: str,
        trade_date: str,
        mainline: ExecutionMainlineInput,
        cycle: ExecutionCycleInput,
        leader: ExecutionLeaderInput | None,
        auction_signal: ExecutionAuctionSignalInput | None = None,
    ) -> PreMarketExecutionPlan:
        theme_status = self.derive_theme_status(mainline, cycle)
        leader_status = self.derive_leader_status(cycle, leader)
        action_today = self.derive_action_today(theme_status, cycle, auction_signal)
        invalid_conditions = self.build_invalid_conditions(cycle, leader)
        if auction_signal is not None and auction_signal.hard_reject_reason:
            invalid_conditions = [auction_signal.hard_reject_reason, *invalid_conditions]
        return PreMarketExecutionPlan(
            source_trade_date=source_trade_date,
            trade_date=trade_date,
            subject_key=mainline.subject_key,
            theme_name=mainline.theme_name,
            theme_status=theme_status,
            leader_stock_id=leader.stock_id if leader else "",
            leader_stock_name=leader.stock_name if leader else "",
            leader_status=leader_status,
            action_today=action_today,
            action_bias=cycle.action_bias,
            watch_reason=self.build_watch_reason(mainline, cycle, leader, auction_signal),
            auction_focus_stock_id=auction_signal.stock_id if auction_signal else "",
            auction_focus_stock_name=auction_signal.stock_name if auction_signal else "",
            auction_signal_level=auction_signal.auction_signal_level if auction_signal else "",
            auction_signal_type=auction_signal.signal_type if auction_signal else "",
            auction_action_today=auction_signal.action_today if auction_signal else "",
            auction_signal_score=auction_signal.auction_signal_score if auction_signal else 0.0,
            auction_hard_reject_reason=auction_signal.hard_reject_reason if auction_signal else "",
            invalid_conditions=invalid_conditions,
        )

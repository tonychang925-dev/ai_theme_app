from __future__ import annotations

from dataclasses import dataclass

from stock_service.models import AuctionWatchUniverse


@dataclass(frozen=True)
class WatchMainlineInput:
    subject_key: str
    theme_name: str
    is_main_theme: bool
    theme_tier: str


@dataclass(frozen=True)
class WatchCycleInput:
    subject_key: str
    primary_cycle_stage: str
    action_bias: str


@dataclass(frozen=True)
class WatchLeaderInput:
    subject_key: str
    stock_id: str
    stock_name: str
    role_label: str
    candidate_rank: int


class AuctionWatchUniverseService:
    """
    盘前竞价候选池：
    - 只承接昨晚已确认的主线/周期/角色
    - 第一版只保留 P1 + P2 候选
    """

    def derive_candidate_priority(self, role_label: str, is_reversal_watch: bool = False) -> str:
        if role_label in {"龙头", "龙二", "卡位"}:
            return "P1"
        if role_label == "强趋势" or is_reversal_watch:
            return "P2"
        return "P3"

    def is_eligible(
        self,
        mainline: WatchMainlineInput,
        cycle: WatchCycleInput,
        leader: WatchLeaderInput,
        *,
        is_reversal_watch: bool = False,
    ) -> bool:
        priority = self.derive_candidate_priority(leader.role_label, is_reversal_watch)
        if priority == "P3":
            return False
        if mainline.is_main_theme:
            return True
        return cycle.action_bias in {"关注弱转强", "试错"}

    def build_item(
        self,
        source_trade_date: str,
        trade_date: str,
        mainline: WatchMainlineInput,
        cycle: WatchCycleInput,
        leader: WatchLeaderInput,
        *,
        is_reversal_watch: bool = False,
    ) -> AuctionWatchUniverse:
        return AuctionWatchUniverse(
            source_trade_date=source_trade_date,
            trade_date=trade_date,
            stock_id=leader.stock_id,
            stock_name=leader.stock_name,
            subject_key=mainline.subject_key,
            theme_name=mainline.theme_name,
            theme_tier=mainline.theme_tier,
            primary_cycle_stage=cycle.primary_cycle_stage,
            action_bias=cycle.action_bias,
            role_label=leader.role_label,
            candidate_rank=leader.candidate_rank,
            candidate_priority=self.derive_candidate_priority(leader.role_label, is_reversal_watch),
            is_reversal_watch=is_reversal_watch,
            source_trace={
                "mainline_subject_key": mainline.subject_key,
                "cycle_stage": cycle.primary_cycle_stage,
                "leader_rank": leader.candidate_rank,
            },
        )

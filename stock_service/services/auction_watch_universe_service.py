from __future__ import annotations

from dataclasses import dataclass

from stock_service.models import AuctionWatchUniverse


@dataclass(frozen=True)
class WatchMainlineInput:
    subject_key: str
    theme_name: str
    mainline_alive: bool
    final_cycle_state: str
    mainline_strength_score: float
    fade_watch: bool = False
    fade_confirmed: bool = False


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
        if mainline.fade_confirmed:
            return False
        if mainline.mainline_alive:
            return True
        stage = str(cycle.primary_cycle_stage or "").lower()
        if stage in {"divergence", "rebound", "repair", "分歧", "回流", "修复"} and str(cycle.action_bias or "") in {
            "关注弱转强",
            "试错",
            "可做弱转强",
            "可观察",
        }:
            return True
        return bool(is_reversal_watch and mainline.mainline_strength_score >= 60.0)

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
            theme_tier="mainline_alive" if mainline.mainline_alive else "inactive",
            mainline_alive=mainline.mainline_alive,
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

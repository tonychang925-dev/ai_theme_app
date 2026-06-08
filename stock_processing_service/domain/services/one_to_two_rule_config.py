from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


RULE_VERSION_V1_0 = "one_to_two_v1.0_post_market_plan"
RULE_VERSION_V1_1 = "one_to_two_v1.1_breadth_strong_count"
RULE_VERSION_V1_2 = "one_to_two_v1.2_turnover_tiered"
RULE_VERSION_V1_3 = "one_to_two_v1.3_breadth_turnover_combined"
RULE_VERSION_V1_4 = "one_to_two_v1.4_relaunch_first_board"
DEFAULT_RULE_VERSION = RULE_VERSION_V1_2


@dataclass(frozen=True, slots=True)
class OneToTwoRuleConfig:
    """Rule thresholds and gates for OneToTwo experiments."""

    rule_version: str = DEFAULT_RULE_VERSION
    min_focus_turnover: Decimal = Decimal("0.08")
    min_reject_turnover: Decimal = Decimal("0.08")
    min_subject_limit_count: int = 2
    min_subject_strong_count_for_breadth: int = 5
    allow_strong_count_breadth: bool = False
    strong_count_breadth_requires_confirmed_mainline: bool = True
    allowed_first_board_types: tuple[str, ...] = ("chain_first_board",)
    low_turnover_cap_decision: str = "observe_only"
    soft_breadth_cap_decision: str = "observe_only"
    low_turnover_risk_flag: str = "低换手，先观察不 focus"
    soft_breadth_risk_flag: str = "涨停合力不足但强势扩散存在"
    strict_breadth_veto_reason: str = "无板块合力"
    strict_turnover_veto_reason: str = "低换手，筹码交换不足"

    def __post_init__(self) -> None:
        if self.rule_version == RULE_VERSION_V1_0:
            raise ValueError(
                "one_to_two_v1.0_post_market_plan is blocked for backtests; use one_to_two_v1.2_turnover_tiered or later"
            )

    @classmethod
    def from_version(cls, rule_version: str | None) -> OneToTwoRuleConfig:
        version = (rule_version or DEFAULT_RULE_VERSION).strip()
        if version == RULE_VERSION_V1_1:
            return cls(
                rule_version=RULE_VERSION_V1_1,
                allowed_first_board_types=("chain_first_board",),
                allow_strong_count_breadth=True,
            )
        if version == RULE_VERSION_V1_2:
            return cls(
                rule_version=RULE_VERSION_V1_2,
                allowed_first_board_types=("chain_first_board",),
                min_focus_turnover=Decimal("0.08"),
                min_reject_turnover=Decimal("0.03"),
            )
        if version == RULE_VERSION_V1_3:
            return cls(
                rule_version=RULE_VERSION_V1_3,
                allowed_first_board_types=("chain_first_board",),
                min_focus_turnover=Decimal("0.08"),
                min_reject_turnover=Decimal("0.03"),
                allow_strong_count_breadth=True,
            )
        if version == RULE_VERSION_V1_4:
            return cls(
                rule_version=RULE_VERSION_V1_4,
                allowed_first_board_types=("chain_first_board",),
            )
        raise ValueError(f"unsupported OneToTwo rule version: {version}")

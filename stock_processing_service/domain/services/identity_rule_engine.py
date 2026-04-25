from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


def _d(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


@dataclass(frozen=True)
class IdentityRuleInput:
    subject_key: str
    subject_name: str
    # Event / continuity
    strong_event_count_7d: int
    event_count_3d: int
    event_recency_days: int
    event_strength_score: Decimal
    event_continuity_score: Decimal
    # Market / board / flow
    heat_latest: Decimal
    avg_heat_5d: Decimal
    limit_up_count: int
    limit_up_ratio_today: Decimal
    board_boom_days_5d: int
    front_row_strength_score: Decimal
    front_row_alive_ratio: Decimal
    net_inflow_sum_5d: Decimal
    net_inflow_days_5d: int
    # Kline risk context
    one_day_tour_flag: bool
    kline_support_hold: bool = False
    platform_breakout_flag: bool = False


@dataclass(frozen=True)
class IdentityRuleResult:
    logic_score: Decimal
    market_score: Decimal
    composite_score: Decimal
    rule_is_main_theme: bool
    logic_ok: bool
    market_ok: bool
    reasons: list[str] = field(default_factory=list)


class IdentityRuleEngine:
    """
    Layer A domain rule engine.
    Implements rule-side scoring + gates without any infrastructure dependency.
    """

    def evaluate(self, x: IdentityRuleInput) -> IdentityRuleResult:
        novelty_score = min(
            Decimal("100"),
            Decimal(str(x.strong_event_count_7d)) * Decimal("18")
            + x.event_strength_score * Decimal("0.35"),
        )
        timing_score = min(
            Decimal("100"),
            max(Decimal("0"), Decimal("100") - (Decimal(str(max(x.event_recency_days - 1, 0))) * Decimal("15"))),
        )
        impact_score = min(
            Decimal("100"),
            x.front_row_strength_score * Decimal("0.55")
            + Decimal(str(x.limit_up_count)) * Decimal("9")
            + x.front_row_alive_ratio * Decimal("25")
            + (Decimal("10") if x.platform_breakout_flag else Decimal("0")),
        )
        logic_score = novelty_score * Decimal("0.4") + timing_score * Decimal("0.3") + impact_score * Decimal("0.3")

        heat_score = min(Decimal("100"), x.heat_latest * Decimal("0.65") + x.avg_heat_5d * Decimal("0.35"))
        board_score = min(
            Decimal("100"),
            Decimal(str(x.limit_up_count)) * Decimal("9")
            + x.limit_up_ratio_today * Decimal("600")
            + Decimal(str(x.board_boom_days_5d)) * Decimal("15")
            + x.front_row_strength_score * Decimal("0.30"),
        )
        flow_score = min(
            Decimal("100"),
            max(Decimal("0"), x.net_inflow_sum_5d / Decimal("100000000")) * Decimal("12")
            + Decimal(str(x.net_inflow_days_5d)) * Decimal("14"),
        )
        fermentation_score = min(
            Decimal("100"),
            x.event_continuity_score * Decimal("0.7")
            + Decimal(str(x.event_count_3d)) * Decimal("8")
            + Decimal(str(x.board_boom_days_5d)) * Decimal("6"),
        )
        market_score = (
            heat_score * Decimal("0.25")
            + board_score * Decimal("0.30")
            + flow_score * Decimal("0.25")
            + fermentation_score * Decimal("0.20")
        )
        composite_score = logic_score * Decimal("0.45") + market_score * Decimal("0.55")

        logic_ok = (
            x.strong_event_count_7d >= 1
            and x.event_count_3d >= 1
            and x.event_recency_days <= 5
        )
        fermentation_ok = fermentation_score >= Decimal("45") and x.strong_event_count_7d >= 1
        fund_ok = (
            x.net_inflow_days_5d >= 2
            or x.kline_support_hold
            or x.platform_breakout_flag
        )
        market_ok = (
            (not x.one_day_tour_flag)
            and x.event_continuity_score >= Decimal("50")
            and heat_score >= Decimal("58")
            and x.limit_up_count >= 2
            and x.limit_up_ratio_today >= Decimal("0.02")
            and x.board_boom_days_5d >= 1
            and fund_ok
            and fermentation_ok
        )

        reasons: list[str] = [
            f"novelty_score={novelty_score:.2f}",
            f"timing_score={timing_score:.2f}",
            f"impact_score={impact_score:.2f}",
            f"heat_score={heat_score:.2f}",
            f"board_score={board_score:.2f}",
            f"flow_score={flow_score:.2f}",
            f"fermentation_score={fermentation_score:.2f}",
            f"logic_ok={logic_ok}",
            f"market_ok={market_ok}",
        ]
        if x.one_day_tour_flag:
            reasons.append("blocked_by_one_day_tour")
        if not fund_ok:
            reasons.append("fund_condition_failed")

        return IdentityRuleResult(
            logic_score=logic_score,
            market_score=market_score,
            composite_score=composite_score,
            rule_is_main_theme=bool(logic_ok and market_ok),
            logic_ok=bool(logic_ok),
            market_ok=bool(market_ok),
            reasons=reasons,
        )


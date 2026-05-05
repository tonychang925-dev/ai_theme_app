from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from stock_processing_service.domain.services.one_day_tour_detector import OneDayTourDetector, OneDayTourInput


def _d(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _legacy_round(value: Decimal, ndigits: int = 3) -> Decimal:
    return Decimal(str(round(float(value), ndigits)))


@dataclass(frozen=True)
class IdentityRuleInput:
    subject_key: str
    subject_name: str
    heat_latest: Decimal
    avg_heat_5d: Decimal
    hot_days_5d: int
    active_days_10d: int
    active_days_20d: int
    his_pct_chg_30d: list[Any]
    his_pct_chg_latest: Decimal
    # Event / continuity, from theme_cycle_evidence_daily.
    strong_event_count_7d: int
    event_count_3d: int
    event_count_7d: int
    event_recency_days: int
    event_strength_score: Decimal
    event_continuity_score: Decimal
    board_stock_count: int
    limit_up_count: int
    front_row_strength_score: Decimal
    front_row_alive_ratio: Decimal
    above_ma10: bool
    above_ma20: bool
    theme_support_score: Decimal
    theme_ret_10d: Decimal
    board_boom_days_5d: int
    net_inflow_sum_5d: Decimal
    net_inflow_days_5d: int


@dataclass(frozen=True)
class IdentityRuleResult:
    logic_score: Decimal
    market_score: Decimal
    composite_score: Decimal
    rule_is_main_theme: bool
    logic_ok: bool
    market_ok: bool
    one_day_tour_flag: bool
    kline_support_hold: bool
    platform_breakout_flag: bool
    platform_breakout_strength: Decimal
    mainline_continuity_score: Decimal
    one_day_tour_risk_score: Decimal
    reasons: list[str] = field(default_factory=list)


class IdentityRuleEngine:
    """
    Layer A domain rule engine.
    Implements rule-side scoring + gates without any infrastructure dependency.
    """

    def evaluate(self, x: IdentityRuleInput) -> IdentityRuleResult:
        # 1:1 复刻 stock_service/scripts/build_mainline_identity_registry.py::_decide_identity。
        heat_latest = x.heat_latest * Decimal("100") if x.heat_latest <= Decimal("1.2") else x.heat_latest
        avg_heat_5d = x.avg_heat_5d * Decimal("100") if x.avg_heat_5d <= Decimal("1.2") else x.avg_heat_5d
        limit_up_ratio_today = (
            Decimal(str(x.limit_up_count)) / Decimal(str(x.board_stock_count))
            if x.board_stock_count > 0
            else Decimal("0")
        )

        fund_continuity_score = min(
            Decimal("100"),
            max(Decimal("0"), x.net_inflow_sum_5d / Decimal("100000000")) * Decimal("10")
            + Decimal(str(x.net_inflow_days_5d)) * Decimal("14"),
        )
        board_continuity_score = min(
            Decimal("100"),
            Decimal(str(x.limit_up_count)) * Decimal("8")
            + limit_up_ratio_today * Decimal("550")
            + Decimal(str(x.board_boom_days_5d)) * Decimal("18"),
        )
        kline_continuity_score = min(
            Decimal("100"),
            (Decimal("20") if x.above_ma10 else Decimal("0"))
            + (Decimal("25") if x.above_ma20 else Decimal("0"))
            + x.theme_support_score * Decimal("0.45")
            + max(Decimal("0"), x.theme_ret_10d + Decimal("8")) * Decimal("1.8"),
        )
        mainline_continuity_score = (
            fund_continuity_score * Decimal("0.35")
            + board_continuity_score * Decimal("0.35")
            + kline_continuity_score * Decimal("0.30")
        )

        pulse_risk_score = Decimal("65") if x.active_days_20d <= 1 else (Decimal("42") if x.active_days_20d <= 2 else Decimal("12"))
        capital_drop_risk = Decimal("25") if (x.net_inflow_days_5d <= 1 and x.net_inflow_sum_5d <= 0) else Decimal("0")
        board_drop_risk = Decimal("20") if x.board_boom_days_5d == 0 else Decimal("0")
        tour_signal = OneDayTourDetector().detect(
            OneDayTourInput(
                active_days_20d=x.active_days_20d,
                board_boom_days_5d=x.board_boom_days_5d,
                net_inflow_sum_5d=x.net_inflow_sum_5d,
                net_inflow_days_5d=x.net_inflow_days_5d,
                above_ma10=x.above_ma10,
                above_ma20=x.above_ma20,
                theme_support_score=x.theme_support_score,
                theme_ret_10d=x.theme_ret_10d,
                mainline_continuity_score=mainline_continuity_score,
                his_pct_chg_30d=x.his_pct_chg_30d,
            )
        )
        kline_support_hold = tour_signal.kline_support_hold
        platform_breakout_flag = tour_signal.platform_breakout_flag
        platform_breakout_strength = tour_signal.platform_breakout_strength
        one_day_tour_risk_score = tour_signal.risk_score
        one_day_tour_flag = tour_signal.one_day_tour_flag

        novelty_score = min(Decimal("100"), Decimal(str(x.strong_event_count_7d)) * Decimal("18") + x.event_strength_score * Decimal("0.35"))
        timing_score = min(
            Decimal("100"),
            max(Decimal("0"), Decimal("100") - Decimal(str(max(x.event_recency_days - 1, 0))) * Decimal("15")),
        )
        impact_score = min(
            Decimal("100"),
            x.front_row_strength_score * Decimal("0.55")
            + Decimal(str(x.limit_up_count)) * Decimal("9")
            + x.front_row_alive_ratio * Decimal("25")
            + (Decimal("8") if platform_breakout_flag else Decimal("0"))
            + min(platform_breakout_strength * Decimal("0.12"), Decimal("8")),
        )
        logic_score = novelty_score * Decimal("0.4") + timing_score * Decimal("0.3") + impact_score * Decimal("0.3")

        heat_score = min(Decimal("100"), heat_latest * Decimal("0.65") + avg_heat_5d * Decimal("0.35"))
        board_score = min(
            Decimal("100"),
            Decimal(str(x.limit_up_count)) * Decimal("9")
            + limit_up_ratio_today * Decimal("600")
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
            + Decimal(str(x.hot_days_5d)) * Decimal("6"),
        )
        market_score = heat_score * Decimal("0.25") + board_score * Decimal("0.30") + flow_score * Decimal("0.25") + fermentation_score * Decimal("0.20")
        composite_score = logic_score * Decimal("0.45") + market_score * Decimal("0.55")

        logic_ok = bool(x.strong_event_count_7d >= 1 and x.event_count_3d >= 1 and x.event_recency_days <= 5)
        fermentation_ok = bool(
            x.event_continuity_score >= Decimal("28")
            and (x.event_count_3d >= 1 or x.hot_days_5d >= 2)
        )
        fund_ok = bool(
            (x.net_inflow_sum_5d > 0 and x.net_inflow_days_5d >= 2)
            or (
                x.net_inflow_sum_5d > 0
                and x.net_inflow_days_5d >= 1
                and kline_support_hold
                and x.active_days_10d >= 2
            )
            or (
                platform_breakout_flag
                and platform_breakout_strength >= Decimal("20")
                and x.net_inflow_sum_5d >= 0
                and x.active_days_10d >= 2
            )
        )
        market_ok = bool(
            not one_day_tour_flag
            and mainline_continuity_score >= Decimal("50")
            and heat_score >= Decimal("58")
            and x.his_pct_chg_latest >= Decimal("-1")
            and x.limit_up_count >= 2
            and limit_up_ratio_today >= Decimal("0.02")
            and x.board_boom_days_5d >= 1
            and fund_ok
            and fermentation_ok
            and x.strong_event_count_7d >= 1
        )

        reasons: list[str] = [
            f"novelty_score={novelty_score:.2f}",
            f"timing_score={timing_score:.2f}",
            f"impact_score={impact_score:.2f}",
            f"heat_score={heat_score:.2f}",
            f"board_score={board_score:.2f}",
            f"flow_score={flow_score:.2f}",
            f"fermentation_score={fermentation_score:.2f}",
            f"mainline_continuity_score={mainline_continuity_score:.2f}",
            f"one_day_tour_risk_score={one_day_tour_risk_score:.2f}",
            f"logic_ok={logic_ok}",
            f"market_ok={market_ok}",
        ]
        if one_day_tour_flag:
            reasons.append("blocked_by_one_day_tour")
        if not fund_ok:
            reasons.append("fund_condition_failed")

        return IdentityRuleResult(
            logic_score=_legacy_round(logic_score),
            market_score=_legacy_round(market_score),
            composite_score=_legacy_round(composite_score),
            rule_is_main_theme=bool(logic_ok and market_ok),
            logic_ok=bool(logic_ok),
            market_ok=bool(market_ok),
            one_day_tour_flag=one_day_tour_flag,
            kline_support_hold=kline_support_hold,
            platform_breakout_flag=platform_breakout_flag,
            platform_breakout_strength=_legacy_round(platform_breakout_strength),
            mainline_continuity_score=_legacy_round(mainline_continuity_score),
            one_day_tour_risk_score=_legacy_round(one_day_tour_risk_score),
            reasons=reasons,
        )

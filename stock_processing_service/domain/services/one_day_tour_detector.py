from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from stock_processing_service.domain.services.theme_kline_analyzer import ThemeKlineAnalyzer


@dataclass(frozen=True)
class OneDayTourInput:
    active_days_20d: int
    board_boom_days_5d: int
    net_inflow_sum_5d: Decimal
    net_inflow_days_5d: int
    above_ma10: bool
    above_ma20: bool
    theme_support_score: Decimal
    theme_ret_10d: Decimal
    mainline_continuity_score: Decimal
    his_pct_chg_30d: list[Any]


@dataclass(frozen=True)
class OneDayTourSignal:
    one_day_tour_flag: bool
    continuity_signal: str
    kline_support_hold: bool
    one_day_tour_kline_flag: bool
    platform_breakout_flag: bool
    platform_breakout_strength: Decimal
    risk_score: Decimal


class OneDayTourDetector:
    """Layer A 一日游检测。

    只复刻旧链 `build_mainline_identity_registry.py::_decide_identity`
    中的一日游风险构成，不允许使用宽度/涨幅等新链自创判定。
    """

    def __init__(self, kline_analyzer: ThemeKlineAnalyzer | None = None) -> None:
        self._kline_analyzer = kline_analyzer or ThemeKlineAnalyzer()

    def detect(self, x: OneDayTourInput) -> OneDayTourSignal:
        pulse_risk_score = Decimal("65") if x.active_days_20d <= 1 else (Decimal("42") if x.active_days_20d <= 2 else Decimal("12"))
        capital_drop_risk = Decimal("25") if (x.net_inflow_days_5d <= 1 and x.net_inflow_sum_5d <= 0) else Decimal("0")
        board_drop_risk = Decimal("20") if x.board_boom_days_5d == 0 else Decimal("0")
        ta_kline = self._kline_analyzer.analyze([float(v or 0) for v in (x.his_pct_chg_30d or [])])

        kline_break_risk = (
            Decimal("22")
            if (
                not x.above_ma10
                and not x.above_ma20
                and x.theme_support_score < Decimal("45")
                and not ta_kline.kline_support_hold
            )
            else Decimal("0")
        )
        deep_fall_risk = Decimal("12") if x.theme_ret_10d < Decimal("-8") else Decimal("0")
        risk_score = min(
            Decimal("100"),
            pulse_risk_score + capital_drop_risk + board_drop_risk + kline_break_risk + deep_fall_risk,
        )
        flag = bool(
            (risk_score >= Decimal("70") and x.mainline_continuity_score < Decimal("45"))
            or ta_kline.one_day_tour_kline_flag
        )
        return OneDayTourSignal(
            one_day_tour_flag=flag,
            continuity_signal="weak_continuity" if flag else "normal",
            kline_support_hold=bool(ta_kline.kline_support_hold),
            one_day_tour_kline_flag=bool(ta_kline.one_day_tour_kline_flag),
            platform_breakout_flag=bool(ta_kline.platform_breakout_flag),
            platform_breakout_strength=Decimal(str(ta_kline.platform_breakout_strength or 0)),
            risk_score=risk_score,
        )

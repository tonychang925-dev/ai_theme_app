"""PR4.2.24b active capital trend source contract."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from stock_processing_service.application.services.analyst_charts.chart_engine import (
    ChartReproductionEngine,
)


def test_build_trend_capital_uses_active_capital_not_market_turnover() -> None:
    """TC-ID: PR4.2.24b-capital-trend-source."""
    snapshot = SimpleNamespace(
        trade_date=date(2026, 7, 9),
        breadth=SimpleNamespace(
            up_count=2357,
            down_count=2642,
            up_ratio=0.471,
            limit_down_count=25,
        ),
        limitup=SimpleNamespace(total_count=75),
        capital=SimpleNamespace(
            total_turnover_yi=289258.22,
            active_limitup_amount_yi=2707.0,
        ),
        emotion_momentum=SimpleNamespace(momentum_raw=1.5),
        relay=SimpleNamespace(
            max_board_height=6,
            promotion_1_to_2=0.043,
            feedback_score=0.5,
            feedback_label="中性",
            continue_ratio=0.0,
        ),
    )

    trend = ChartReproductionEngine.build_trend([snapshot])

    assert trend["capital"][0]["amount"] == 2707.0
    assert trend["capital"][0]["amount"] != round(289258.22 / 10_000, 1)

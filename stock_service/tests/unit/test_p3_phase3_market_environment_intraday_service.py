from __future__ import annotations

from stock_service.services.market_environment_intraday_service import MarketEnvironmentIntradayService


def test_is_morning_high_then_fall_detects_pullback():
    service = MarketEnvironmentIntradayService()
    points = service.parse_points(
        [
            {"ts": "09:31:00", "pct_chg": 1.0},
            {"ts": "09:45:00", "pct_chg": 3.6},
            {"ts": "10:35:00", "pct_chg": 1.2},
            {"ts": "14:55:00", "pct_chg": 0.8},
        ]
    )

    assert service.is_morning_high_then_fall(points) is True


def test_is_intraday_fade_detects_early_strength_then_close_back():
    service = MarketEnvironmentIntradayService()
    points = service.parse_points(
        [
            {"ts": "09:31:00", "pct_chg": 1.8},
            {"ts": "09:52:00", "pct_chg": 3.0},
            {"ts": "14:55:00", "pct_chg": 1.1},
        ]
    )

    assert service.is_intraday_fade(points) is True


def test_parse_points_orders_by_time():
    service = MarketEnvironmentIntradayService()
    points = service.parse_points(
        [
            {"ts": "09:45:00", "pct_chg": 3.0},
            {"ts": "09:31:00", "pct_chg": 1.0},
        ]
    )

    assert [point.ts for point in points] == ["09:31:00", "09:45:00"]

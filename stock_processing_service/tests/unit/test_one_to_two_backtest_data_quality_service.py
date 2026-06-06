from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from stock_processing_service.application.services.backtest.one_to_two_backtest_data_quality_service import (
    OneToTwoBacktestDataQualityService,
)
from stock_processing_service.contracts.dto.trade_calendar_dto import TradeCalendarDTO


class _ReadPortBase:
    def __init__(self, *, missing_market_regime: bool = False, missing_watch_bars: bool = False) -> None:
        self.missing_market_regime = missing_market_regime
        self.missing_watch_bars = missing_watch_bars

    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO:
        return TradeCalendarDTO(
            trade_date=trade_date,
            calendar_is_open=True,
            prev_trade_date=trade_date - timedelta(days=1),
            next_trade_date=trade_date + timedelta(days=1),
        )

    async def get_post_market_report_context(self, trade_date: date) -> dict[str, object]:
        if self.missing_market_regime:
            return {
                "trading_principle": {"position_limit": 0.1},
                "pressure_by_stock": {},
                "ma_pattern_by_stock": {},
            }
        return {
            "market_regime": {"trade_mode": "normal", "allow_trade": True},
            "trading_principle": {"position_limit": 0.1},
            "pressure_by_stock": {},
            "ma_pattern_by_stock": {},
        }

    async def get_active_confirmed_mainlines(self, trade_date: date, limit: int = 100) -> list[dict[str, object]]:
        return [{"subject_key": "mainline_ai", "canonical_subject_key": "mainline_ai"}]

    async def get_subject_board_stats(self, trade_date: date) -> list[dict[str, object]]:
        return [{"subject_key": "mainline_ai", "limit_up_count": 1}]

    async def get_stock_daily_bars_range(
        self,
        start_date: date,
        end_date: date,
        stock_ids: list[str] | None = None,
    ) -> list[dict[str, object]]:
        return [
            {
                "trade_date": end_date.isoformat(),
                "stock_id": "600367.SH",
                "limit_up": True,
                "close_price": Decimal("10.00"),
                "limit_up_price": Decimal("10.00"),
                "pct_chg": Decimal("9.90"),
            }
        ]

    async def get_subject_stock_daily_bars_range(
        self,
        start_date: date,
        end_date: date,
        stock_ids: list[str] | None = None,
        subject_keys: list[str] | None = None,
    ) -> list[dict[str, object]]:
        return [
            {
                "trade_date": end_date.isoformat(),
                "stock_id": "600367.SH",
                "subject_key": "mainline_ai",
                "limit_up": True,
                "close_price": Decimal("10.00"),
                "limit_up_price": Decimal("10.00"),
                "pct_chg": Decimal("9.90"),
            }
        ]

    async def get_mainline_state_daily(self, trade_date: date, subject_keys: list[str]) -> list[dict[str, object]]:
        return [{"subject_key": "mainline_ai", "state": "start"}]

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[dict[str, object]]:
        if self.missing_watch_bars:
            return []
        return [
            {
                "trade_date": trade_date.isoformat(),
                "stock_id": "600367.SH",
                "close_price": Decimal("10.00"),
                "high_price": Decimal("10.00"),
                "low_price": Decimal("9.50"),
                "limit_up_price": Decimal("10.00"),
            }
        ]


@pytest.mark.asyncio
async def test_data_quality_does_not_call_setup_plan_engine() -> None:
    service = OneToTwoBacktestDataQualityService(_ReadPortBase())

    report = await service.check(date(2026, 6, 4), date(2026, 6, 4))

    assert report["blocked"] is False
    assert report["generation_quality"]["blocking"] is False
    assert report["validation_quality"]["blocking"] is False


@pytest.mark.asyncio
async def test_one_to_two_backtest_data_quality_passes_on_complete_sources() -> None:
    service = OneToTwoBacktestDataQualityService(_ReadPortBase())

    report = await service.check(date(2026, 6, 4), date(2026, 6, 4))

    assert report["blocked"] is False
    assert report["generation_quality"]["blocking"] is False
    assert report["generation_quality"]["daily_bar_coverage_ratio"] == 1.0
    assert report["validation_quality"]["blocking"] is False
    assert report["validation_quality"]["next_day_bar_coverage_ratio"] == 1.0
    assert report["validation_quality"]["missing_outcome_days"] == 0


@pytest.mark.asyncio
async def test_one_to_two_backtest_data_quality_blocks_on_missing_market_regime() -> None:
    service = OneToTwoBacktestDataQualityService(
        _ReadPortBase(missing_market_regime=True),
    )

    report = await service.check(date(2026, 6, 4), date(2026, 6, 4))

    assert report["blocked"] is True
    assert report["generation_quality"]["blocking"] is True
    assert report["blocking_errors"]


@pytest.mark.asyncio
async def test_one_to_two_backtest_data_quality_blocks_on_generation_source_exception() -> None:
    class _BrokenReadPort(_ReadPortBase):
        async def get_post_market_report_context(self, trade_date: date) -> dict[str, object]:
            raise RuntimeError("boom")

    service = OneToTwoBacktestDataQualityService(_BrokenReadPort())

    report = await service.check(date(2026, 6, 4), date(2026, 6, 4))

    assert report["blocked"] is True
    assert any("get_post_market_report_context" in err for err in report["blocking_errors"])

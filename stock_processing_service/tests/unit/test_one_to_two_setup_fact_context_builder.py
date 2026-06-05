from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.post_market_setup_fact_context_builder import (
    PostMarketSetupFactContextBuilder,
)
from stock_processing_service.contracts.dto.trade_calendar_dto import TradeCalendarDTO


class _MissingMarketContextReadPort:
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO:
        return TradeCalendarDTO(trade_date=trade_date, calendar_is_open=True, next_trade_date=trade_date)

    async def get_post_market_report_context(self, trade_date: date, subject_keys=None, stock_ids=None):
        return {}

    async def get_active_confirmed_mainlines(self, trade_date=None, limit: int = 100):
        return []

    async def get_subject_board_stats(self, trade_date):
        return []

    async def get_stock_daily_bars_range(self, start_date, end_date, stock_ids=None):
        return [{"trade_date": end_date, "stock_id": "000001.SZ", "close_price": 1, "limit_up_price": 1, "limit_up": True}]

    async def get_subject_stock_daily_bars_range(self, start_date, end_date, stock_ids=None, subject_keys=None):
        return [{"trade_date": end_date, "stock_id": "000001.SZ", "subject_key": "robot"}]

    async def get_mainline_state_daily(self, trade_date, subject_keys):
        return []


class _GuardedReadPort(_MissingMarketContextReadPort):
    async def get_strong_stock_watch_view_rows(self, *args, **kwargs):
        raise AssertionError("Layer C read-model should not be called")

    async def get_w2s_candidate_inputs(self, *args, **kwargs):
        raise AssertionError("D1 read-model should not be called")


@pytest.mark.asyncio
async def test_post_market_setup_fact_context_builder_fails_loud_when_market_context_missing() -> None:
    builder = PostMarketSetupFactContextBuilder(_MissingMarketContextReadPort())

    with pytest.raises(Exception, match="missing market_regime"):
        await builder.build(date(2026, 6, 4))


@pytest.mark.asyncio
async def test_post_market_setup_fact_context_builder_does_not_touch_layer_c_or_d1() -> None:
    class _HappyReadPort(_GuardedReadPort):
        async def get_post_market_report_context(self, trade_date: date, subject_keys=None, stock_ids=None):
            return {
                "market_regime_review": {"trade_mode": "no_trade", "allow_trade": False},
                "trading_principle": {"position_limit": 0.0},
            }

    builder = PostMarketSetupFactContextBuilder(_HappyReadPort())
    ctx = await builder.build(date(2026, 6, 4))

    assert ctx.trade_date == "2026-06-04"
    assert ctx.watch_date == "2026-06-04"
    assert ctx.market_regime["trade_mode"] == "no_trade"

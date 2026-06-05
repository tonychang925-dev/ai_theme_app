from __future__ import annotations

from datetime import date
from typing import Any

import pytest

from stock_processing_service import api_app


class _GatewayFake:
    async def get_trade_calendar(self, trade_date: date):
        return {"trade_date": trade_date, "calendar_is_open": True, "next_trade_date": date(2026, 6, 5)}

    async def get_post_market_report_context(self, trade_date: date, subject_keys=None, stock_ids=None):
        return {
            "market_regime_review": {
                "allow_trade": False,
                "trade_mode": "no_trade",
                "position_limit": 0,
                "no_trade_blocking_rule": "unit-test",
                "no_trade_reasons": ["market_closed"],
            },
            "trading_principle": {"summary": "unit-test"},
            "strong_hotspot_subjects": [],
            "pressure_by_stock": {},
            "ma_pattern_by_stock": {},
        }

    async def get_active_confirmed_mainlines(self, trade_date=None, limit: int = 100):
        return []

    async def get_subject_board_stats(self, trade_date):
        return []

    async def get_stock_daily_bars_range(self, start_date, end_date, stock_ids=None):
        return []

    async def get_subject_stock_daily_bars_range(self, start_date, end_date, stock_ids=None, subject_keys=None):
        return []

    async def get_mainline_state_daily(self, trade_date, subject_keys):
        return []

    async def get_strong_stock_watch_view_rows(self, *args, **kwargs):
        raise AssertionError("OneToTwo must not read Layer C strong watch view rows")

    async def get_w2s_candidate_inputs(self, *args, **kwargs):
        raise AssertionError("OneToTwo must not read D1 candidate inputs")


@pytest.mark.asyncio
async def test_daily_review_v2_watchlists_one_to_two_empty_state_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _GatewayFake()
    monkeypatch.setattr(api_app.app.state, "gateway", fake, raising=False)

    watchlists = await api_app._build_one_to_two_watchlists(date(2026, 6, 4))
    block = watchlists["one_to_two"]

    assert block["summary"]["focus_count"] == 0
    assert block["summary"]["empty_is_valid"] is True
    assert block["items"] == []
    assert block["diagnostics"]["empty_is_valid"] is True

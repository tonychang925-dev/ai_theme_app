from __future__ import annotations

from datetime import date
from typing import Any

import pytest
from fastapi import HTTPException

from stock_processing_service import api_app


class _GatewayFake:
    async def get_trade_calendar(self, trade_date: date):
        return {"trade_date": trade_date, "calendar_is_open": True, "next_trade_date": date(2026, 6, 5)}

    async def get_post_market_setup_plan_rows(self, trade_date: date, setup_type: str = "one_to_two"):
        return [
            {
                "trade_date": trade_date,
                "watch_date": date(2026, 6, 5),
                "setup_type": "one_to_two",
                "stock_id": "__SUMMARY__",
                "subject_key": "__SUMMARY__",
                "summary": {
                    "focus_count": 0,
                    "observe_only_count": 2,
                    "pending_review_only_count": 1,
                    "reject_count": 18,
                    "empty_is_valid": True,
                },
                "diagnostics": {"empty_is_valid": True},
            }
        ]

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
async def test_daily_review_v2_watchlists_one_to_two_propagates_read_error(monkeypatch: pytest.MonkeyPatch) -> None:
    class _BrokenGateway(_GatewayFake):
        async def get_post_market_setup_plan_rows(self, trade_date: date, setup_type: str = "one_to_two"):
            raise RuntimeError("db offline")

    fake = _BrokenGateway()
    monkeypatch.setattr(api_app.app.state, "read_port", fake, raising=False)

    with pytest.raises(RuntimeError, match="db offline"):
        await api_app._build_one_to_two_watchlists(date(2026, 6, 4))


@pytest.mark.asyncio
async def test_daily_review_v2_watchlists_one_to_two_rejects_missing_summary_row(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MissingSummaryGateway(_GatewayFake):
        async def get_post_market_setup_plan_rows(self, trade_date: date, setup_type: str = "one_to_two"):
            return [
                {
                    "trade_date": trade_date,
                    "watch_date": date(2026, 6, 5),
                    "setup_type": "one_to_two",
                    "stock_id": "000001.SZ",
                    "subject_key": "sk_001",
                    "decision": "observe_only",
                }
            ]

    fake = _MissingSummaryGateway()
    monkeypatch.setattr(api_app.app.state, "read_port", fake, raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await api_app._build_one_to_two_watchlists(date(2026, 6, 4))

    assert exc_info.value.status_code == 424
    assert exc_info.value.detail["error_code"] == "SETUP_PLAN_SUMMARY_MISSING"


@pytest.mark.asyncio
async def test_daily_review_v2_watchlists_one_to_two_rejects_empty_summary_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class _EmptySummaryGateway(_GatewayFake):
        async def get_post_market_setup_plan_rows(self, trade_date: date, setup_type: str = "one_to_two"):
            rows = await super().get_post_market_setup_plan_rows(trade_date, setup_type)
            rows[0]["summary"] = {}
            return rows

    fake = _EmptySummaryGateway()
    monkeypatch.setattr(api_app.app.state, "read_port", fake, raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await api_app._build_one_to_two_watchlists(date(2026, 6, 4))

    assert exc_info.value.status_code == 424
    assert exc_info.value.detail["error_code"] == "SETUP_PLAN_PAYLOAD_INVALID"


@pytest.mark.asyncio
async def test_daily_review_v2_watchlists_one_to_two_rejects_invalid_diagnostics_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class _InvalidDiagnosticsGateway(_GatewayFake):
        async def get_post_market_setup_plan_rows(self, trade_date: date, setup_type: str = "one_to_two"):
            rows = await super().get_post_market_setup_plan_rows(trade_date, setup_type)
            rows[0]["diagnostics"] = ["bad", "diagnostics"]
            return rows

    fake = _InvalidDiagnosticsGateway()
    monkeypatch.setattr(api_app.app.state, "read_port", fake, raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await api_app._build_one_to_two_watchlists(date(2026, 6, 4))

    assert exc_info.value.status_code == 424
    assert exc_info.value.detail["error_code"] == "SETUP_PLAN_PAYLOAD_INVALID"


@pytest.mark.asyncio
async def test_daily_review_v2_watchlists_one_to_two_rejects_invalid_summary_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class _InvalidSummaryGateway(_GatewayFake):
        async def get_post_market_setup_plan_rows(self, trade_date: date, setup_type: str = "one_to_two"):
            rows = await super().get_post_market_setup_plan_rows(trade_date, setup_type)
            rows[0]["summary"] = ["bad", "summary"]
            return rows

    fake = _InvalidSummaryGateway()
    monkeypatch.setattr(api_app.app.state, "read_port", fake, raising=False)

    with pytest.raises(HTTPException) as exc_info:
        await api_app._build_one_to_two_watchlists(date(2026, 6, 4))

    assert exc_info.value.status_code == 424
    assert exc_info.value.detail["error_code"] == "SETUP_PLAN_PAYLOAD_INVALID"


@pytest.mark.asyncio
async def test_daily_review_v2_watchlists_one_to_two_empty_state_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _GatewayFake()
    monkeypatch.setattr(api_app.app.state, "read_port", fake, raising=False)

    watchlists = await api_app._build_one_to_two_watchlists(date(2026, 6, 4))
    block = watchlists["one_to_two"]

    assert block["summary"]["focus_count"] == 0
    assert block["summary"]["empty_is_valid"] is True
    assert block["items"] == []
    assert block["diagnostics"]["empty_is_valid"] is True

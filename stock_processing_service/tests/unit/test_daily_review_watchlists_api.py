from __future__ import annotations

import pytest
from fastapi import HTTPException

from stock_processing_service import api_app


@pytest.mark.asyncio
async def test_daily_review_watchlists_api_returns_one_to_two_block(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_watchlists(trade_date):
        return {
            "one_to_two": {
                "summary": {
                    "focus_count": 0,
                    "observe_only_count": 2,
                    "pending_review_only_count": 1,
                    "reject_count": 18,
                    "empty_is_valid": True,
                },
                "items": [],
                "diagnostics": {"empty_is_valid": True},
            }
        }

    monkeypatch.setattr(api_app, "_build_one_to_two_watchlists", _fake_watchlists)

    payload = await api_app.get_daily_review_watchlists("2026-06-04", setup_type="one_to_two")

    assert payload["trade_date"] == "2026-06-04"
    assert payload["setup_type"] == "one_to_two"
    assert payload["summary"]["observe_only_count"] == 2
    assert payload["diagnostics"]["empty_is_valid"] is True


@pytest.mark.asyncio
async def test_daily_review_watchlists_api_rejects_unsupported_setup_type() -> None:
    with pytest.raises(HTTPException):
        await api_app.get_daily_review_watchlists("2026-06-04", setup_type="weak_to_strong")

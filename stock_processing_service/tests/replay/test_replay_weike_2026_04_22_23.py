from __future__ import annotations

import os
from datetime import date

import pytest

from stock_processing_service.tests.replay._post_market_replay_runner import run_post_market_replay


@pytest.mark.asyncio
@pytest.mark.replay
async def test_replay_weike_2026_04_22() -> None:
    if os.getenv("REPLAY_LIVE_DB", "0") != "1":
        pytest.skip("live DB replay disabled; set REPLAY_LIVE_DB=1 on dedicated DB")

    result = await run_post_market_replay(trade_date=date(2026, 4, 22), sample_name="weike")
    assert result.daily_status == "ok"
    assert result.recap_status == "ok"
    assert result.assertion_report.get("passed") is True, result.assertion_report


@pytest.mark.asyncio
@pytest.mark.replay
async def test_replay_weike_2026_04_23() -> None:
    if os.getenv("REPLAY_LIVE_DB", "0") != "1":
        pytest.skip("live DB replay disabled; set REPLAY_LIVE_DB=1 on dedicated DB")

    result = await run_post_market_replay(trade_date=date(2026, 4, 23), sample_name="weike")
    assert result.daily_status == "ok"
    assert result.recap_status == "ok"
    assert result.assertion_report.get("passed") is True, result.assertion_report

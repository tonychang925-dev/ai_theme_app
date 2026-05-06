from __future__ import annotations

import os
from datetime import date

import pytest

from stock_processing_service.tests.replay._post_market_replay_runner import (
    run_post_market_replay,
    run_post_market_replay_readonly,
)


@pytest.mark.asyncio
@pytest.mark.replay
async def test_replay_liande_2026_04_15() -> None:
    if os.getenv("REPLAY_LIVE_DB", "0") == "1":
        result = await run_post_market_replay(trade_date=date(2026, 4, 15), sample_name="liande")

        assert result.daily_status == "ok"
        assert result.daily_affected_rows > 0
        assert result.recap_status == "ok"
        assert result.assertion_report.get("passed") is True, result.assertion_report
        layer_results = result.assertion_report.get("layer_results") or {}
        assert layer_results["layer_d.present_in_observe_candidates"]["actual"] is True
        assert layer_results["layer_d.candidate_level"]["actual"] == "observe_only"

        diag = result.target_diagnostics.get("605060.SH") or {}
        refresh = diag.get("refresh") or {}
        assert "transition_type" in refresh
        assert "transition_confidence" in refresh
        assert "trigger_flags" in refresh
        return

    result = run_post_market_replay_readonly(date(2026, 4, 15), target_stock_id="605060.SH")
    assert result.trade_date == date(2026, 4, 15)
    assert result.candidate_count == 0
    assert result.candidate_count_total == 10
    assert result.strong_watch_input_7d_count == 41
    assert result.has_target_in_input_7d is True
    assert result.has_target_in_top_candidates is False
    assert result.target_preview.get("stock_id") == "605060.SH"
    assert result.target_preview.get("watch_score") == "30.00"

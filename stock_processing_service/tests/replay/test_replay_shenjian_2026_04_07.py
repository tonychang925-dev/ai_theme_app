from __future__ import annotations

import os
from datetime import date

import pytest

from stock_processing_service.tests.replay._post_market_replay_runner import (
    replay_enabled,
    run_post_market_replay,
    run_post_market_replay_readonly,
)


@pytest.mark.asyncio
@pytest.mark.replay
async def test_replay_shenjian_2026_04_07() -> None:
    if os.getenv("REPLAY_LIVE_DB", "0") == "1":
        result = await run_post_market_replay(trade_date=date(2026, 4, 7), sample_name="shenjian")

        assert result.daily_status == "ok"
        assert result.daily_affected_rows > 0
        assert result.recap_status == "ok"

        recap_doc = result.recap_doc
        top_candidates = recap_doc.get("top_candidates", [])
        candidate_count = int(recap_doc.get("candidate_count") or 0)
        assert top_candidates, (
            "2026-04-07 top_candidates empty: "
            f"{recap_doc}, diagnostics={result.target_diagnostics.get('002361.SZ')}"
        )

        hit = any(c.get("stock_id") == "002361.SZ" or c.get("stock_name") == "神剑股份" for c in top_candidates)
        assert hit, (
            "神剑股份未命中盘后候选: "
            f"{top_candidates}, diagnostics={result.target_diagnostics.get('002361.SZ')}"
        )

        assert candidate_count <= 10, f"candidate_count too large: {candidate_count}"

        target = next(
            c for c in top_candidates if c.get("stock_id") == "002361.SZ" or c.get("stock_name") == "神剑股份"
        )
        assert target.get("candidate_level") not in {"reject", "REJECT"}
        assert target.get("candidate_score") not in (None, "", "0", 0)
        assert target.get("subject_key")
        assert target.get("subject_name")
        assert "transition_type" in target
        assert "transition_confidence" in target
        assert "trigger_flags" in target
        assert target.get("evidence_rules"), f"missing evidence_rules: {target}"

        diag = result.target_diagnostics.get("002361.SZ") or {}
        refresh = diag.get("refresh") or {}
        assert "transition_type" in refresh
        assert "transition_confidence" in refresh
        assert "trigger_flags" in refresh
        return

    result = run_post_market_replay_readonly(date(2026, 4, 7))
    assert result.trade_date == date(2026, 4, 7)
    assert result.candidate_count == 0
    assert result.candidate_count_total == 2
    assert result.strong_watch_input_7d_count == 10
    assert result.has_target_in_input_7d is True
    assert result.has_target_in_top_candidates is False
    assert result.target_preview.get("stock_id") == "002361.SZ"
    assert result.target_preview.get("watch_score") == "58.00"

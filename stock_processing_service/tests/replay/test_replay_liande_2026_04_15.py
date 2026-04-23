from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.tests.replay._post_market_replay_runner import (
    replay_enabled,
    run_post_market_replay,
)


@pytest.mark.asyncio
@pytest.mark.replay
@pytest.mark.replay_db
async def test_replay_liande_2026_04_15() -> None:
    if not replay_enabled():
        pytest.skip("real replay disabled; set RUN_REPLAY_DB=1 on dedicated DB")

    result = await run_post_market_replay(trade_date=date(2026, 4, 15), sample_name="liande")

    assert result.daily_status == "ok"
    assert result.daily_affected_rows > 0
    assert result.recap_status == "ok"

    recap_doc = result.recap_doc
    top_candidates = recap_doc.get("top_candidates", [])
    candidate_count = int(recap_doc.get("candidate_count") or 0)
    assert top_candidates, (
        "2026-04-15 top_candidates empty: "
        f"{recap_doc}, diagnostics={result.target_diagnostics.get('605060.SH')}"
    )

    hit = any(c.get("stock_id") == "605060.SH" or c.get("stock_name") == "联德股份" for c in top_candidates)
    assert hit, (
        "联德股份未命中盘后候选: "
        f"{top_candidates}, diagnostics={result.target_diagnostics.get('605060.SH')}"
    )

    assert candidate_count <= 10, f"candidate_count too large: {candidate_count}"

    target = next(
        c for c in top_candidates if c.get("stock_id") == "605060.SH" or c.get("stock_name") == "联德股份"
    )
    assert target.get("candidate_level") not in {"reject", "REJECT"}
    assert target.get("candidate_score") not in (None, "", "0", 0)
    assert target.get("subject_key")
    assert target.get("subject_name")
    assert target.get("evidence_rules"), f"missing evidence_rules: {target}"

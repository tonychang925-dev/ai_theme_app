from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.tests.replay._post_market_replay_runner import (
    replay_enabled,
    run_pre_market_replay,
)


@pytest.mark.asyncio
@pytest.mark.replay
@pytest.mark.replay_db
async def test_replay_pre_market_liande_2026_04_16() -> None:
    if not replay_enabled():
        pytest.skip("real replay disabled; set RUN_REPLAY_DB=1 on dedicated DB")

    result = await run_pre_market_replay(trade_date=date(2026, 4, 16), sample_name="liande")
    assert result.pre_market_status == "ok"

    brief_doc = result.brief_doc
    picks = brief_doc.get("picks", [])
    assert isinstance(picks, list), f"invalid picks payload: {brief_doc}"
    assert picks, (
        "2026-04-16 pre-market picks empty: "
        f"{brief_doc}, diagnostics={result.target_diagnostics.get('605060.SH')}"
    )

    hit = any(p.get("stock_id") == "605060.SH" for p in picks)
    assert hit, f"联德股份未命中盘前 picks: {picks}"

    target = next(p for p in picks if p.get("stock_id") == "605060.SH")
    assert target.get("confirm_score") not in (None, "", "0", 0)
    assert "approved" in target
    assert target.get("evidence_rules"), f"missing evidence_rules: {target}"

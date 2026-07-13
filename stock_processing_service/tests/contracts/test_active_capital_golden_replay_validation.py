"""PR4.2.29 active capital replay validation contract."""

from __future__ import annotations

from pathlib import Path


DOC = Path("docs/architecture/Active_Capital_Golden_Replay_Validation.md")


def test_active_capital_replay_validation_document_exists() -> None:
    """TC-ID: PR4.2.29-active-capital-replay-validation-doc."""
    assert DOC.exists()


def test_active_capital_validation_keeps_production_and_analyst_truth_separate() -> None:
    """TC-ID: PR4.2.29-active-capital-production-vs-analyst-truth."""
    content = DOC.read_text(encoding="utf-8")

    assert "value_yi: 2664.84" in content
    assert "method: board_pool_zt_zb_v1" in content
    assert "quality: PARTIAL" in content
    assert "confidence: 0.85" in content
    assert "source: eastmoney_board_pool_daily.amount" in content
    assert "board_pool.yzt.amount_yi" in content
    assert "capital.active_amount expected 2707, got 2664.84" in content
    assert "Do not hardcode `2707` into production" in content
    assert "Do not hardcode `2707` into production and do not restore the" in content
    assert "old `5058.28` fixed-factor path" in content

"""Unit tests for MarketCognitionReplay.run_pair() (historical cognitive backtest).

Tests pair building, Time Travel Rule enforcement, and BacktestPendingRecord
structure. Uses existing MarketCognitionReplay infrastructure — no new framework.
"""

from __future__ import annotations

import pytest

from stock_processing_service.application.services.market_cognition.replay import (
    BacktestPendingRecord,
    MarketCognitionReplay,
    build_pairs,
)


def _snapshot(trade_date: str) -> dict:
    return {
        "trade_date": trade_date,
        "payload": {
            "schema_version": "post_market_recap.v2",
            "engine_summary": {
                "allow_trade": False,
                "trade_mode": "no_trade",
                "blocking_rule": "short_term_sentiment_dead",
            },
            "market_regime_review": {
                "short_term_sentiment": "dead",
                "mainline_environment": "mainline_tradable",
            },
            "mainline_states": [{"theme_name": "mock_theme"}],
            "post_market_setup_plan": {
                "summary": {
                    "trade_date": trade_date,
                    "watch_date": "2026-07-06",
                }
            },
        },
    }


# ── TC-M8P1-HBT-01: Pair building ──

def test_build_pairs_consecutive_days() -> None:
    snapshots = [_snapshot(d) for d in ("2026-07-01", "2026-07-02", "2026-07-03")]
    pairs = build_pairs(snapshots)
    assert len(pairs) == 2
    assert pairs[0][0]["trade_date"] == "2026-07-01"
    assert pairs[0][1]["trade_date"] == "2026-07-02"


def test_build_pairs_single_snapshot_returns_empty() -> None:
    assert build_pairs([_snapshot("2026-07-01")]) == []


def test_build_pairs_duplicate_dates_skipped() -> None:
    snapshots = [_snapshot("2026-07-01"), _snapshot("2026-07-01"), _snapshot("2026-07-02")]
    pairs = build_pairs(snapshots)
    assert all(str(p[0]["trade_date"]) != str(p[1]["trade_date"]) for p in pairs)


# ── TC-M8P1-HBT-02: Time Travel Rule ──

def test_run_pair_hypothesis_only_from_day_d() -> None:
    """Verify that run_pair() reads Hypothesis from day D and Reality from D+1."""
    day_d = _snapshot("2026-07-01")
    day_d_next = _snapshot("2026-07-02")
    record = MarketCognitionReplay.run_pair(day_d, day_d_next)
    assert record is not None
    assert record.thesis_trade_date == "2026-07-01"
    assert record.verification_trade_date == "2026-07-02"


def test_run_pair_validation_mode_is_historical() -> None:
    record = MarketCognitionReplay.run_pair(
        _snapshot("2026-07-01"), _snapshot("2026-07-02")
    )
    assert record is not None
    assert record.validation_mode == "historical"


# ── TC-M8P1-HBT-03: Record structure ──

def test_record_has_required_fields() -> None:
    record = MarketCognitionReplay.run_pair(
        _snapshot("2026-07-01"), _snapshot("2026-07-02")
    )
    assert record is not None
    assert record.record_id.startswith("hbt:")
    assert record.hypothesis_id
    assert record.hypothesis_statement
    assert 0 <= record.prediction_probability <= 1
    assert record.prediction_probability == 0.35  # from FixedCognitionPolicy for no_trade


def test_record_is_immutable() -> None:
    record = MarketCognitionReplay.run_pair(
        _snapshot("2026-07-01"), _snapshot("2026-07-02")
    )
    assert record is not None
    with pytest.raises(Exception):
        record.prediction_probability = 0.99  # type: ignore[misc]


def test_record_hashes_are_present() -> None:
    record = MarketCognitionReplay.run_pair(
        _snapshot("2026-07-01"), _snapshot("2026-07-02")
    )
    assert record is not None
    assert len(record.source_knowledge_hash) > 0
    assert len(record.source_evidence_hash) > 0
    assert len(record.source_context_hash) > 0
    assert len(record.source_thesis_hash) > 0

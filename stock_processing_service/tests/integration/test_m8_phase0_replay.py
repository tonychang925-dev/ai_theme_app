from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta

try:
    from stock_processing_service.application.services.market_cognition.replay import (
        MarketCognitionReplay,
    )
except ModuleNotFoundError:
    MarketCognitionReplay = None


def _historical_payload(trade_date: str, theme: str = "机器人") -> dict:
    return {
        "recap_doc": {
            "schema_version": "post_market_recap.v2",
            "trade_date": trade_date,
            "engine_summary": {
                "allow_trade": False,
                "trade_mode": "no_trade",
                "blocking_rule": "short_term_sentiment_dead",
            },
            "market_regime_review": {
                "broad_market_regime": "downtrend_rebound",
                "short_term_sentiment": "dead",
                "mainline_environment": "mainline_tradable",
            },
            "mainline_states": [
                {"theme_name": theme, "lifecycle": "divergence", "strong_stock_count": 4}
            ],
        }
    }


# TC-M8P0-T03-01
def test_same_snapshot_when_replayed_twice_then_all_layer_hashes_and_decision_are_stable() -> None:
    assert MarketCognitionReplay is not None, "replay implementation is missing"
    payload = _historical_payload("2026-07-03")
    before = deepcopy(payload)

    first = MarketCognitionReplay.run(payload, "2026-07-03")
    second = MarketCognitionReplay.run(payload, "2026-07-03")

    assert first.status == "ready"
    assert first.layer_hashes == second.layer_hashes
    assert first.decision_unchanged is True
    assert payload == before
    assert first.thesis is not None
    assert first.thesis.unsupported_claim_count == 0


# TC-M8P0-T03-02
def test_empty_snapshot_when_replayed_then_failure_is_structured_and_has_no_thesis() -> None:
    assert MarketCognitionReplay is not None, "replay implementation is missing"
    result = MarketCognitionReplay.run({}, "2026-07-03")

    assert result.status == "failed"
    assert result.failed_stage == "knowledge"
    assert result.thesis is None
    assert result.diagnostics


# TC-M8P0-T05-01
def test_seven_historical_days_when_replayed_then_quality_gate_has_no_unsupported_claims() -> None:
    assert MarketCognitionReplay is not None, "replay implementation is missing"
    start = date(2026, 6, 25)
    payloads = [
        _historical_payload((start + timedelta(days=index)).isoformat(), theme=f"题材{index}")
        for index in range(7)
    ]

    results = [
        MarketCognitionReplay.run(payload, payload["recap_doc"]["trade_date"])
        for payload in payloads
    ]

    assert len(results) == 7
    assert all(item.status == "ready" for item in results)
    assert all(item.decision_unchanged for item in results)
    assert all(item.thesis and item.thesis.unsupported_claim_count == 0 for item in results)
    assert len({item.layer_hashes["thesis"] for item in results}) == 7

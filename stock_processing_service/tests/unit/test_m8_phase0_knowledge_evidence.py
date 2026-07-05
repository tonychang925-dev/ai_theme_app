from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

try:
    from stock_processing_service.application.services.market_cognition.knowledge_evidence import (
        MarketEvidenceAdapter,
        MarketKnowledgeBundleBuilder,
    )
except ModuleNotFoundError:
    MarketEvidenceAdapter = None
    MarketKnowledgeBundleBuilder = None


def _recap_payload() -> dict:
    return {
        "schema_version": "post_market_recap.v2",
        "engine_summary": {
            "allow_trade": False,
            "trade_mode": "no_trade",
            "blocking_rule": "short_term_sentiment_dead",
            "position_limit": 0,
        },
        "market_regime_review": {
            "broad_market_regime": "downtrend_rebound",
            "short_term_sentiment": "dead",
            "mainline_environment": "mainline_tradable",
        },
        "mainline_states": [
            {
                "theme_name": "机器人",
                "lifecycle": "divergence",
                "strong_stock_count": 4,
            }
        ],
        "theme_reviews": [{"theme_name": "机器人", "market_score": 72}],
    }


# TC-M8P0-T01-01
def test_same_knowledge_input_when_built_twice_then_hash_is_stable_and_input_unchanged() -> None:
    assert MarketKnowledgeBundleBuilder is not None, "knowledge bundle implementation is missing"
    payload = _recap_payload()
    before = deepcopy(payload)
    as_of = datetime(2026, 7, 3, 15, 30, tzinfo=timezone.utc)

    first = MarketKnowledgeBundleBuilder.build(payload, "2026-07-03", as_of=as_of)
    second = MarketKnowledgeBundleBuilder.build(payload, "2026-07-03", as_of=as_of)

    assert first.content_hash == second.content_hash
    assert first.bundle_id == second.bundle_id
    assert first.module_coverage
    assert first.producer_versions
    assert payload == before


# TC-M8P0-T01-02
def test_missing_capital_when_adapted_then_missing_is_explicit_and_not_zero_evidence() -> None:
    assert MarketKnowledgeBundleBuilder is not None, "knowledge bundle implementation is missing"
    assert MarketEvidenceAdapter is not None, "evidence adapter implementation is missing"
    bundle = MarketKnowledgeBundleBuilder.build(
        _recap_payload(),
        "2026-07-03",
        as_of=datetime(2026, 7, 3, 15, 30, tzinfo=timezone.utc),
    )

    snapshot = MarketEvidenceAdapter.build(bundle)

    decision = snapshot.get("decision.allow_trade")
    assert decision is not None
    assert decision.value is False
    assert decision.ref.source_module == "engine_summary"
    assert snapshot.evidence_ref_coverage == 1.0
    assert snapshot.coverage_for("seat_money_summary").status == "missing"
    assert snapshot.get("capital.net_inflow") is None
    assert snapshot.quality.status in {"partial", "ready"}


# TC-M8P0-T01-02
def test_empty_payload_when_building_bundle_then_contract_error_is_raised() -> None:
    assert MarketKnowledgeBundleBuilder is not None, "knowledge bundle implementation is missing"
    try:
        MarketKnowledgeBundleBuilder.build({}, "2026-07-03")
    except ValueError as exc:
        assert "empty" in str(exc).lower() or "payload" in str(exc).lower()
    else:
        raise AssertionError("empty payload must fail instead of creating synthetic knowledge")


# TC-M8P0-T01-02
def test_daily_review_v2_nested_shape_when_adapted_then_real_producer_paths_are_preserved() -> None:
    assert MarketKnowledgeBundleBuilder is not None, "knowledge bundle implementation is missing"
    assert MarketEvidenceAdapter is not None, "evidence adapter implementation is missing"
    payload = {
        "recap_doc": {
            "daily_review_v2": {
                "schema_version": "daily_review_v2",
                "engine_summary": {
                    "allow_trade": False,
                    "trade_mode": "no_trade",
                    "no_trade_blocking_rule": "short_term_sentiment_dead",
                },
                "market_regime_review": {
                    "broad_market_regime": "downtrend_rebound",
                    "short_term_sentiment": "dead",
                    "mainline_environment": "mainline_tradable",
                },
                "mainline_daily_states": [
                    {
                        "mainline_name": "机器人",
                        "lifecycle_state": "divergence",
                        "strong_pool_count": 4,
                    }
                ],
            }
        }
    }

    bundle = MarketKnowledgeBundleBuilder.build(payload, "2026-07-03")
    snapshot = MarketEvidenceAdapter.build(bundle)

    assert snapshot.get("decision.allow_trade").value is False
    assert snapshot.get("decision.blocking_rule").value == "short_term_sentiment_dead"
    assert snapshot.get("mainline.0.name").value == "机器人"

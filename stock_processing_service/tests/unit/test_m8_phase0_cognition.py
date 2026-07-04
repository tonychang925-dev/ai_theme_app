from __future__ import annotations

from datetime import datetime, timezone

try:
    from stock_processing_service.application.services.market_cognition.cognition import (
        Phase0CognitionPipeline,
    )
    from stock_processing_service.application.services.market_cognition.knowledge_evidence import (
        MarketEvidenceAdapter,
        MarketKnowledgeBundleBuilder,
    )
except ModuleNotFoundError:
    Phase0CognitionPipeline = None
    MarketEvidenceAdapter = None
    MarketKnowledgeBundleBuilder = None


def _evidence(payload: dict):
    assert MarketKnowledgeBundleBuilder is not None, "knowledge implementation is missing"
    assert MarketEvidenceAdapter is not None, "evidence implementation is missing"
    bundle = MarketKnowledgeBundleBuilder.build(
        payload,
        "2026-07-03",
        as_of=datetime(2026, 7, 3, 15, 30, tzinfo=timezone.utc),
    )
    return MarketEvidenceAdapter.build(bundle)


# TC-M8P0-T02-01
def test_no_trade_evidence_when_cognition_runs_then_thesis_is_explainable_and_falsifiable() -> None:
    assert Phase0CognitionPipeline is not None, "cognition implementation is missing"
    evidence = _evidence(
        {
            "schema_version": "post_market_recap.v2",
            "engine_summary": {
                "allow_trade": False,
                "trade_mode": "no_trade",
                "blocking_rule": "short_term_sentiment_dead",
                "next_day_strategy": "不做新开仓，只观察主线是否修复",
            },
            "market_regime_review": {
                "broad_market_regime": "downtrend_rebound",
                "short_term_sentiment": "dead",
                "mainline_environment": "mainline_tradable",
            },
            "mainline_states": [
                {"theme_name": "机器人", "lifecycle": "divergence", "strong_stock_count": 4}
            ],
            "post_market_setup_plan": {
                "summary": {
                    "trade_date": "2026-07-03",
                    "watch_date": "2026-07-06",
                }
            },
        }
    )

    result = Phase0CognitionPipeline.build(evidence)

    assert result.context.context_type == "CLOSE"
    assert result.thesis.status == "ready"
    assert result.thesis.primary_thesis is not None
    assert result.thesis.primary_thesis.evidence_refs
    assert result.thesis.evidence_ref_coverage == 1.0
    assert result.cognition.hypotheses
    assert all(item.deadline for item in result.cognition.hypotheses)
    assert result.cognition.hypotheses[0].deadline == "2026-07-06"
    assert all(item.falsifiers for item in result.cognition.hypotheses)
    assert "no_trade" not in result.thesis.primary_thesis.statement
    assert "short_term_sentiment_dead" not in result.thesis.primary_thesis.statement


# TC-M8P0-T02-01
def test_no_trade_without_next_trading_day_when_cognition_runs_then_hypothesis_is_not_invented() -> None:
    assert Phase0CognitionPipeline is not None, "cognition implementation is missing"
    evidence = _evidence(
        {
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
            "mainline_states": [{"theme_name": "机器人"}],
        }
    )

    result = Phase0CognitionPipeline.build(evidence)

    assert evidence.get("calendar.next_trade_date") is None
    assert result.cognition.hypotheses == ()


# TC-M8P0-T02-02
def test_insufficient_evidence_when_cognition_runs_then_no_supported_thesis_is_invented() -> None:
    assert Phase0CognitionPipeline is not None, "cognition implementation is missing"
    evidence = _evidence({"schema_version": "post_market_recap.v2"})

    result = Phase0CognitionPipeline.build(evidence)

    assert result.thesis.status == "unavailable"
    assert result.thesis.primary_thesis is None
    assert result.thesis.unsupported_claim_count == 0
    assert "insufficient_evidence" in result.diagnostics

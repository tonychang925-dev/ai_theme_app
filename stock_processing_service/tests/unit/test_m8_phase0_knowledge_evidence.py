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
def test_same_knowledge_input_when_built_twice_then_hash_is_stable_and_input_unchanged() -> (
    None
):
    assert (
        MarketKnowledgeBundleBuilder is not None
    ), "knowledge bundle implementation is missing"
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
def test_missing_capital_when_adapted_then_missing_is_explicit_and_not_zero_evidence() -> (
    None
):
    assert (
        MarketKnowledgeBundleBuilder is not None
    ), "knowledge bundle implementation is missing"
    assert (
        MarketEvidenceAdapter is not None
    ), "evidence adapter implementation is missing"
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
    assert (
        MarketKnowledgeBundleBuilder is not None
    ), "knowledge bundle implementation is missing"
    try:
        MarketKnowledgeBundleBuilder.build({}, "2026-07-03")
    except ValueError as exc:
        assert "empty" in str(exc).lower() or "payload" in str(exc).lower()
    else:
        raise AssertionError(
            "empty payload must fail instead of creating derived knowledge"
        )


# TC-M8P0-T01-02
def test_daily_review_v2_nested_shape_when_adapted_then_real_producer_paths_are_preserved() -> (
    None
):
    assert (
        MarketKnowledgeBundleBuilder is not None
    ), "knowledge bundle implementation is missing"
    assert (
        MarketEvidenceAdapter is not None
    ), "evidence adapter implementation is missing"
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


def test_next_day_evidence_projects_existing_watchlist_and_setup_fields_only() -> None:
    assert (
        MarketKnowledgeBundleBuilder is not None
    ), "knowledge bundle implementation is missing"
    assert (
        MarketEvidenceAdapter is not None
    ), "evidence adapter implementation is missing"
    payload = {
        "post_market_setup_plan": {
            "summary": {"watch_date": "2026-07-10"},
            "items": [
                {
                    "stock_name": "长电科技",
                    "summary": "首板事实入池，明日观察晋级确认。",
                    "technical_summary": {"reason": "ma_not_bullish_alignment"},
                }
            ],
        },
        "watchlists": {
            "one_to_two": {
                "items": [
                    {
                        "stock_id": "600584.SH",
                        "stock_name": "长电科技",
                        "subject_key": "9015778",
                        "summary": "首板事实入池，明日观察晋级确认。",
                        "watch_date": "2026-07-10",
                        "decision": "observe_only",
                        "setup_type": "one_to_two",
                        "reason": None,
                    }
                ]
            }
        },
    }
    before = deepcopy(payload)

    bundle = MarketKnowledgeBundleBuilder.build(payload, "2026-07-09")
    first = MarketEvidenceAdapter.build(bundle)
    second = MarketEvidenceAdapter.build(bundle)

    assert first.get("calendar.next_trade_date").value == "2026-07-10"
    expected = {
        "watchlist.0.stock_id": "600584.SH",
        "watchlist.0.stock_name": "长电科技",
        "watchlist.0.subject_key": "9015778",
        "watchlist.0.summary": "首板事实入池，明日观察晋级确认。",
        "watchlist.0.watch_date": "2026-07-10",
        "watchlist.0.decision": "observe_only",
        "watchlist.0.setup_type": "one_to_two",
        "setup.0.summary": "首板事实入池，明日观察晋级确认。",
        "setup.0.technical_reason": "ma_not_bullish_alignment",
    }
    for key, value in expected.items():
        item = first.get(key)
        assert item is not None
        assert item.value == value
        assert item.ref.source_snapshot_id == bundle.bundle_id
        assert item.observed_at == bundle.as_of

    assert first.get("watchlist.0.reason") is None
    assert first.get("setup.0.focus") is None
    assert first.get("setup.0.reason") is None
    assert first.get("setup.0.rationale") is None
    assert first.get("setup.0.technical_focus") is None
    assert first.content_hash == second.content_hash
    assert payload == before

    watchlist_item = first.get("watchlist.0.stock_name")
    setup_item = first.get("setup.0.technical_reason")
    assert watchlist_item.ref.source_module == "watchlists"
    assert watchlist_item.ref.source_path == "one_to_two.items.0.stock_name"
    assert setup_item.ref.source_module == "post_market_setup_plan"
    assert setup_item.ref.source_path == "items.0.technical_summary.reason"


def test_next_day_missing_producer_fields_stay_absent_without_defaults() -> None:
    assert (
        MarketKnowledgeBundleBuilder is not None
    ), "knowledge bundle implementation is missing"
    assert (
        MarketEvidenceAdapter is not None
    ), "evidence adapter implementation is missing"
    bundle = MarketKnowledgeBundleBuilder.build(
        {
            "watchlists": {
                "one_to_two": {
                    "items": [{"stock_name": "", "reason": None, "subject_key": ""}]
                }
            },
            "post_market_setup_plan": {
                "items": [{"summary": "", "focus": None, "technical_summary": {}}]
            },
        },
        "2026-07-09",
    )

    snapshot = MarketEvidenceAdapter.build(bundle)

    assert snapshot.get("watchlist.0.stock_name") is None
    assert snapshot.get("watchlist.0.reason") is None
    assert snapshot.get("watchlist.0.subject_key") is None
    assert snapshot.get("setup.0.summary") is None
    assert snapshot.get("setup.0.focus") is None
    assert snapshot.get("setup.0.technical_reason") is None

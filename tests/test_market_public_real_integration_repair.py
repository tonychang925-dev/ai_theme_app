from __future__ import annotations

import os

import pytest

from market_public import (
    EventReadRequest,
    EventResolveRequest,
    MarketAnalysisReadRequest,
    MarketDataState,
    MarketOperationStatus,
    MarketPublicFactory,
    MarketStateReadRequest,
)


pytestmark = pytest.mark.skipif(
    os.getenv("MARKET_REAL_DB", "0") != "1",
    reason="set MARKET_REAL_DB=1 only for the configured real Market database",
)


@pytest.mark.asyncio
async def test_real_state_read_binds_exact_date_and_returns_empty_without_row():
    provider = MarketPublicFactory.create()
    try:
        result = await provider.execute(
            "market.state.read",
            MarketStateReadRequest(trade_date="2026-07-10"),
            request_id="repair-state-empty",
            correlation_id="repair-state-empty-correlation",
        )
    finally:
        await provider.close()

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.EMPTY
    assert result.payload is None
    assert result.failures == ()


@pytest.mark.asyncio
async def test_real_frozen_state_read_projects_wrapped_recap_review():
    provider = MarketPublicFactory.create()
    try:
        result = await provider.execute(
            "market.state.read",
            MarketStateReadRequest(trade_date="2026-05-15"),
            request_id="repair-state-frozen",
            correlation_id="repair-state-frozen-correlation",
        )
    finally:
        await provider.close()

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.payload["trade_date"] == "2026-05-15"
    assert result.payload["source"] == (
        "post_market_recap_snapshot.payload.recap_doc.market_overview_review"
    )
    assert isinstance(result.payload["snapshot_version"], str)
    assert result.payload["snapshot_version"]
    assert result.failures == ()


@pytest.mark.asyncio
async def test_real_analysis_read_returns_existing_evidence_and_exact_empty():
    provider = MarketPublicFactory.create()
    try:
        ready = await provider.execute(
            "market.analysis.read",
            MarketAnalysisReadRequest(trade_date="2026-05-15"),
            request_id="repair-analysis-ready",
            correlation_id="repair-analysis-ready-correlation",
        )
        empty = await provider.execute(
            "market.analysis.read",
            MarketAnalysisReadRequest(trade_date="2026-07-10"),
            request_id="repair-analysis-empty",
            correlation_id="repair-analysis-empty-correlation",
        )
    finally:
        await provider.close()

    assert ready.operation_status is MarketOperationStatus.SUCCESS
    assert ready.data_state is MarketDataState.READY
    assert ready.payload["trade_date"] == "2026-05-15"
    assert ready.payload["source"]["snapshot_ref"] == "post_market_recap_snapshot"
    assert ready.payload["source"]["snapshot_version"]
    assert ready.payload["source_bundle_id"]
    assert ready.payload["evidence_snapshot_id"]
    assert ready.payload["evidence"]
    assert ready.payload["quality"]["status"] == "partial"
    assert ready.payload["quality"]["missing_modules"]
    assert ready.payload["review_maturity"]["available"] is False
    assert ready.provenance.source_refs
    assert ready.provenance.evidence_refs
    assert ready.failures == ()

    assert empty.operation_status is MarketOperationStatus.SUCCESS
    assert empty.data_state is MarketDataState.EMPTY
    assert empty.payload is None
    assert empty.failures == ()


@pytest.mark.asyncio
async def test_real_analysis_read_projects_next_day_watchlist_evidence():
    provider = MarketPublicFactory.create()
    try:
        result = await provider.execute(
            "market.analysis.read",
            MarketAnalysisReadRequest(trade_date="2026-07-09"),
            request_id="repair-analysis-watchlist",
            correlation_id="repair-analysis-watchlist-correlation",
        )
    finally:
        await provider.close()

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    evidence = {item["key"]: item for item in result.payload["evidence"]}
    assert evidence["calendar.next_trade_date"]["value"] == "2026-07-10"
    assert evidence["watchlist.0.stock_id"]["value"] == "600584.SH"
    assert evidence["watchlist.0.stock_name"]["value"] == "长电科技"
    assert evidence["watchlist.0.subject_key"]["value"] == "9015778"
    assert evidence["watchlist.0.watch_date"]["value"] == "2026-07-10"
    assert evidence["watchlist.0.decision"]["value"] == "observe_only"
    assert evidence["watchlist.0.setup_type"]["value"] == "one_to_two"
    assert evidence["watchlist.0.summary"]["ref"]["source_path"] == (
        "one_to_two.items.0.summary"
    )
    assert evidence["setup.0.summary"]["ref"]["source_path"] == ("items.0.summary")
    assert evidence["setup.0.technical_reason"]["ref"]["source_path"] == (
        "items.0.technical_summary.reason"
    )
    assert "setup.0.focus" not in evidence
    assert "setup.0.reason" not in evidence
    assert "setup.0.rationale" not in evidence


@pytest.mark.asyncio
async def test_real_resolve_read_roundtrip_preserves_both_source_namespaces():
    provider = MarketPublicFactory.create()
    try:
        jyhf_resolve = await provider.execute(
            "market.event.resolve",
            EventResolveRequest(feed_date="2026-05-19", limit=200),
            request_id="repair-jyhf-resolve",
            correlation_id="repair-jyhf-roundtrip",
        )
        assert jyhf_resolve.operation_status is MarketOperationStatus.SUCCESS
        assert jyhf_resolve.data_state is MarketDataState.READY
        jyhf_item_id = next(
            item["item_id"]
            for item in jyhf_resolve.payload
            if item["item_id"].startswith("event:jyhf_cdp:")
        )
        jyhf_read = await provider.execute(
            "market.event.read",
            EventReadRequest(item_id=jyhf_item_id),
            request_id="repair-jyhf-read",
            correlation_id="repair-jyhf-roundtrip",
        )
        assert jyhf_read.operation_status is MarketOperationStatus.SUCCESS
        assert jyhf_read.data_state is MarketDataState.READY
        assert jyhf_read.payload["item_id"] == jyhf_item_id

        news_resolve = await provider.execute(
            "market.event.resolve",
            EventResolveRequest(feed_date="2026-04-30", limit=200),
            request_id="repair-news-resolve",
            correlation_id="repair-news-roundtrip",
        )
        assert news_resolve.operation_status is MarketOperationStatus.SUCCESS
        assert news_resolve.data_state is MarketDataState.READY
        news_item_id = next(
            item["item_id"]
            for item in news_resolve.payload
            if not item["item_id"].startswith("event:jyhf_cdp:")
        )
        news_read = await provider.execute(
            "market.event.read",
            EventReadRequest(item_id=news_item_id),
            request_id="repair-news-read",
            correlation_id="repair-news-roundtrip",
        )
        assert news_read.operation_status is MarketOperationStatus.SUCCESS
        assert news_read.data_state is MarketDataState.READY
        assert news_read.payload["item_id"] == news_item_id
    finally:
        await provider.close()

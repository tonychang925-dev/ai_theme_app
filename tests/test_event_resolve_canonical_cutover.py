from datetime import date

import pytest

from market_public import (
    EventResolveRequest,
    MarketAcceptanceStatus,
    MarketDataState,
    MarketFailureKind,
    MarketOperationStatus,
)
from market_public.private.event_acceptance import (
    EventAcceptancePolicy,
    OperationalWindow,
)
from market_public.provider import _MarketPublicProvider


class CanonicalEventFeed:
    def __init__(self, items, acceptance_status):
        self.items = items
        self.acceptance_status = acceptance_status


def _item(event_id: int, source: str, *, raw: bool = True, trace: bool = True):
    return {
        "item_id": f"event:{event_id}:subject:{event_id}",
        "item_type": "event",
        "event_id": event_id,
        "subject_key": f"subject:{event_id}",
        "theme_subject_keys": [f"subject:{event_id}"],
        "source_category": source,
        "source_channel": source,
        "source_trace_id": f"trace:{event_id}" if trace else None,
        "news_raw_id": event_id if raw else None,
        "jyhf_provenance": source == "jyhf_dom",
        "jyhf_ingest_at": "2026-09-30T08:00:00+00:00"
        if source == "jyhf_dom"
        else None,
    }


class CanonicalFixtureRepository:
    def __init__(self, feeds):
        self.feeds = feeds
        self.canonical_calls = []
        self.legacy_calls = []

    async def fetch_canonical_intel_feed(self, **kwargs):
        self.canonical_calls.append(kwargs)
        return self.feeds[kwargs.get("feed_date")]

    async def fetch_intel_feed(self, **kwargs):
        self.legacy_calls.append(kwargs)
        return [_item(999, "news")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("trade_date", "status", "count"),
    [
        ("2026-07-19", MarketAcceptanceStatus.ACCEPTED, 13),
        ("2026-09-24", MarketAcceptanceStatus.CASE_INELIGIBLE, 0),
        ("2026-09-26", MarketAcceptanceStatus.CASE_INELIGIBLE, 0),
        ("2026-09-30", MarketAcceptanceStatus.ACCEPTED, 27),
        ("2026-10-02", MarketAcceptanceStatus.ACCEPTED, 26),
    ],
)
async def test_frozen_source_aware_acceptance_fixtures(trade_date, status, count):
    source = "jyhf_dom" if trade_date == "2026-09-30" else "news"
    feed = CanonicalEventFeed(
        [_item(index, source) for index in range(1, count + 1)], status
    )
    repo = CanonicalFixtureRepository({trade_date: feed})

    result = await _MarketPublicProvider(repo).execute(
        "market.event.resolve", EventResolveRequest(feed_date=trade_date)
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.acceptance_status is status
    assert result.data_state is (
        MarketDataState.NOT_APPLICABLE
        if status is MarketAcceptanceStatus.CASE_INELIGIBLE
        else MarketDataState.READY
    )
    assert len(result.payload) == count
    assert repo.legacy_calls == []


@pytest.mark.asyncio
async def test_canonical_empty_never_falls_back_to_legacy_rows():
    repo = CanonicalFixtureRepository(
        {"2026-10-02": CanonicalEventFeed([], MarketAcceptanceStatus.EMPTY)}
    )

    result = await _MarketPublicProvider(repo).execute(
        "market.event.resolve", EventResolveRequest(feed_date="2026-10-02")
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.EMPTY
    assert result.acceptance_status is MarketAcceptanceStatus.EMPTY
    assert result.payload == []
    assert repo.legacy_calls == []


@pytest.mark.asyncio
async def test_broken_provenance_is_present_unverified_not_accepted():
    repo = CanonicalFixtureRepository(
        {
            "2026-10-02": CanonicalEventFeed(
                [_item(1, "news", raw=False)],
                MarketAcceptanceStatus.PRESENT_UNVERIFIED,
            )
        }
    )

    result = await _MarketPublicProvider(repo).execute(
        "market.event.resolve", EventResolveRequest(feed_date="2026-10-02")
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.PENDING
    assert result.acceptance_status is MarketAcceptanceStatus.PRESENT_UNVERIFIED


def test_acceptance_policy_distinguishes_missing_identity_from_missing_provenance():
    policy = EventAcceptancePolicy()
    assert policy.classify_row({"event_id": 1}) == "INVALID"
    assert (
        policy.classify_row(_item(1, "news", raw=False)).value
        == "PRESENT_UNVERIFIED"
    )
    assert (
        policy.classify_row(_item(1, "news")).value
        == "ACCEPTED"
    )


def test_operational_windows_make_pause_case_ineligible_without_inference():
    policy = EventAcceptancePolicy(
        (
            OperationalWindow(end=date(2026, 7, 19)),
            OperationalWindow(start=date(2026, 9, 30)),
        )
    )
    assert policy.classify(date(2026, 9, 24), []) is MarketAcceptanceStatus.CASE_INELIGIBLE
    assert policy.classify(date(2026, 9, 30), [_item(1, "jyhf_dom")]) is MarketAcceptanceStatus.ACCEPTED


def test_canonical_factory_adapter_exposes_only_the_new_reader_for_real_repository():
    from market_public.factory import MarketPublicFactory

    provider = MarketPublicFactory.create(database_url="postgresql://example.invalid/market")
    assert hasattr(provider._repository, "fetch_canonical_intel_feed")

from datetime import date
import json

import pytest

from market_public.private.market_state import (
    MARKET_STATE_SOURCE,
    MarketStateReader,
    MarketStateRequest,
    MarketStateResult,
    MarketStateStatus,
)


class RepositoryFixture:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error
        self.calls = []

    async def get_existing_post_market_recap_snapshot(self, trade_date):
        self.calls.append(trade_date)
        if self.error is not None:
            raise self.error
        return self.row


def overview(**overrides):
    values = {
        "up_count": 2400,
        "down_count": 1600,
        "limit_up_total": 37,
        "limit_down_total": 8,
        "total_amount": 16543210000,
    }
    values.update(overrides)
    return values


def repository_row(**overrides):
    row = {
        "trade_date": date(2026, 9, 18),
        "snapshot_version": "post_market_recap.v2",
        "batch_id": "batch-1",
        "trace_id": "trace-1",
        "payload": {"market_overview_review": overview()},
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_valid_snapshot_projects_exact_required_breadth_facts():
    repository = RepositoryFixture(repository_row())

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.READY
    assert result.snapshot.trade_date == "2026-09-18"
    assert result.snapshot.breadth.up_count == 2400
    assert result.snapshot.breadth.down_count == 1600
    assert result.snapshot.breadth.up_ratio == 0.6
    assert result.snapshot.breadth.limit_up_count == 37
    assert result.snapshot.breadth.limit_down_count == 8
    assert result.snapshot.breadth.turnover_yi == 1654321.0
    assert result.snapshot.source == MARKET_STATE_SOURCE == "recap_snapshot"
    assert repository.calls == ["2026-09-18"]


@pytest.mark.asyncio
async def test_total_amount_wan_is_deterministically_normalized_to_yi():
    repository = RepositoryFixture(
        repository_row(payload={"market_overview_review": overview(total_amount=12345)})
    )

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.snapshot.breadth.turnover_yi == 1.23


@pytest.mark.asyncio
async def test_json_payload_transport_preserves_source_values():
    payload = {"market_overview_review": overview(up_count=12, down_count=8)}
    repository = RepositoryFixture(repository_row(payload=json.dumps(payload)))

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.READY
    assert (
        result.snapshot.breadth.up_count,
        result.snapshot.breadth.down_count,
    ) == (12, 8)


@pytest.mark.parametrize(
    "trade_date",
    [None, 20260918, "", "latest", "2026-9-18", "09/18/2026"],
)
@pytest.mark.asyncio
async def test_trade_date_is_required_and_canonical_before_repository(trade_date):
    repository = RepositoryFixture()

    result = await MarketStateReader(repository).read(MarketStateRequest(trade_date))

    assert result.status is MarketStateStatus.INVALID_REQUEST
    assert result.snapshot is None
    assert result.failure.code == "invalid_request"
    assert repository.calls == []


@pytest.mark.asyncio
async def test_missing_snapshot_returns_typed_empty_without_date_substitution():
    repository = RepositoryFixture(None)

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.EMPTY
    assert result.snapshot is None
    assert result.failure.code == "snapshot_not_found"
    assert repository.calls == ["2026-09-18"]


@pytest.mark.parametrize(
    "payload",
    [None, {}, {"other": {}}, {"market_overview_review": None},
     {"market_overview_review": []}, "{invalid"],
)
@pytest.mark.asyncio
async def test_missing_or_malformed_payload_is_data_integrity_failure(payload):
    repository = RepositoryFixture(repository_row(payload=payload))

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.DATA_INTEGRITY_FAILURE
    assert result.failure.code == "market_overview_review_invalid"
    assert result.snapshot is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("up_count", None),
        ("up_count", "2400"),
        ("down_count", None),
        ("down_count", True),
        ("limit_up_total", None),
        ("limit_up_total", 1.5),
        ("limit_down_total", None),
        ("limit_down_total", "8"),
        ("total_amount", None),
        ("total_amount", "16543210000"),
    ],
)
@pytest.mark.asyncio
async def test_missing_or_malformed_required_field_fails_closed(field, value):
    source = overview(**{field: value})
    repository = RepositoryFixture(
        repository_row(payload={"market_overview_review": source})
    )

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.DATA_INTEGRITY_FAILURE
    assert result.failure.code == "market_overview_review_invalid"
    assert field in result.failure.message
    assert result.snapshot is None


@pytest.mark.asyncio
async def test_explicit_source_zero_is_preserved_as_zero():
    source = overview(
        up_count=0,
        down_count=0,
        limit_up_total=0,
        limit_down_total=0,
        total_amount=0,
    )
    repository = RepositoryFixture(
        repository_row(payload={"market_overview_review": source})
    )

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.READY
    assert result.snapshot.breadth.up_count == 0
    assert result.snapshot.breadth.down_count == 0
    assert result.snapshot.breadth.limit_up_count == 0
    assert result.snapshot.breadth.limit_down_count == 0
    assert result.snapshot.breadth.turnover_yi == 0.0


@pytest.mark.asyncio
async def test_mismatched_trade_date_is_data_integrity_failure():
    repository = RepositoryFixture(repository_row(trade_date=date(2026, 9, 17)))

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.DATA_INTEGRITY_FAILURE
    assert result.snapshot is None
    assert repository.calls == ["2026-09-18"]


@pytest.mark.asyncio
async def test_connectivity_failure_is_distinct_from_internal_failure():
    connectivity = RepositoryFixture(error=ConnectionError("database unavailable"))
    postgres_connectivity = RepositoryFixture(
        error=type("PostgresConnectionError", (Exception,), {})("connect failed")
    )
    protocol = RepositoryFixture(error=TypeError("repository contract invalid"))

    connectivity_result = await MarketStateReader(connectivity).read(
        MarketStateRequest("2026-09-18")
    )
    postgres_result = await MarketStateReader(postgres_connectivity).read(
        MarketStateRequest("2026-09-18")
    )
    protocol_result = await MarketStateReader(protocol).read(
        MarketStateRequest("2026-09-18")
    )

    assert connectivity_result.status is MarketStateStatus.DEPENDENCY_UNAVAILABLE
    assert connectivity_result.failure.code == "repository_unavailable"
    assert postgres_result.status is MarketStateStatus.DEPENDENCY_UNAVAILABLE
    assert protocol_result.status is MarketStateStatus.INTERNAL_FAILURE
    assert protocol_result.failure.code == "repository_protocol_failed"


def test_result_default_shape_is_empty_not_synthetic_success():
    result = MarketStateResult(MarketStateStatus.EMPTY)

    assert result.snapshot is None
    assert result.failure is None


def test_private_reader_uses_only_authoritative_source_path():
    from pathlib import Path

    source = Path("market_public/private/market_state.py").read_text()
    assert "get_existing_post_market_recap_snapshot" in source
    assert 'payload.get("market_overview_review")' in source
    assert "total_amount_wan / 10_000" in source
    for forbidden in (
        "TDX",
        "MarketMetricsService",
        "board_pool",
        "board-pool",
        "get_latest_post_market_recap_trade_date",
        "POSTGRES_",
        "postgresql://",
    ):
        assert forbidden not in source

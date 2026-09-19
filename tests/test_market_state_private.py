from datetime import date
import json

import pytest

from market_public.private.market_state import (
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


def repository_row(**overrides):
    row = {
        "trade_date": date(2026, 9, 18),
        "snapshot_version": "post_market_recap.v2",
        "batch_id": "batch-1",
        "trace_id": "trace-1",
        "payload": {
            "market_overview_review": {
                "up_count": 2318,
                "down_count": 2317,
                "total_amount": 1654321000000,
            }
        },
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_returns_exact_market_overview_review_payload():
    repository = RepositoryFixture(repository_row())

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.READY
    assert result.snapshot.trade_date == "2026-09-18"
    assert result.snapshot.market_overview_review == {
        "up_count": 2318,
        "down_count": 2317,
        "total_amount": 1654321000000,
    }
    assert repository.calls == ["2026-09-18"]


@pytest.mark.asyncio
async def test_accepts_json_payload_transport_without_rewriting_values():
    payload = {"market_overview_review": {"up_count": 12, "down_count": 8}}
    repository = RepositoryFixture(repository_row(payload=json.dumps(payload)))

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.READY
    assert result.snapshot.market_overview_review == {"up_count": 12, "down_count": 8}


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
async def test_missing_explicit_snapshot_is_not_found_without_date_substitution():
    repository = RepositoryFixture(None)

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.NOT_FOUND
    assert result.snapshot is None
    assert repository.calls == ["2026-09-18"]


@pytest.mark.asyncio
async def test_mismatched_trade_date_is_contract_mismatch():
    repository = RepositoryFixture(repository_row(trade_date=date(2026, 9, 17)))

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.CONTRACT_MISMATCH
    assert result.snapshot is None
    assert repository.calls == ["2026-09-18"]


@pytest.mark.asyncio
async def test_missing_market_overview_review_fails_closed_without_projection():
    repository = RepositoryFixture(repository_row(payload={"other": {}}))

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.CONTRACT_MISMATCH
    assert result.failure.code == "market_overview_review_missing"
    assert result.snapshot is None


@pytest.mark.asyncio
async def test_repository_failure_is_typed_unavailable():
    repository = RepositoryFixture(error=ConnectionError("database unavailable"))

    result = await MarketStateReader(repository).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.DEPENDENCY_UNAVAILABLE
    assert result.snapshot is None
    assert result.failure.code == "repository_unavailable"


@pytest.mark.asyncio
async def test_projection_exception_is_internal_failure_not_ready():
    class InvalidPayloadRepository(RepositoryFixture):
        async def get_existing_post_market_recap_snapshot(self, trade_date):
            self.calls.append(trade_date)
            return {"trade_date": date(2026, 9, 18), "payload": "{invalid"}

    result = await MarketStateReader(InvalidPayloadRepository()).read(
        MarketStateRequest("2026-09-18")
    )

    assert result.status is MarketStateStatus.INTERNAL_FAILURE
    assert result.snapshot is None


def test_result_default_shape_is_explicitly_empty_not_synthetic():
    result = MarketStateResult(MarketStateStatus.NOT_FOUND)

    assert result.snapshot is None
    assert result.failure is None


def test_private_reader_uses_only_persisted_market_overview_source():
    from pathlib import Path

    source = Path("market_public/private/market_state.py").read_text()
    assert "get_existing_post_market_recap_snapshot" in source
    assert 'payload.get("market_overview_review")' in source
    for forbidden in (
        "TDX",
        "MarketMetricsService",
        "board_pool",
        "board-pool",
        "get_latest_post_market_recap_trade_date",
    ):
        assert forbidden not in source

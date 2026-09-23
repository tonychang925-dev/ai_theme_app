from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from market_public.contracts import (
    CAPABILITIES,
    MARKET_PUBLIC_CONTRACT_VERSION,
    MarketDataState,
    MarketFailureKind,
    MarketOperationStatus,
    StockQuoteReadRequest,
)
from market_public.factory import MarketPublicFactory
from market_public.private.phase1_market_state_repository import (
    Phase1MarketStateReadRepository,
)
from market_public.provider import _MarketPublicProvider


class QuoteRepository:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error
        self.calls = []

    async def get_stock_daily_quote(self, stock_id, trade_date):
        self.calls.append((stock_id, trade_date))
        if self.error is not None:
            raise self.error
        return self.row


class FakeRepositoryConnection:
    def __init__(self, row):
        self.row = row
        self.queries = []

    async def fetchrow(self, sql, *args):
        self.queries.append((sql, args))
        return self.row


class FakeRepositoryPool:
    def __init__(self, row):
        self.connection = FakeRepositoryConnection(row)

    def acquire(self):
        return self

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return None


def quote_row(**overrides):
    row = {
        "trade_date": "2026-07-31",
        "stock_id": "600519.SH",
        "stock_name": "",
        "open_price": "1420.00",
        "high_price": "1430.00",
        "low_price": "1410.00",
        "close_price": "1425.00",
        "pre_close": "1418.00",
        "pct_chg": "0.49",
        "volume": "2500000",
        "amount": "3550000000",
        "source_name": "tushare",
    }
    row.update(overrides)
    return row


def test_stock_quote_contract_is_exact_public_read_capability():
    assert MARKET_PUBLIC_CONTRACT_VERSION == "0.4.0"
    assert "market.stock.quote.read" in CAPABILITIES
    assert set(StockQuoteReadRequest.__annotations__) == {"stock_id", "trade_date"}


@pytest.mark.asyncio
async def test_exact_stock_and_date_reach_repository_and_return_ready_envelope():
    repository = QuoteRepository(quote_row())

    result = await _MarketPublicProvider(repository).execute(
        "market.stock.quote.read",
        StockQuoteReadRequest(stock_id="600519.SH", trade_date="2026-07-31"),
        request_id="request-1",
        correlation_id="correlation-1",
    )

    assert repository.calls == [("600519.SH", "2026-07-31")]
    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.payload == quote_row()
    assert result.provenance.source_refs == ("tushare",)
    assert result.provenance.public_object_refs == ("600519.SH",)


@pytest.mark.asyncio
async def test_no_exact_row_is_success_empty_without_latest_discovery():
    repository = QuoteRepository(None)

    result = await _MarketPublicProvider(repository).execute(
        "market.stock.quote.read",
        StockQuoteReadRequest(stock_id="600519.SH", trade_date="2026-07-31"),
    )

    assert repository.calls == [("600519.SH", "2026-07-31")]
    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.EMPTY
    assert result.payload is None


@pytest.mark.asyncio
async def test_invalid_request_and_date_fail_as_contract_mismatch():
    repository = QuoteRepository(quote_row())
    requests = (
        None,
        StockQuoteReadRequest(stock_id="600519.SH", trade_date=""),
        StockQuoteReadRequest(stock_id="600519.SH", trade_date="not-a-date"),
        StockQuoteReadRequest(stock_id="600519.SH", trade_date="0000-01-01"),
        StockQuoteReadRequest(stock_id="", trade_date="2026-07-31"),
        StockQuoteReadRequest(stock_id="600519.SH", trade_date="2026-7-31"),
        StockQuoteReadRequest(stock_id="600519.SH", trade_date="2026/07/31"),
        StockQuoteReadRequest(stock_id="600519.SH", trade_date="2026-02-30"),
        StockQuoteReadRequest(stock_id="600519.SH", trade_date="２０２６-07-31"),
    )

    for request in requests:
        result = await _MarketPublicProvider(repository).execute(
            "market.stock.quote.read",
            request,
        )
        assert result.operation_status is MarketOperationStatus.FAILURE
        assert result.data_state is MarketDataState.NOT_APPLICABLE
        assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH

    assert repository.calls == []


@pytest.mark.asyncio
async def test_dependency_and_internal_failures_remain_typed():
    dependency = QuoteRepository(error=ConnectionError("database unavailable"))
    internal = QuoteRepository(error=RuntimeError("query defect"))
    request = StockQuoteReadRequest(stock_id="600519.SH", trade_date="2026-07-31")

    dependency_result = await _MarketPublicProvider(dependency).execute(
        "market.stock.quote.read", request
    )
    internal_result = await _MarketPublicProvider(internal).execute(
        "market.stock.quote.read", request
    )

    assert dependency_result.data_state is MarketDataState.UNAVAILABLE
    assert dependency_result.failures[0].kind is MarketFailureKind.UNAVAILABLE
    assert internal_result.data_state is MarketDataState.UNAVAILABLE
    assert internal_result.failures[0].kind is MarketFailureKind.INTERNAL_FAILURE


@pytest.mark.asyncio
async def test_repository_quote_read_is_exact_date_and_stock_without_fallback():
    repository = Phase1MarketStateReadRepository(
        database_url="postgresql://example.invalid/market"
    )
    pool = FakeRepositoryPool(
        {
            "trade_date": date(2026, 7, 31),
            "stock_id": "600519.SH",
            "stock_name": "",
            "open_price": Decimal("1420.00"),
            "high_price": Decimal("1430.00"),
            "low_price": Decimal("1410.00"),
            "close_price": Decimal("1425.00"),
            "pre_close": Decimal("1418.00"),
            "pct_chg": Decimal("0.49"),
            "volume": Decimal("2500000"),
            "amount": Decimal("3550000000"),
            "source_name": "tushare",
        }
    )
    repository._pool = pool

    result = await repository.get_stock_daily_quote("600519.SH", "2026-07-31")

    assert result == quote_row()
    sql, args = pool.connection.queries[0]
    assert args == (date(2026, 7, 31), "600519.SH")
    assert "FROM stock_daily_snapshot" in sql
    assert "trade_date = $1::date" in sql
    assert "stock_id = $2::text" in sql
    assert "source_name ILIKE 'tushare%'" in sql
    assert "source_name ILIKE 'tushare'" in sql
    assert "source_name LIKE" not in sql
    assert "LIMIT 1" in sql
    assert "MAX(" not in sql


@pytest.mark.asyncio
async def test_authoritative_source_case_variants_use_consistent_truth_gate():
    for source_name in ("tushare", "Tushare", "TUSHARE", "Tushare-Daily"):
        repository = Phase1MarketStateReadRepository(
            database_url="postgresql://example.invalid/market"
        )
        pool = FakeRepositoryPool(
            {
                "trade_date": date(2026, 7, 31),
                "stock_id": "600519.SH",
                "stock_name": "",
                "open_price": Decimal("1330.0300"),
                "high_price": Decimal("1355.7200"),
                "low_price": Decimal("1325.7700"),
                "close_price": Decimal("1350.6000"),
                "pre_close": Decimal("1361.7600"),
                "pct_chg": Decimal("-0.8195"),
                "volume": Decimal("55127.5200"),
                "amount": Decimal("7373462.6050"),
                "source_name": source_name,
            }
        )
        repository._pool = pool

        result = await repository.get_stock_daily_quote("600519.SH", "2026-07-31")

        assert result["source_name"] == source_name
        sql, _ = pool.connection.queries[0]
        assert "source_name ILIKE 'tushare%'" in sql
        assert "source_name ILIKE 'tushare'" in sql


@pytest.mark.asyncio
async def test_lazy_factory_delegates_exact_quote_read():
    lazy_repository = MarketPublicFactory.create(
        database_url="postgresql://example.invalid/market"
    )._repository
    bound = QuoteRepository(quote_row())
    lazy_repository._repository = bound

    result = await lazy_repository.get_stock_daily_quote("600519.SH", "2026-07-31")

    assert result == quote_row()
    assert bound.calls == [("600519.SH", "2026-07-31")]

from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.post_market_readiness_service import (
    PostMarketReadinessService,
)


class _FakeConn:
    def __init__(self, counts: dict[str, int]) -> None:
        self._counts = counts

    async def fetchrow(self, sql: str, trade_date: date):
        for table_name, count in self._counts.items():
            if f"FROM {table_name}" in sql:
                return {"cnt": count}
        return {"cnt": 0}


class _AcquireCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakePool:
    def __init__(self, counts: dict[str, int]) -> None:
        self._conn = _FakeConn(counts)

    def acquire(self) -> _AcquireCtx:
        return _AcquireCtx(self._conn)


@pytest.mark.asyncio
async def test_readiness_requires_index_quote_snapshot() -> None:
    """TC-POSTMARKET-INDEX: reports must not be generated with empty index performance."""

    service = PostMarketReadinessService(
        pool=_FakePool(
            {
                "subject_stock_daily_snapshot": 26325,
                "jyhf_index_quote_snapshot": 0,
                "theme_cycle_judgement_v2": 6,
                "money_flow_enhanced": 24,
                "strong_stock_watch_history": 39,
                "dragon_tiger_object": 90,
            }
        )
    )

    result = await service.check(date(2026, 5, 29))

    assert result.status == "failed_precondition"
    assert result.base_tables["jyhf_index_quote_snapshot"] == 0
    assert "jyhf_index_quote_snapshot" in result.missing_tables

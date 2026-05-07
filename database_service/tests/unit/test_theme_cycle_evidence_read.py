from __future__ import annotations

from datetime import date

import pytest

from database_service.managers.postgres_manager import PostgresDatabaseManager


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetch(self, sql: str, *params: object):
        self.calls.append((sql, params))
        return [{"subject_key": "S1", "trade_date": date(2026, 4, 15), "theme_name": "T"}]


class _AcquireContext:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConnection:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakePool:
    def __init__(self, conn: _FakeConnection) -> None:
        self._conn = conn

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self._conn)


@pytest.mark.asyncio
async def test_get_subject_cycle_evidence_daily_none_subject_keys_reads_full_trade_date():
    conn = _FakeConnection()
    manager = object.__new__(PostgresDatabaseManager)
    manager.pool = _FakePool(conn)

    rows = await manager.get_subject_cycle_evidence_daily(date(2026, 4, 15), subject_keys=None)

    assert rows[0]["subject_key"] == "S1"
    sql, params = conn.calls[0]
    assert "subject_key = ANY" not in sql
    assert params == (date(2026, 4, 15),)


@pytest.mark.asyncio
async def test_get_subject_cycle_evidence_daily_empty_subject_keys_returns_empty_without_query():
    conn = _FakeConnection()
    manager = object.__new__(PostgresDatabaseManager)
    manager.pool = _FakePool(conn)

    rows = await manager.get_subject_cycle_evidence_daily(date(2026, 4, 15), subject_keys=[])

    assert rows == []
    assert conn.calls == []

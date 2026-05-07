from __future__ import annotations

from datetime import date

import pytest

from database_service.managers.postgres_manager import PostgresDatabaseManager


class _FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    async def fetch(self, sql: str, *params: object):
        self.calls.append((sql, params))
        return [{"subject_key": "S1", "trade_date": date(2026, 4, 15), "theme_name": "T"}]

    async def executemany(self, sql: str, params: list[tuple[object, ...]]):
        self.executemany_calls.append((sql, params))

    def transaction(self):
        return _TransactionContext()


class _FakeJudgementConnection(_FakeConnection):
    async def fetch(self, sql: str, *params: object):
        self.calls.append((sql, params))
        return [
            {"column_name": "subject_key"},
            {"column_name": "trade_date"},
            {"column_name": "theme_name"},
            {"column_name": "cycle_state_rule"},
            {"column_name": "mainline_alive_rule"},
            {"column_name": "final_cycle_state"},
            {"column_name": "final_mainline_alive"},
            {"column_name": "snapshot_version"},
            {"column_name": "batch_id"},
            {"column_name": "trace_id"},
            {"column_name": "rule_version"},
            {"column_name": "source_version"},
            {"column_name": "updated_at"},
            {"column_name": "evidence_json"},
        ]


class _TransactionContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


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


@pytest.mark.asyncio
async def test_upsert_theme_cycle_judgement_v2_rows_writes_audit_columns_when_present():
    conn = _FakeJudgementConnection()
    manager = object.__new__(PostgresDatabaseManager)
    manager.pool = _FakePool(conn)

    written = await manager.upsert_theme_cycle_judgement_v2_rows(
        [
            {
                "subject_key": "9064286",
                "trade_date": date(2026, 4, 15),
                "theme_name": "国产算力",
                "final_cycle_state": "divergence",
                "final_mainline_alive": True,
                "mainline_alive_rule": False,
                "snapshot_version": "replay_liande_v2",
                "batch_id": "batch-1",
                "trace_id": "trace-1",
                "rule_version": "subject_cycle_judgement.v2.old_chain_alive",
                "source_version": "stock_processing_service.layer_b.v2",
                "decision_path": "event_active_gate_failed_but_not_dead",
            }
        ]
    )

    assert written == 1
    sql, payload = conn.executemany_calls[0]
    assert "snapshot_version" in sql
    assert "batch_id" in sql
    assert "trace_id" in sql
    assert "rule_version" in sql
    assert "evidence_json" in sql
    row_values = payload[0]
    assert "replay_liande_v2" in row_values
    assert "batch-1" in row_values
    assert "trace-1" in row_values

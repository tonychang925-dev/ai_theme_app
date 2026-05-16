from __future__ import annotations

import json
from datetime import date

import pytest

from database_service.managers.postgres_manager import PostgresDatabaseManager


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _FakeAcquire(self.conn)


class _FakeConn:
    def __init__(self):
        self.rows: dict[date, dict] = {}

    async def execute(self, sql, *args):
        if "UPDATE pre_market_brief_snapshot" in sql:
            trade_date, force = args
            row = self.rows.get(trade_date)
            if not row or (row.get("status") == "final" and not force):
                return "UPDATE 0"
            row["status"] = "final"
            row["finalized_at"] = "now"
            row["updated_at"] = "now"
            return "UPDATE 1"

        (
            trade_date,
            snapshot_version,
            batch_id,
            trace_id,
            source_trace_id,
            payload_json,
            source_name,
            status,
            generated_at,
            finalized_at,
            force,
            explicit_status,
        ) = args
        existing = self.rows.get(trade_date)
        if existing and existing.get("status") == "final" and not force:
            return "INSERT 0 0"

        new_payload = json.loads(payload_json)
        if existing:
            payload = dict(existing.get("payload") or {})
            payload.update(new_payload)
        else:
            payload = new_payload
        self.rows[trade_date] = {
            "trade_date": trade_date,
            "snapshot_version": snapshot_version,
            "batch_id": batch_id,
            "trace_id": trace_id,
            "source_trace_id": source_trace_id,
            "payload": payload,
            "source_name": source_name,
            "status": explicit_status or (existing or {}).get("status") or status,
            "generated_at": generated_at or "now",
            "finalized_at": finalized_at,
            "updated_at": "now",
        }
        return "INSERT 0 1"

    async def fetchrow(self, sql, trade_date):
        return self.rows.get(trade_date)


def _manager() -> PostgresDatabaseManager:
    manager = object.__new__(PostgresDatabaseManager)
    manager.pool = _FakePool()
    return manager


@pytest.mark.asyncio
async def test_draft_rebuild_overwrites_existing_payload_keys():
    manager = _manager()
    trade_date = date(2026, 5, 16)

    await manager.upsert_pre_market_brief_snapshot(
        {"trade_date": trade_date, "snapshot_version": "v1", "payload": {"status": "draft", "a": 1}}
    )
    affected = await manager.upsert_pre_market_brief_snapshot(
        {"trade_date": trade_date, "snapshot_version": "v2", "payload": {"a": 2, "b": 3}}
    )

    row = await manager.get_pre_market_brief_snapshot(trade_date)
    assert affected == 1
    assert row["payload"] == {"status": "draft", "a": 2, "b": 3}
    assert row["snapshot_version"] == "v2"


@pytest.mark.asyncio
async def test_final_snapshot_is_not_overwritten_without_force():
    manager = _manager()
    trade_date = date(2026, 5, 16)

    await manager.upsert_pre_market_brief_snapshot(
        {"trade_date": trade_date, "snapshot_version": "v1", "payload": {"a": 1}}
    )
    assert await manager.finalize_pre_market_brief_snapshot(trade_date) == 1
    affected = await manager.upsert_pre_market_brief_snapshot(
        {"trade_date": trade_date, "snapshot_version": "v2", "payload": {"a": 2}},
        force=False,
    )

    row = await manager.get_pre_market_brief_snapshot(trade_date)
    assert affected == 0
    assert row["status"] == "final"
    assert row["payload"] == {"a": 1}
    assert row["snapshot_version"] == "v1"


@pytest.mark.asyncio
async def test_force_can_overwrite_final_snapshot():
    manager = _manager()
    trade_date = date(2026, 5, 16)

    await manager.upsert_pre_market_brief_snapshot(
        {"trade_date": trade_date, "snapshot_version": "v1", "payload": {"a": 1}}
    )
    await manager.finalize_pre_market_brief_snapshot(trade_date)
    affected = await manager.upsert_pre_market_brief_snapshot(
        {"trade_date": trade_date, "snapshot_version": "v2", "payload": {"a": 2}},
        force=True,
    )

    row = await manager.get_pre_market_brief_snapshot(trade_date)
    assert affected == 1
    assert row["payload"] == {"a": 2}
    assert row["snapshot_version"] == "v2"
    assert row["status"] == "final"


@pytest.mark.asyncio
async def test_explicit_status_can_change_force_overwritten_final_snapshot():
    manager = _manager()
    trade_date = date(2026, 5, 16)

    await manager.upsert_pre_market_brief_snapshot(
        {"trade_date": trade_date, "snapshot_version": "v1", "payload": {"a": 1}}
    )
    await manager.finalize_pre_market_brief_snapshot(trade_date)
    affected = await manager.upsert_pre_market_brief_snapshot(
        {"trade_date": trade_date, "snapshot_version": "v2", "status": "draft", "payload": {"a": 2}},
        force=True,
    )

    row = await manager.get_pre_market_brief_snapshot(trade_date)
    assert affected == 1
    assert row["payload"] == {"a": 2}
    assert row["status"] == "draft"

from __future__ import annotations

from types import SimpleNamespace

import pytest

from database_service.managers.postgres_manager import PostgresDatabaseManager


class _FakeConn:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []

    async def executemany(self, sql: str, payload: list[tuple[object, ...]]) -> None:
        self.executemany_calls.append((sql, payload))
        if self.fail:
            raise RuntimeError("boom")


class _AcquireCtx:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _FakeConn:
        return self._conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakePool:
    def __init__(self, conn: _FakeConn) -> None:
        self._conn = conn

    def acquire(self) -> _AcquireCtx:
        return _AcquireCtx(self._conn)


async def _noop_async() -> None:
    return None


@pytest.mark.asyncio
async def test_post_market_setup_plan_write_failure_raises() -> None:
    manager = PostgresDatabaseManager(SimpleNamespace(postgres_schema="public"))
    conn = _FakeConn(fail=True)
    manager.pool = _FakePool(conn)  # type: ignore[assignment]
    manager._ensure_one_to_two_setup_tables = _noop_async  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="failed to upsert post_market_setup_plan rows"):
        await manager.upsert_post_market_setup_plan_rows(
            [
                {
                    "trade_date": "2026-06-04",
                    "watch_date": "2026-06-05",
                    "setup_type": "one_to_two",
                    "stock_id": "__SUMMARY__",
                    "subject_key": "__SUMMARY__",
                    "decision": "pending_review_only",
                }
            ]
        )


@pytest.mark.asyncio
async def test_one_to_two_candidate_feature_write_failure_raises() -> None:
    manager = PostgresDatabaseManager(SimpleNamespace(postgres_schema="public"))
    conn = _FakeConn(fail=True)
    manager.pool = _FakePool(conn)  # type: ignore[assignment]
    manager._ensure_one_to_two_setup_tables = _noop_async  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="failed to upsert one_to_two_candidate_feature rows"):
        await manager.upsert_one_to_two_candidate_feature_rows(
            [
                {
                    "trade_date": "2026-06-04",
                    "watch_date": "2026-06-05",
                    "setup_type": "one_to_two",
                    "stock_id": "600367.SH",
                    "subject_key": "mainline_ai",
                    "decision": "reject",
                    "veto_reasons": ["other"],
                }
            ]
        )


@pytest.mark.asyncio
async def test_one_to_two_candidate_feature_invalid_row_raises() -> None:
    manager = PostgresDatabaseManager(SimpleNamespace(postgres_schema="public"))
    manager.pool = _FakePool(_FakeConn())  # type: ignore[assignment]
    manager._ensure_one_to_two_setup_tables = _noop_async  # type: ignore[assignment]

    with pytest.raises(ValueError, match="invalid one_to_two_candidate_feature row"):
        await manager.upsert_one_to_two_candidate_feature_rows(
            [
                {
                    "trade_date": "2026-06-04",
                    "watch_date": "2026-06-05",
                    "setup_type": "one_to_two",
                    "stock_id": "",
                    "subject_key": "mainline_ai",
                    "decision": "reject",
                    "veto_reasons": ["missing_stock_id"],
                }
            ]
        )


@pytest.mark.asyncio
async def test_post_market_setup_plan_invalid_row_raises() -> None:
    manager = PostgresDatabaseManager(SimpleNamespace(postgres_schema="public"))
    manager.pool = _FakePool(_FakeConn())  # type: ignore[assignment]
    manager._ensure_one_to_two_setup_tables = _noop_async  # type: ignore[assignment]

    with pytest.raises(ValueError, match="invalid post_market_setup_plan row"):
        await manager.upsert_post_market_setup_plan_rows(
            [
                {
                    "trade_date": "2026-06-04",
                    "watch_date": "",
                    "setup_type": "one_to_two",
                    "stock_id": "__SUMMARY__",
                    "subject_key": "__SUMMARY__",
                    "decision": "pending_review_only",
                }
            ]
        )

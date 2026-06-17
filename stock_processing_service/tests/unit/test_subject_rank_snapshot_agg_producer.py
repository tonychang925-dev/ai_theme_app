from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.jobs.subject_rank.base import (
    SubjectRankBuildRequest,
)
from stock_processing_service.application.jobs.subject_rank.snapshot_agg_producer import (
    SnapshotAggSubjectRankProducer,
)


class _Txn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Conn:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def fetchval(self, query: str, *args):
        if "subject_stock_daily_snapshot" in query:
            return 10
        if "subject_rank_daily" in query:
            return 0
        return 0

    async def fetchrow(self, query: str, *args):
        if "FROM agg" in query:
            return {
                "snapshot_subject_count": 1,
                "ranked_subject_count": 1,
                "avg_heat": 12.3456,
            }
        if "FROM ranked" in query:
            return {
                "ranked_subject_count": 1,
                "top100_count": 1,
                "avg_heat": 12.34,
                "max_heat": 20,
                "min_heat": 20,
            }
        return None

    async def execute(self, query: str, *args):
        self.execute_calls.append((query, args))
        return "INSERT 0 1"

    def transaction(self):
        return _Txn()


class _Pool:
    def __init__(self, conn: _Conn) -> None:
        self._conn = conn

    def acquire(self):
        return self

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TestProducer(SnapshotAggSubjectRankProducer):
    async def _check_quality(self, conn, td: date) -> dict:
        return {
            "snapshot_subject_count": 1,
            "ranked_subject_count": 1,
            "top100_count": 0,
            "missing_name_count": 0,
            "avg_heat": 12.3456,
            "max_heat": 0,
            "min_heat": 0,
        }

    async def _check_written_quality(self, conn, td: date) -> dict:
        return {
            "ranked_subject_count": 1,
            "top100_count": 1,
            "avg_heat": 12.34,
            "max_heat": 20,
            "min_heat": 20,
        }


@pytest.mark.asyncio
async def test_snapshot_agg_build_passes_one_arg_to_insert_sql() -> None:
    """TC-SUBJECT-RANK-SNAPSHOT-AGG-ARGS: INSERT SQL must receive the same arg count as placeholders."""

    conn = _Conn()
    producer = _TestProducer(db_pool=_Pool(conn))
    request = SubjectRankBuildRequest(
        trade_date=date(2026, 6, 17),
        provider="snapshot_agg",
        on_existing="replace",
        batch_id="batch-123",
    )

    result = await producer.build(request)

    assert result.status == "ok"
    insert_calls = [call for call in conn.execute_calls if "INSERT INTO subject_rank_daily" in call[0]]
    assert len(insert_calls) == 1
    assert len(insert_calls[0][1]) == 1

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from stock_processing_service.application.jobs.build_theme_cycle_evidence_daily_job import (
    BuildThemeCycleEvidenceDailyJob,
)


class _ReadPort:
    def __init__(self) -> None:
        self.bar_subject_key_calls: list[list[str] | None] = []

    async def get_all_confirmed_mainlines(self):
        return []

    async def get_all_prior_alive_cycles(self, trade_date: date):
        return []

    async def get_subject_rank_daily(self, trade_date: date, limit: int = 100):
        return [
            {"subject_key": "tracked_a", "description": "Tracked A", "heat": 70},
            {"subject_key": "tracked_b", "description": "Tracked B", "heat": 60},
        ]

    async def get_new_subject_rank_entries(self, trade_date: date):
        return []

    async def get_cluster_related_subjects(self, subject_keys: list[str], trade_date: date):
        return []

    async def get_subject_cycle_evidence_daily(self, trade_date: date, subject_keys=None):
        return [{"subject_key": key} for key in (subject_keys or [])]

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date):
        return [
            {"subject_key": "tracked_a", "theme_name": "Tracked A", "stock_id": "000001.SZ"},
            {"subject_key": "tracked_b", "theme_name": "Tracked B", "stock_id": "000002.SZ"},
            {"subject_key": "untracked", "theme_name": "Untracked", "stock_id": "000003.SZ"},
        ]

    async def get_subject_stock_daily_bars_range(self, **kwargs):
        self.bar_subject_key_calls.append(kwargs.get("subject_keys"))
        return []

    async def get_trade_calendar(self, trade_date: date):
        return SimpleNamespace(prev_trade_date=date(2026, 5, 27))

    async def get_mainline_cycle_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return []

    async def get_subject_event_stats(self, trade_date: date, subject_keys: list[str]):
        return [
            {
                "subject_key": key,
                "theme_name": key,
                "today_event_count": 0,
                "recent_event_count": 0,
                "distinct_event_days": 0,
                "key_event_count": 0,
                "sample_summaries": [],
            }
            for key in subject_keys
        ]


class _Builder:
    def build_many(self, *, trade_date, pool_rows, **kwargs):
        rows = []
        for row in pool_rows:
            rows.append(
                SimpleNamespace(
                    subject_key=row.subject_key,
                    theme_name=row.subject_name,
                    trade_date=trade_date,
                    event_strength_score=Decimal("0"),
                    event_continuity_score=Decimal("0"),
                    strong_event_count_7d=0,
                    event_recency_days=0,
                    event_count_3d=0,
                    event_count_7d=0,
                    leader_alive_score=Decimal("0"),
                    leader_breakdown_flag=False,
                    relay_strength_score=Decimal("0"),
                    front_row_survival_ratio=Decimal("0"),
                    limit_up_count=0,
                    limit_down_count=0,
                    red_ratio=Decimal("0"),
                    big_drop_ratio=Decimal("0"),
                    front_row_strength_score=Decimal("0"),
                    theme_support_score=Decimal("0"),
                    break_start_pivot=False,
                    above_ma5=False,
                    above_ma10=False,
                    above_ma20=False,
                    previous_cycle_state="",
                    evidence_json={},
                )
            )
        return rows


class _KlineBuilder:
    HISTORY_NATURAL_DAYS = 60

    def build_one(self, *, subject_key, stock_ids, bars_by_date, trade_dates):
        return SimpleNamespace(subject_key=subject_key, kline_quality="insufficient_history")


class _WritePort:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def upsert_theme_cycle_evidence_daily_rows(self, rows):
        self.rows = rows
        return len(rows)


class _EventPort:
    async def publish_stock_processing_event(self, event):
        return None


class _IdempotencyPort:
    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        return True

    async def mark_job_completed(self, job_key: str, metadata=None) -> None:
        return None


@pytest.mark.asyncio
async def test_theme_cycle_evidence_scopes_kline_to_tracked_universe_only() -> None:
    """TC-POSTMARKET-SCOPE: evidence build must not run K-line over all 660 subjects."""

    read_port = _ReadPort()
    write_port = _WritePort()
    job = BuildThemeCycleEvidenceDailyJob(
        read_port=read_port,
        write_port=write_port,
        event_port=_EventPort(),
        idempotency_port=_IdempotencyPort(),
        builder=_Builder(),
        kline_builder=_KlineBuilder(),
    )

    result = await job.execute(
        trade_date=date(2026, 5, 28),
        snapshot_version="test",
        batch_id="batch",
        trace_id="trace",
    )

    assert result.status == "ok"
    assert {row["subject_key"] for row in write_port.rows} == {"tracked_a", "tracked_b"}
    assert result.metrics["raw_pool_row_count"] == 3
    assert result.metrics["scoped_pool_row_count"] == 2
    assert read_port.bar_subject_key_calls
    assert all(call is None or set(call) <= {"tracked_a", "tracked_b"} for call in read_port.bar_subject_key_calls)

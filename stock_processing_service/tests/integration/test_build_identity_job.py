from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.application.jobs import BuildIdentityJob
from stock_processing_service.contracts.dto import StockBarDTO, SubjectContextDTO, SubjectStockPoolDTO


class _FakeReadPort:
    async def get_trade_calendar(self, trade_date: date):
        return None

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None):
        return [
            StockBarDTO(
                trade_date=trade_date,
                stock_id="688001.SH",
                stock_name="ChipA",
                open_price=Decimal("50"),
                high_price=Decimal("55"),
                low_price=Decimal("49"),
                close_price=Decimal("54"),
                pre_close=Decimal("50"),
                pct_chg=Decimal("8"),
                volume=Decimal("20000"),
                amount=Decimal("1000000"),
                limit_up_price=Decimal("55"),
                limit_down_price=Decimal("45"),
            )
        ]

    async def get_stock_auction_snapshot(self, trade_date: date, stock_ids: list[str] | None = None):
        return []

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date):
        return [
            SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key="ai_chip",
                subject_name="AI Chip",
                stock_id="688001.SH",
                stock_name="ChipA",
                pool_rank=1,
            )
        ]

    async def get_subject_context_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return [
            SubjectContextDTO(
                trade_date=trade_date,
                subject_key="ai_chip",
                subject_name="AI Chip",
                theme_context_tags=["policy", "capital"],
            )
        ]

    async def get_prior_stock_daily_snapshots(self, trade_date: date, lookback_days: int, stock_ids: list[str] | None = None):
        return []

    async def get_existing_pre_market_brief_snapshot(self, trade_date: date):
        return None

    async def get_existing_post_market_recap_snapshot(self, trade_date: date):
        return None

    async def get_subject_event_stats(
        self, trade_date: date, subject_keys: list[str] | None = None
    ):
        return []

    async def get_mainline_identity_by_subject_keys(
        self, subject_keys: list[str], trade_date: date
    ):
        return []

    async def get_mainline_cycle_by_subject_keys(
        self, subject_keys: list[str], trade_date: date
    ):
        return []

    async def get_prior_strong_watch_pool_rows(
        self, trade_date: date, lookback_days: int
    ):
        return []


class _FakeWritePort:
    def __init__(self) -> None:
        self.identity_rows: list[dict[str, Any]] = []
        self.review_rows: list[dict[str, Any]] = []

    async def upsert_stock_daily_snapshot_rows(self, rows):
        return len(rows)

    async def upsert_subject_stock_daily_snapshot_rows(self, rows):
        return len(rows)

    async def upsert_stock_abnormal_event_rows(self, rows):
        return len(rows)

    async def upsert_theme_stock_leaderboard_rows(self, rows):
        return len(rows)

    async def upsert_pre_market_brief_snapshot(self, doc):
        return 1

    async def upsert_post_market_recap_snapshot(self, doc):
        return 1

    async def upsert_theme_mainline_identity_registry_rows(self, rows):
        self.identity_rows.extend(rows)
        return len(rows)

    async def upsert_mainline_identity_review_queue_rows(self, rows):
        self.review_rows.extend(rows)
        return len(rows)


class _FakeEventPort:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish_stock_processing_event(self, event):
        self.events.append(asdict(event))
        return "msg"

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str):
        return "dlq"


class _FakeIdempotencyPort:
    def __init__(self) -> None:
        self.once = False

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int):
        if self.once:
            return False
        self.once = True
        return True

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None):
        return None


def test_build_identity_job() -> None:
    async def _run() -> None:
        write = _FakeWritePort()
        events = _FakeEventPort()
        job = BuildIdentityJob(
            read_port=_FakeReadPort(),
            write_port=write,
            event_port=events,
            idempotency_port=_FakeIdempotencyPort(),
        )
        result = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="id-v1",
            batch_id="bid1",
            trace_id="tid1",
        )
        assert result.status == "ok"
        assert len(write.identity_rows) == 1
        assert len(events.events) == 1
        assert events.events[0]["event_name"] == "snapshot_built"

    asyncio.run(_run())

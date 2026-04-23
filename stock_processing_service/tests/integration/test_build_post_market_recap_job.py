from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.application.jobs import BuildPostMarketRecapJob
from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO


class _FakeReadPort:
    async def get_trade_calendar(self, trade_date: date):
        return None

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[StockBarDTO]:
        return [
            StockBarDTO(
                trade_date=trade_date,
                stock_id="002000.SZ",
                stock_name="SampleA",
                open_price=Decimal("12"),
                high_price=Decimal("13"),
                low_price=Decimal("11.8"),
                close_price=Decimal("12.9"),
                pre_close=Decimal("12"),
                pct_chg=Decimal("7.5"),
                volume=Decimal("30000"),
                amount=Decimal("350000"),
                limit_up_price=Decimal("13.2"),
                limit_down_price=Decimal("10.8"),
            )
        ]

    async def get_stock_auction_snapshot(self, trade_date: date, stock_ids: list[str] | None = None):
        return []

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date) -> list[SubjectStockPoolDTO]:
        return [
            SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key="ai_chip",
                subject_name="AI Chip",
                stock_id="002000.SZ",
                stock_name="SampleA",
                pool_rank=1,
            )
        ]

    async def get_subject_context_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return []

    async def get_prior_stock_daily_snapshots(
        self, trade_date: date, lookback_days: int, stock_ids: list[str] | None = None
    ) -> list[PriorSnapshotDTO]:
        return [
            PriorSnapshotDTO(
                trade_date=trade_date,
                stock_id="002000.SZ",
                snapshot_version="v-prev",
                payload={"final_cycle_state": "repair"},
            )
        ]

    async def get_existing_pre_market_brief_snapshot(self, trade_date: date):
        return None

    async def get_existing_post_market_recap_snapshot(self, trade_date: date):
        return None


class _FakeWritePort:
    def __init__(self) -> None:
        self.recap_docs: list[Any] = []

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
        self.recap_docs.append(doc)
        return 1


class _FakeEventPort:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish_stock_processing_event(self, event):
        self.events.append(asdict(event))
        return "msg-1"

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str):
        return "dlq"


class _FakeIdempotencyPort:
    def __init__(self) -> None:
        self.once = False

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        if self.once:
            return False
        self.once = True
        return True

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None) -> None:
        return None


class _FakeCachePort:
    def __init__(self) -> None:
        self.cache: dict[str, Any] = {}

    async def get(self, key: str):
        return self.cache.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None):
        self.cache[key] = {"value": value, "ttl": ttl_seconds}

    async def delete(self, key: str):
        self.cache.pop(key, None)
        return 1

    async def invalidate_pattern(self, pattern: str):
        return 0


def test_build_post_market_recap_job() -> None:
    async def _run() -> None:
        read_port = _FakeReadPort()
        write_port = _FakeWritePort()
        event_port = _FakeEventPort()
        idempotency_port = _FakeIdempotencyPort()
        cache_port = _FakeCachePort()

        job = BuildPostMarketRecapJob(
            read_port=read_port,
            write_port=write_port,
            event_port=event_port,
            idempotency_port=idempotency_port,
            cache_port=cache_port,
        )

        result = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="pm-v1",
            batch_id="bpm1",
            trace_id="tpm1",
        )
        assert result.status == "ok"
        assert result.affected_rows == 1
        assert len(write_port.recap_docs) == 1
        recap_doc = write_port.recap_docs[0].recap_doc
        assert recap_doc["candidate_source"] == "strong_watch_pool"
        assert recap_doc["strong_watch_promoted_count"] >= recap_doc["candidate_count"]
        assert len(event_port.events) == 1
        assert event_port.events[0]["event_name"] == "snapshot_built"
        assert "sps:post_market_recap:2026-04-23" in cache_port.cache
        assert "sps:post_market_recap:current:2026-04-23" in cache_port.cache

        skipped = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="pm-v1",
            batch_id="bpm1",
            trace_id="tpm1",
        )
        assert skipped.status == "skipped_idempotent"

    asyncio.run(_run())

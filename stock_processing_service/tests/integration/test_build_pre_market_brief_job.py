from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.application.jobs import BuildPreMarketBriefJob
from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockAuctionDTO, StockBarDTO, SubjectStockPoolDTO


class _FakeReadPort:
    async def get_trade_calendar(self, trade_date: date):
        return None

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[StockBarDTO]:
        return [
            StockBarDTO(
                trade_date=trade_date,
                stock_id="300001.SZ",
                stock_name="SampleB",
                open_price=Decimal("20"),
                high_price=Decimal("21"),
                low_price=Decimal("19.5"),
                close_price=Decimal("20.8"),
                pre_close=Decimal("20"),
                pct_chg=Decimal("4"),
                volume=Decimal("50000"),
                amount=Decimal("800000"),
                limit_up_price=Decimal("22"),
                limit_down_price=Decimal("18"),
            )
        ]

    async def get_stock_auction_snapshot(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> list[StockAuctionDTO]:
        return [
            StockAuctionDTO(
                trade_date=trade_date,
                stock_id="300001.SZ",
                auction_open_pct=Decimal("2.5"),
                auction_amount=Decimal("2500000"),
                tail_auction_vwap=Decimal("20.9"),
            )
        ]

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date) -> list[SubjectStockPoolDTO]:
        return [
            SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key="ai_agent",
                subject_name="AI Agent",
                stock_id="300001.SZ",
                stock_name="SampleB",
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
                stock_id="300001.SZ",
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
        self.docs: list[Any] = []

    async def upsert_stock_daily_snapshot_rows(self, rows):
        return len(rows)

    async def upsert_subject_stock_daily_snapshot_rows(self, rows):
        return len(rows)

    async def upsert_stock_abnormal_event_rows(self, rows):
        return len(rows)

    async def upsert_theme_stock_leaderboard_rows(self, rows):
        return len(rows)

    async def upsert_pre_market_brief_snapshot(self, doc):
        self.docs.append(doc)
        return 1

    async def upsert_post_market_recap_snapshot(self, doc):
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
        self.used = False

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        if self.used:
            return False
        self.used = True
        return True

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None):
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


def test_build_pre_market_brief_job() -> None:
    async def _run() -> None:
        write_port = _FakeWritePort()
        event_port = _FakeEventPort()
        job = BuildPreMarketBriefJob(
            read_port=_FakeReadPort(),
            write_port=write_port,
            event_port=event_port,
            idempotency_port=_FakeIdempotencyPort(),
            cache_port=_FakeCachePort(),
        )
        result = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="pre-v1",
            batch_id="bp1",
            trace_id="tp1",
        )
        assert result.status == "ok"
        assert len(write_port.docs) == 1
        brief_doc = write_port.docs[0].brief_doc
        assert brief_doc["reject_reason_coverage_ok"] is True
        assert brief_doc["reject_reason_valid_ok"] is True
        assert len(event_port.events) == 1
        skipped = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="pre-v1",
            batch_id="bp1",
            trace_id="tp1",
        )
        assert skipped.status == "skipped_idempotent"

    asyncio.run(_run())

from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.application.jobs import BuildDailySnapshotJob
from stock_processing_service.contracts.dto import (
    PriorSnapshotDTO,
    StockBarDTO,
    SubjectContextDTO,
    SubjectStockPoolDTO,
    TradeCalendarDTO,
)


class _FakeReadPort:
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO | None:
        return TradeCalendarDTO(trade_date=trade_date, calendar_is_open=True)

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[StockBarDTO]:
        return [
            StockBarDTO(
                trade_date=trade_date,
                stock_id="000001.SZ",
                stock_name="PingAn",
                open_price=Decimal("10"),
                high_price=Decimal("11"),
                low_price=Decimal("9.8"),
                close_price=Decimal("10.8"),
                pre_close=Decimal("10"),
                pct_chg=Decimal("8"),
                volume=Decimal("100000"),
                amount=Decimal("1000000"),
                limit_up_price=Decimal("11"),
                limit_down_price=Decimal("9"),
            )
        ]

    async def get_stock_auction_snapshot(self, trade_date: date, stock_ids: list[str] | None = None):
        return []

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date) -> list[SubjectStockPoolDTO]:
        return [
            SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key="robotics",
                subject_name="Robotics",
                stock_id="000001.SZ",
                stock_name="PingAn",
                pool_rank=1,
            )
        ]

    async def get_subject_context_by_subject_keys(
        self, subject_keys: list[str], trade_date: date
    ) -> list[SubjectContextDTO]:
        return [
            SubjectContextDTO(
                trade_date=trade_date,
                subject_key="robotics",
                subject_name="Robotics",
                theme_context_tags=["policy"],
            )
        ]

    async def get_prior_stock_daily_snapshots(
        self, trade_date: date, lookback_days: int, stock_ids: list[str] | None = None
    ) -> list[PriorSnapshotDTO]:
        return [
            PriorSnapshotDTO(
                trade_date=trade_date,
                stock_id="000001.SZ",
                snapshot_version="v-prev",
                payload={"final_cycle_state": "mainline_active"},
            )
        ]

    async def get_existing_pre_market_brief_snapshot(self, trade_date: date):
        return None

    async def get_existing_post_market_recap_snapshot(self, trade_date: date):
        return None


class _FakeWritePort:
    def __init__(self) -> None:
        self.calls: dict[str, list[Any]] = {
            "daily": [],
            "subject": [],
            "abnormal": [],
            "leaderboard": [],
        }

    async def upsert_stock_daily_snapshot_rows(self, rows):
        self.calls["daily"].append(rows)
        return len(rows)

    async def upsert_subject_stock_daily_snapshot_rows(self, rows):
        self.calls["subject"].append(rows)
        return len(rows)

    async def upsert_stock_abnormal_event_rows(self, rows):
        self.calls["abnormal"].append(rows)
        return len(rows)

    async def upsert_theme_stock_leaderboard_rows(self, rows):
        self.calls["leaderboard"].append(rows)
        return len(rows)

    async def upsert_pre_market_brief_snapshot(self, doc):
        return 1

    async def upsert_post_market_recap_snapshot(self, doc):
        return 1


class _FakeEventPort:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish_stock_processing_event(self, event):
        self.events.append(asdict(event))
        return f"msg-{len(self.events)}"

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str):
        self.events.append({"event_name": event_name, "payload": payload, "reason": reason})
        return "dlq"


class _FakeIdempotencyPort:
    def __init__(self) -> None:
        self.done: list[dict[str, Any]] = []
        self._acquired = False

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        if self._acquired:
            return False
        self._acquired = True
        return True

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None) -> None:
        self.done.append({"job_key": job_key, "metadata": metadata or {}})


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


def test_build_daily_snapshot_job_end_to_end_and_idempotent() -> None:
    async def _run() -> None:
        read_port = _FakeReadPort()
        write_port = _FakeWritePort()
        event_port = _FakeEventPort()
        idempotency_port = _FakeIdempotencyPort()
        cache_port = _FakeCachePort()

        job = BuildDailySnapshotJob(
            read_port=read_port,
            write_port=write_port,
            event_port=event_port,
            idempotency_port=idempotency_port,
            cache_port=cache_port,
        )

        result = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="v1",
            batch_id="b1",
            trace_id="t1",
            lookback_days=5,
        )

        assert result.status == "ok"
        assert len(write_port.calls["daily"]) == 1
        assert len(write_port.calls["subject"]) == 1
        assert len(write_port.calls["abnormal"]) == 1
        assert len(write_port.calls["leaderboard"]) == 1
        assert len(event_port.events) >= 2
        assert any(e["event_name"] == "snapshot_built" for e in event_port.events)
        assert any(e["event_name"] == "leaderboard_updated" for e in event_port.events)
        assert idempotency_port.done
        assert "sps:calendar:2026-04-23" in cache_port.cache
        assert "sps:stock_daily_snapshot:current:2026-04-23" in cache_port.cache

        skipped = await job.execute(
            trade_date=date(2026, 4, 23),
            snapshot_version="v1",
            batch_id="b1",
            trace_id="t1",
            lookback_days=5,
        )
        assert skipped.status == "skipped_idempotent"
        assert skipped.batch_id == "b1"
        assert skipped.trace_id == "t1"
        assert "idempotency_key_already_completed" in skipped.warnings

    asyncio.run(_run())

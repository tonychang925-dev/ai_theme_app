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


class _ReadPort:
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO | None:
        return TradeCalendarDTO(trade_date=trade_date, calendar_is_open=True)

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[StockBarDTO]:
        return [
            StockBarDTO(
                trade_date=trade_date,
                stock_id="000001.SZ",
                stock_name="A",
                open_price=Decimal("10"),
                high_price=Decimal("11"),
                low_price=Decimal("9"),
                close_price=Decimal("9.2"),
                pre_close=Decimal("10"),
                pct_chg=Decimal("-8"),
                volume=Decimal("100"),
                amount=Decimal("1000"),
                limit_up_price=Decimal("11"),
                limit_down_price=Decimal("9"),
            ),
            StockBarDTO(
                trade_date=trade_date,
                stock_id="000002.SZ",
                stock_name="B",
                open_price=Decimal("20"),
                high_price=Decimal("20.5"),
                low_price=Decimal("18"),
                close_price=Decimal("18.1"),
                pre_close=Decimal("20"),
                pct_chg=Decimal("-9.5"),
                volume=Decimal("120"),
                amount=Decimal("1300"),
                limit_up_price=Decimal("22"),
                limit_down_price=Decimal("18"),
            ),
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
                stock_name="A",
                pool_rank=1,
            ),
            SubjectStockPoolDTO(
                trade_date=trade_date,
                subject_key="robotics",
                subject_name="Robotics",
                stock_id="000002.SZ",
                stock_name="B",
                pool_rank=2,
            ),
        ]

    async def get_subject_context_by_subject_keys(self, subject_keys: list[str], trade_date: date) -> list[SubjectContextDTO]:
        return [
            SubjectContextDTO(
                trade_date=trade_date,
                subject_key="robotics",
                subject_name="Robotics",
                theme_context_tags=["policy"],
            )
        ]

    async def get_prior_stock_daily_snapshots(self, trade_date: date, lookback_days: int, stock_ids: list[str] | None = None) -> list[PriorSnapshotDTO]:
        return [
            PriorSnapshotDTO(
                trade_date=date(2026, 4, 22),
                stock_id="000001.SZ",
                snapshot_version="v0",
                payload={"final_cycle_state": "fade_watch"},
            ),
            PriorSnapshotDTO(
                trade_date=date(2026, 4, 22),
                stock_id="000002.SZ",
                snapshot_version="v0",
                payload={"final_cycle_state": "fade_watch"},
            ),
        ]


class _WritePort:
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


class _EventPort:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def publish_stock_processing_event(self, event):
        self.events.append(asdict(event))
        return "ok"

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str):
        return "ok"


class _IdempotencyPort:
    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        return True

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None) -> None:
        return None


async def _run() -> list[dict[str, Any]]:
    event_port = _EventPort()
    job = BuildDailySnapshotJob(
        read_port=_ReadPort(),
        write_port=_WritePort(),
        event_port=event_port,
        idempotency_port=_IdempotencyPort(),
        cache_port=None,
    )
    await job.execute(
        trade_date=date(2026, 4, 23),
        snapshot_version="v1",
        batch_id="b1",
        trace_id="t1",
    )
    return event_port.events


def test_event_payloads_grouped_publish() -> None:
    events = asyncio.run(_run())

    snapshot_events = [e for e in events if e.get("event_name") == "snapshot_built"]
    abnormal_events = [e for e in events if e.get("event_name") == "abnormal_detected"]
    leaderboard_events = [e for e in events if e.get("event_name") == "leaderboard_updated"]

    assert len(snapshot_events) == 1
    assert len(leaderboard_events) == 1

    payload = snapshot_events[0]["payload"]
    assert payload.get("domain") == "daily_snapshot"
    assert payload.get("snapshot_version") == "v1"
    assert payload.get("object_name") == "stock_daily_snapshot"

    # abnormal_detected should be grouped by stock_id (one event per stock)
    stock_ids = {e["payload"].get("stock_id") for e in abnormal_events}
    assert "*batch*" not in stock_ids
    assert stock_ids.issubset({"000001.SZ", "000002.SZ"})
    assert len(abnormal_events) == len(stock_ids)

    # leaderboard_updated should be grouped by subject_key
    assert leaderboard_events[0]["payload"].get("subject_key") == "robotics"

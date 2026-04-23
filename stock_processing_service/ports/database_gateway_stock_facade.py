from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from stock_processing_service.contracts.dto import (
    BriefSnapshotDTO,
    PriorSnapshotDTO,
    RecapSnapshotDTO,
    StockAuctionDTO,
    StockBarDTO,
    SubjectContextDTO,
    SubjectStockPoolDTO,
    TradeCalendarDTO,
)
from stock_processing_service.contracts.events import EventEnvelope
from stock_processing_service.contracts.snapshots import (
    PostMarketRecapSnapshot,
    PreMarketBriefSnapshot,
    StockAbnormalEvent,
    StockDailySnapshot,
    SubjectStockDailySnapshot,
    ThemeStockLeaderboard,
)


class DatabaseGatewayStockFacade(Protocol):
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO | None: ...

    async def get_stock_daily_bars(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> list[StockBarDTO]: ...

    async def get_stock_auction_snapshot(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> list[StockAuctionDTO]: ...

    async def get_subject_stock_pool_by_trade_date(
        self, trade_date: date
    ) -> list[SubjectStockPoolDTO]: ...

    async def get_subject_context_by_subject_keys(
        self, subject_keys: list[str], trade_date: date
    ) -> list[SubjectContextDTO]: ...

    async def get_prior_stock_daily_snapshots(
        self, trade_date: date, lookback_days: int, stock_ids: list[str] | None = None
    ) -> list[PriorSnapshotDTO]: ...

    async def get_existing_pre_market_brief_snapshot(
        self, trade_date: date
    ) -> BriefSnapshotDTO | None: ...

    async def get_existing_post_market_recap_snapshot(
        self, trade_date: date
    ) -> RecapSnapshotDTO | None: ...

    async def upsert_stock_daily_snapshot_rows(self, rows: list[StockDailySnapshot]) -> int: ...

    async def upsert_subject_stock_daily_snapshot_rows(
        self, rows: list[SubjectStockDailySnapshot]
    ) -> int: ...

    async def upsert_stock_abnormal_event_rows(self, rows: list[StockAbnormalEvent]) -> int: ...

    async def upsert_theme_stock_leaderboard_rows(self, rows: list[ThemeStockLeaderboard]) -> int: ...

    async def upsert_pre_market_brief_snapshot(self, doc: PreMarketBriefSnapshot) -> int: ...

    async def upsert_post_market_recap_snapshot(self, doc: PostMarketRecapSnapshot) -> int: ...

    async def upsert_theme_mainline_identity_registry_rows(self, rows: list[dict[str, Any]]) -> int: ...

    async def upsert_mainline_identity_review_queue_rows(self, rows: list[dict[str, Any]]) -> int: ...

    async def publish_stock_processing_event(self, event: EventEnvelope[Any]) -> str: ...

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool: ...

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None) -> None: ...

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str) -> str: ...

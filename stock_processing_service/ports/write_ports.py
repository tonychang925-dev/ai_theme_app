from __future__ import annotations

from typing import Any, Protocol

from stock_processing_service.contracts.snapshots import (
    PostMarketRecapSnapshot,
    PreMarketBriefSnapshot,
    StockAbnormalEvent,
    StockDailySnapshot,
    SubjectStockDailySnapshot,
    ThemeStockLeaderboard,
)


class SnapshotWritePort(Protocol):
    async def upsert_stock_daily_snapshot_rows(self, rows: list[StockDailySnapshot]) -> int: ...

    async def upsert_subject_stock_daily_snapshot_rows(
        self, rows: list[SubjectStockDailySnapshot]
    ) -> int: ...

    async def upsert_stock_abnormal_event_rows(self, rows: list[StockAbnormalEvent]) -> int: ...

    async def upsert_theme_stock_leaderboard_rows(self, rows: list[ThemeStockLeaderboard]) -> int: ...

    async def upsert_pre_market_brief_snapshot(self, doc: PreMarketBriefSnapshot) -> int: ...

    async def upsert_post_market_recap_snapshot(self, doc: PostMarketRecapSnapshot) -> int: ...


class AlgorithmStateWritePort(Protocol):
    async def upsert_theme_mainline_identity_registry_rows(self, rows: list[dict[str, Any]]) -> int: ...

    async def upsert_mainline_identity_review_queue_rows(self, rows: list[dict[str, Any]]) -> int: ...


class StockWritePort(SnapshotWritePort, AlgorithmStateWritePort, Protocol):
    """Backward-compatible composite port."""


# Backward-compatible alias
StockWritePorts = StockWritePort

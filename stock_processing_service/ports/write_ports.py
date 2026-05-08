from __future__ import annotations

from typing import Any, Protocol

from stock_processing_service.contracts.snapshots import (
    PostMarketRecapSnapshot,
    PreMarketBriefSnapshot,
    StockAbnormalEvent,
    StockDailyStrategySnapshot,
    SubjectStockDailySnapshot,
    ThemeStockLeaderboard,
)


class SnapshotWritePort(Protocol):
    async def upsert_stock_daily_strategy_snapshot_rows(self, rows: list[StockDailyStrategySnapshot]) -> int: ...

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

    async def upsert_strong_watch_history_rows(self, rows: list[dict[str, Any]]) -> int: ...

    async def upsert_theme_cycle_evidence_daily_rows(self, rows: list[dict[str, Any]]) -> int: ...

    async def upsert_theme_cycle_judgement_v2_rows(self, rows: list[dict[str, Any]]) -> int: ...


class StrongWatchWritePort(Protocol):
    """Layer C 强势池写入端口。"""

    async def upsert_strong_watch_pool_rows(self, rows: list[dict[str, Any]]) -> int: ...

    async def promote_strong_watch_candidates(self, trade_date: Any) -> int: ...

    async def prune_strong_watch_pool(self, trade_date: Any, weakening_min_score: float = 62.0) -> int: ...


class StockWritePort(SnapshotWritePort, AlgorithmStateWritePort, StrongWatchWritePort, Protocol):
    """Backward-compatible composite port."""


# Backward-compatible alias
StockWritePorts = StockWritePort

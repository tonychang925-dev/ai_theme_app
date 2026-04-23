from __future__ import annotations

from datetime import date

from stock_processing_service.contracts.dto import StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_prune_service import StrongWatchPruneService
from stock_processing_service.domain.services.strong_watch_promote_service import StrongWatchPromoteService
from stock_processing_service.domain.services.strong_watch_refresh_service import (
    StrongWatchRecord,
    StrongWatchRefreshService,
)
from stock_processing_service.domain.services.strong_watch_seed_service import StrongWatchSeedService


class StrongWatchService:
    def __init__(
        self,
        seed_service: StrongWatchSeedService | None = None,
        refresh_service: StrongWatchRefreshService | None = None,
        prune_service: StrongWatchPruneService | None = None,
        promote_service: StrongWatchPromoteService | None = None,
    ) -> None:
        self._seed_service = seed_service or StrongWatchSeedService()
        self._refresh_service = refresh_service or StrongWatchRefreshService()
        self._prune_service = prune_service or StrongWatchPruneService()
        self._promote_service = promote_service or StrongWatchPromoteService()

    def build_promoted_pool(
        self,
        trade_date: date,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
    ) -> tuple[list[SubjectStockPoolDTO], list[StrongWatchRecord]]:
        seeded = self._seed_service.seed(pool_rows)
        refreshed = self._refresh_service.refresh(seeded, bars)
        pruned = self._prune_service.prune(refreshed)
        promoted = self._promote_service.promote(trade_date, pruned)
        return promoted, pruned

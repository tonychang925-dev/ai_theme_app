from __future__ import annotations

from dataclasses import replace
from datetime import date

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO, SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_prune_service import StrongWatchPruneService
from stock_processing_service.domain.services.strong_watch_promote_service import StrongWatchPromoteService
from stock_processing_service.domain.services.strong_watch_refresh_service import (
    StrongWatchRecord,
    StrongWatchRefreshService,
)
from stock_processing_service.domain.services.strong_watch_history_service import (
    StrongWatchHistoryRecord,
    StrongWatchHistoryService,
)
from stock_processing_service.domain.services.strong_watch_roll_forward_service import (
    StrongWatchRollForwardService,
)
from stock_processing_service.domain.services.strong_watch_seed_service import StrongWatchSeedService


class StrongWatchService:
    def __init__(
        self,
        seed_service: StrongWatchSeedService | None = None,
        refresh_service: StrongWatchRefreshService | None = None,
        prune_service: StrongWatchPruneService | None = None,
        promote_service: StrongWatchPromoteService | None = None,
        roll_forward_service: StrongWatchRollForwardService | None = None,
        history_service: StrongWatchHistoryService | None = None,
    ) -> None:
        self._seed_service = seed_service or StrongWatchSeedService()
        self._refresh_service = refresh_service or StrongWatchRefreshService()
        self._prune_service = prune_service or StrongWatchPruneService()
        self._promote_service = promote_service or StrongWatchPromoteService()
        self._roll_forward_service = roll_forward_service or StrongWatchRollForwardService()
        self._history_service = history_service or StrongWatchHistoryService()

    def build_promoted_pool(
        self,
        trade_date: date,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
        prior_active_rows: list[StrongWatchRecord] | None = None,
    ) -> tuple[list[SubjectStockPoolDTO], list[StrongWatchRecord]]:
        promoted, kept, _history = self.build_promoted_pool_with_history(
            trade_date=trade_date,
            pool_rows=pool_rows,
            bars=bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
            prior_active_rows=prior_active_rows,
        )
        return promoted, kept

    def build_promoted_pool_with_history(
        self,
        trade_date: date,
        pool_rows: list[SubjectStockPoolDTO],
        bars: list[StockBarDTO],
        prior_rows: list[PriorSnapshotDTO] | None = None,
        history_bars: list[StockBarDTO] | None = None,
        prior_active_rows: list[StrongWatchRecord] | None = None,
    ) -> tuple[list[SubjectStockPoolDTO], list[StrongWatchRecord], list[StrongWatchHistoryRecord]]:
        seeded = self._seed_service.seed(pool_rows)
        rolled = self._roll_forward_service.roll_forward(
            trade_date=trade_date,
            seeded_rows=seeded,
            prior_active_rows=prior_active_rows or [],
        )
        refreshed = self._refresh_service.refresh(
            seeded,
            bars,
            prior_rows=prior_rows,
            history_bars=history_bars,
        )
        # merge roll-forward weak_days baseline
        baseline_weak_days = {r.stock_id: r.weak_days for r in rolled}
        refreshed = [replace(r, weak_days=baseline_weak_days.get(r.stock_id, 0)) for r in refreshed]
        kept, pruned = self._prune_service.prune(refreshed)
        promoted = self._promote_service.promote(trade_date, kept)
        history_rows = self._history_service.build_history_snapshot(
            trade_date=trade_date,
            kept_rows=kept,
            pruned_rows=pruned,
        )
        return promoted, kept, history_rows

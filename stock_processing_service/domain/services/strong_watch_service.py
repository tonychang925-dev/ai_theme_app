from __future__ import annotations

from dataclasses import replace
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
        prior_active_rows: list[StrongWatchRecord] | None = None,
    ) -> tuple[list[SubjectStockPoolDTO], list[StrongWatchRecord]]:
        seeded = self._seed_service.seed(pool_rows)
        rolled = self.roll_forward_active_pool(seeded, prior_active_rows or [])
        refreshed = self._refresh_service.refresh(seeded, bars)
        # merge roll-forward weak_days baseline
        baseline_weak_days = {r.stock_id: r.weak_days for r in rolled}
        refreshed = [replace(r, weak_days=baseline_weak_days.get(r.stock_id, 0)) for r in refreshed]
        kept, _pruned = self._prune_service.prune(refreshed)
        promoted = self._promote_service.promote(trade_date, kept)
        return promoted, kept

    def roll_forward_active_pool(
        self,
        seeded_rows: list[SubjectStockPoolDTO],
        prior_active_rows: list[StrongWatchRecord],
    ) -> list[StrongWatchRecord]:
        seeded_ids = {row.stock_id for row in seeded_rows}
        # Keep prior active/weakening rows in baseline for weak_days continuity.
        return [row for row in prior_active_rows if row.stock_id in seeded_ids and row.watch_status in {"active", "weakening"}]

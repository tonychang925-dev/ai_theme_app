from __future__ import annotations

from datetime import date
from typing import Protocol

from stock_processing_service.contracts.dto import (
    BriefSnapshotDTO,
    MainlineCycleDTO,
    MainlineIdentityDTO,
    PriorSnapshotDTO,
    RecapSnapshotDTO,
    StockAuctionDTO,
    StockBarDTO,
    SubjectContextDTO,
    SubjectEventStatsDTO,
    SubjectStockPoolDTO,
    TradeCalendarDTO,
)


class StockReadPort(Protocol):
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO | None: ...

    async def get_stock_daily_bars(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> list[StockBarDTO]: ...

    async def get_stock_daily_bars_range(
        self, start_date: date, end_date: date, stock_ids: list[str] | None = None
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

    async def get_mainline_identity_by_subject_keys(
        self, subject_keys: list[str], trade_date: date
    ) -> list[MainlineIdentityDTO]: ...

    async def get_mainline_identity_rule_inputs(
        self, trade_date: date, subject_keys: list[str]
    ) -> list[dict]: ...

    async def get_mainline_cycle_by_subject_keys(
        self, subject_keys: list[str], trade_date: date
    ) -> list[MainlineCycleDTO]: ...

    async def get_prior_strong_watch_pool_rows(
        self, trade_date: date, lookback_days: int
    ) -> list[SubjectStockPoolDTO]: ...

    async def get_legacy_strong_watch_candidate_inputs(
        self, trade_date: date, lookback_days: int = 7
    ) -> list[SubjectStockPoolDTO]: ...

    async def get_subject_event_stats(
        self, trade_date: date, subject_keys: list[str] | None = None
    ) -> list[SubjectEventStatsDTO]: ...

    async def get_subject_cycle_evidence_daily(
        self, trade_date: date, subject_keys: list[str] | None = None
    ) -> list[dict]: ...

    async def get_mainline_state_daily(
        self, trade_date: date, subject_keys: list[str]
    ) -> list[dict[str, Any]]: ...

    async def get_prior_mainline_state_daily(
        self, trade_date: date
    ) -> list[dict[str, Any]]: ...

    async def get_subject_board_stats(
        self, trade_date: date
    ) -> list[dict[str, Any]]: ...

    async def get_stock_position_judgement(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> list[dict[str, Any]]: ...

    async def get_stock_pattern_judgement(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> list[dict[str, Any]]: ...

    async def get_w2s_candidate_inputs(
        self, trade_date: date
    ) -> list[dict[str, Any]]: ...

    async def get_strong_watch_seed_rows(
        self, trade_date: date, lookback_days: int = 7
    ) -> list[dict[str, Any]]: ...

    async def get_strong_watch_refresh_rows(
        self, trade_date: date
    ) -> list[dict[str, Any]]: ...


# Backward-compatible alias
StockReadPorts = StockReadPort

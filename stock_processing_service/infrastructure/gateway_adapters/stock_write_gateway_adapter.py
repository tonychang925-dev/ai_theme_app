from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from stock_processing_service.contracts.snapshots import (
    PostMarketRecapSnapshot,
    PreMarketBriefSnapshot,
    StockAbnormalEvent,
    StockDailyStrategySnapshot,
    SubjectStockDailySnapshot,
    ThemeStockLeaderboard,
)
from stock_processing_service.ports.database_gateway_stock_facade import DatabaseGatewayStockFacade


def _row(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if is_dataclass(row):
        return asdict(row)
    return dict(row)


class StockWriteGatewayAdapter:
    def __init__(self, db_gateway: DatabaseGatewayStockFacade) -> None:
        self._db = db_gateway

    async def upsert_stock_daily_strategy_snapshot_rows(self, rows: list[StockDailyStrategySnapshot]) -> int:
        fn = getattr(self._db, "upsert_stock_daily_strategy_snapshot_rows", None)
        if callable(fn):
            return await fn([_row(r) for r in rows])
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_stock_daily_strategy_snapshot_rows")

    async def upsert_subject_stock_daily_snapshot_rows(self, rows: list[SubjectStockDailySnapshot]) -> int:
        return await self._db.upsert_subject_stock_daily_snapshot_rows([_row(r) for r in rows])

    async def upsert_stock_abnormal_event_rows(self, rows: list[StockAbnormalEvent]) -> int:
        return await self._db.upsert_stock_abnormal_event_rows([_row(r) for r in rows])

    async def upsert_theme_stock_leaderboard_rows(self, rows: list[ThemeStockLeaderboard]) -> int:
        return await self._db.upsert_theme_stock_leaderboard_rows([_row(r) for r in rows])

    async def upsert_pre_market_brief_snapshot(self, doc: PreMarketBriefSnapshot) -> int:
        payload = _row(doc)
        if "brief_doc" in payload and "payload" not in payload:
            payload["payload"] = payload.pop("brief_doc")
        if "source" in payload and "source_name" not in payload:
            payload["source_name"] = payload.pop("source")
        return await self._db.upsert_pre_market_brief_snapshot(payload)

    async def upsert_post_market_recap_snapshot(self, doc: PostMarketRecapSnapshot) -> int:
        payload = _row(doc)
        if "recap_doc" in payload and "payload" not in payload:
            payload["payload"] = payload.pop("recap_doc")
        if "source" in payload and "source_name" not in payload:
            payload["source_name"] = payload.pop("source")
        return await self._db.upsert_post_market_recap_snapshot(payload)

    async def upsert_theme_mainline_identity_registry_rows(
        self, rows: list[dict[str, Any]],
        *,
        allow_historical_overwrite: bool = False,
        allow_unsafe_demotion: bool = False,
    ) -> int:
        fn = getattr(self._db, "upsert_theme_mainline_identity_registry_rows", None)
        if callable(fn):
            return await fn(
                rows,
                allow_historical_overwrite=allow_historical_overwrite,
                allow_unsafe_demotion=allow_unsafe_demotion,
            )
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_theme_mainline_identity_registry_rows")

    async def upsert_mainline_identity_review_queue_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_mainline_identity_review_queue_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_mainline_identity_review_queue_rows")

    async def upsert_strong_watch_pool_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_strong_watch_pool_rows", None)
        if callable(fn):
            return await fn(rows)
        return 0

    async def apply_lifecycle_downgrade(
        self, trade_date, deactivate_fade_days: int = 2
    ) -> int:
        fn = getattr(self._db, "apply_lifecycle_downgrade", None)
        if callable(fn):
            return await fn(trade_date, deactivate_fade_days)
        return 0

    async def upsert_strong_watch_history_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_strong_watch_history_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_strong_watch_history_rows")

    async def upsert_theme_cycle_evidence_daily_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_theme_cycle_evidence_daily_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_theme_cycle_evidence_daily_rows")

    async def upsert_theme_cycle_judgement_v2_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_theme_cycle_judgement_v2_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_theme_cycle_judgement_v2_rows")

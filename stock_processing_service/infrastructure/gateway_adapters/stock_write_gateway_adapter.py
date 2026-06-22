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

    async def upsert_source_raw_snapshot(self, row: dict[str, Any]) -> int:
        fn = getattr(self._db, "upsert_source_raw_snapshot", None)
        if callable(fn):
            return await fn(_row(row))
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_source_raw_snapshot")

    async def upsert_market_data_source_registry_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_market_data_source_registry_rows", None)
        if callable(fn):
            return await fn([_row(r) for r in rows])
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_market_data_source_registry_rows")

    async def upsert_ths_hot_reason_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_ths_hot_reason_snapshot_rows", None)
        if callable(fn):
            return await fn([_row(r) for r in rows])
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_ths_hot_reason_snapshot_rows")

    async def upsert_stock_theme_reason_evidence_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_stock_theme_reason_evidence_rows", None)
        if callable(fn):
            return await fn([_row(r) for r in rows])
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_stock_theme_reason_evidence_rows")

    async def upsert_subject_stock_daily_snapshot_rows(self, rows: list[SubjectStockDailySnapshot]) -> int:
        return await self._db.upsert_subject_stock_daily_snapshot_rows([_row(r) for r in rows])

    async def upsert_stock_abnormal_event_rows(self, rows: list[StockAbnormalEvent]) -> int:
        return await self._db.upsert_stock_abnormal_event_rows([_row(r) for r in rows])

    async def upsert_theme_stock_leaderboard_rows(self, rows: list[ThemeStockLeaderboard]) -> int:
        return await self._db.upsert_theme_stock_leaderboard_rows([_row(r) for r in rows])

    async def upsert_pre_market_brief_snapshot(self, doc: PreMarketBriefSnapshot, force: bool = False) -> int:
        payload = _row(doc)
        if "brief_doc" in payload and "payload" not in payload:
            payload["payload"] = payload.pop("brief_doc")
        if "source" in payload and "source_name" not in payload:
            payload["source_name"] = payload.pop("source")
        try:
            return await self._db.upsert_pre_market_brief_snapshot(payload, force=force)
        except TypeError:
            if force:
                raise
            return await self._db.upsert_pre_market_brief_snapshot(payload)

    async def upsert_post_market_recap_snapshot(self, doc: PostMarketRecapSnapshot) -> int:
        payload = _row(doc)
        if "recap_doc" in payload and "payload" not in payload:
            payload["payload"] = payload.pop("recap_doc")
        if "source" in payload and "source_name" not in payload:
            payload["source_name"] = payload.pop("source")
        return await self._db.upsert_post_market_recap_snapshot(payload)

    async def upsert_post_market_setup_plan_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_post_market_setup_plan_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_post_market_setup_plan_rows")

    async def upsert_stock_f10_capital_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_stock_f10_capital_snapshot_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_stock_f10_capital_snapshot_rows")

    async def upsert_one_to_two_candidate_feature_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_one_to_two_candidate_feature_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_one_to_two_candidate_feature_rows")

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

    async def upsert_mainline_daily_state_rows(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        fn = getattr(self._db, "upsert_mainline_daily_state_rows", None)
        if callable(fn):
            return await fn(rows)
        return 0

    async def upsert_mainline_state_daily_rows(self, rows: list[dict[str, Any]]) -> int:
        """Compatibility alias for BuildMainlineStateJob."""
        if not rows:
            return 0
        fn = getattr(self._db, "upsert_mainline_state_daily_rows", None)
        if callable(fn):
            return await fn(rows)
        return 0

    async def upsert_mainline_state_transition_rows(self, rows: list[dict[str, Any]]) -> int:
        """Compatibility alias for BuildMainlineStateJob."""
        if not rows:
            return 0
        fn = getattr(self._db, "upsert_mainline_state_transition_rows", None)
        if callable(fn):
            return await fn(rows)
        return 0

    async def upsert_strong_watch_pool_rows(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        fn = getattr(self._db, "upsert_strong_watch_pool_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_strong_watch_pool_rows")

    async def upsert_weak_to_strong_candidate_pool_rows(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        fn = getattr(self._db, "upsert_weak_to_strong_candidate_pool_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGatewayStockFacade missing upsert_weak_to_strong_candidate_pool_rows")

    async def recompute_strong_watch_window_days(self, stock_ids: list[str]) -> int:
        if not stock_ids:
            return 0
        fn = getattr(self._db, "recompute_strong_watch_window_days", None)
        if callable(fn):
            return await fn(stock_ids)
        raise RuntimeError("DatabaseGatewayStockFacade missing recompute_strong_watch_window_days")

    async def promote_strong_watch_candidates(self, trade_date) -> int:
        fn = getattr(self._db, "promote_strong_watch_candidates", None)
        if callable(fn):
            return await fn(trade_date)
        raise RuntimeError("DatabaseGatewayStockFacade missing promote_strong_watch_candidates")

    async def prune_strong_watch_pool(self, trade_date, weakening_min_score: float = 62.0) -> int:
        fn = getattr(self._db, "prune_strong_watch_pool", None)
        if callable(fn):
            return await fn(trade_date, weakening_min_score)
        raise RuntimeError("DatabaseGatewayStockFacade missing prune_strong_watch_pool")

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

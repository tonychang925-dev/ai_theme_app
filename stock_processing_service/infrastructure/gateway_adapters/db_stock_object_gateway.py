from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from stock_processing_service.infrastructure.gateway_adapters.json_output import (
    dump_json_only,
    dump_json_only_rows,
    is_json_only_mode,
)


class DBStockObjectGateway:
    """Adapter over DatabaseGateway for stock object-layer persistence."""

    def __init__(self, db_gateway: Any) -> None:
        self._db = db_gateway

    @staticmethod
    def _to_dict(obj: Any) -> dict[str, Any]:
        if obj is None:
            return {}
        if isinstance(obj, dict):
            payload = dict(obj)
        elif is_dataclass(obj):
            payload = asdict(obj)
        else:
            to_dict = getattr(obj, "to_dict", None)
            if callable(to_dict):
                payload = dict(to_dict())
            else:
                payload = dict(obj)
        # Snapshot compatibility bridge: domain snapshot uses *_doc/source,
        # DB manager expects payload/source_name.
        if "payload" not in payload:
            if "brief_doc" in payload:
                payload["payload"] = payload.get("brief_doc") or {}
            elif "recap_doc" in payload:
                payload["payload"] = payload.get("recap_doc") or {}
        if "source_name" not in payload and "source" in payload:
            payload["source_name"] = payload.get("source") or "stock_processing_service"
        return payload

    async def upsert_stock_daily_strategy_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        if is_json_only_mode():
            return dump_json_only_rows(object_name="stock_daily_strategy_snapshot", rows=rows)
        fn = getattr(self._db, "upsert_stock_daily_strategy_snapshot_rows", None)
        if callable(fn):
            return await fn(rows)
        return 0

    async def upsert_subject_stock_daily_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        return await self.upsert_subject_stock_daily_snapshot(rows)

    async def upsert_stock_abnormal_event_rows(self, rows: list[dict[str, Any]]) -> int:
        return await self.upsert_stock_abnormal_events(rows)

    async def upsert_theme_stock_leaderboard_rows(self, rows: list[dict[str, Any]]) -> int:
        return await self.upsert_theme_stock_leaderboard(rows)

    async def upsert_pre_market_brief_snapshot(self, doc: dict[str, Any]) -> int:
        return await self.upsert_pre_market_snapshot(doc)

    async def upsert_post_market_recap_snapshot(self, doc: dict[str, Any]) -> int:
        return await self.upsert_post_market_snapshot(doc)

    async def upsert_theme_mainline_identity_registry_rows(self, rows: list[dict[str, Any]]) -> int:
        if is_json_only_mode():
            return dump_json_only_rows(object_name="theme_mainline_identity_registry", rows=rows)
        fn = getattr(self._db, "upsert_theme_mainline_identity_registry_rows", None)
        if callable(fn):
            return await fn(rows)
        return len(rows)

    async def upsert_mainline_identity_review_queue_rows(self, rows: list[dict[str, Any]]) -> int:
        if is_json_only_mode():
            return dump_json_only_rows(object_name="mainline_identity_review_queue", rows=rows)
        fn = getattr(self._db, "upsert_mainline_identity_review_queue_rows", None)
        if callable(fn):
            return await fn(rows)
        return len(rows)

    async def upsert_strong_watch_history_rows(self, rows: list[dict[str, Any]]) -> int:
        if is_json_only_mode():
            return dump_json_only_rows(object_name="strong_stock_watch_history", rows=rows)
        fn = getattr(self._db, "upsert_strong_watch_history_rows", None)
        if callable(fn):
            return await fn(rows)
        return len(rows)

    async def upsert_subject_stock_daily_snapshot(self, rows: list[dict[str, Any]]) -> int:
        if is_json_only_mode():
            return dump_json_only_rows(object_name="subject_stock_daily_snapshot", rows=rows)
        return await self._db.upsert_subject_stock_daily_snapshot_rows(rows)

    async def upsert_stock_abnormal_events(self, rows: list[dict[str, Any]]) -> int:
        if is_json_only_mode():
            return dump_json_only_rows(object_name="stock_abnormal_event", rows=rows)
        return await self._db.upsert_stock_abnormal_event_rows(rows)

    async def upsert_theme_stock_leaderboard(self, rows: list[dict[str, Any]]) -> int:
        if is_json_only_mode():
            return dump_json_only_rows(object_name="theme_stock_leaderboard", rows=rows)
        return await self._db.upsert_theme_stock_leaderboard_rows(rows)

    async def upsert_pre_market_snapshot(self, row: dict[str, Any]) -> int:
        payload = self._to_dict(row)
        if is_json_only_mode():
            return dump_json_only(object_name="pre_market_brief_snapshot", payload=payload)
        return await self._db.upsert_pre_market_brief_snapshot(payload)

    async def upsert_post_market_snapshot(self, row: dict[str, Any]) -> int:
        payload = self._to_dict(row)
        if is_json_only_mode():
            return dump_json_only(object_name="post_market_recap_snapshot", payload=payload)
        return await self._db.upsert_post_market_recap_snapshot(payload)

    async def query_stock_daily_snapshot(self, trade_date: date) -> list[dict[str, Any]]:
        rows = await self._db.get_stock_daily_snapshot_by_trade_date(trade_date)
        return [dict(row) for row in rows]

    async def query_stock_abnormal_events(self, trade_date: date) -> list[dict[str, Any]]:
        row = await self._db.get_existing_post_market_recap_snapshot(trade_date)
        if not row:
            return []
        payload = row.get("payload") or {}
        return payload.get("stock_abnormal_event_rows", [])

    async def query_theme_stock_leaderboard(self, trade_date: date) -> list[dict[str, Any]]:
        row = await self._db.get_existing_post_market_recap_snapshot(trade_date)
        if not row:
            return []
        payload = row.get("payload") or {}
        return payload.get("theme_stock_leaderboard_rows", [])

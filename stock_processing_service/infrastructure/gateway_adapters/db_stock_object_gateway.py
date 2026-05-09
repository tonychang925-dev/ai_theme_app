from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any


class DBStockObjectGateway:
    """Adapter over DatabaseGateway for stock object-layer persistence."""

    def __init__(self, db_gateway: Any) -> None:
        self._db = db_gateway

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)
        attr = getattr(self._db, name, None)
        if attr is None:
            raise AttributeError(f"DatabaseGateway missing method: {name}")
        return attr

    @staticmethod
    def _json_safe(obj: Any) -> Any:
        from decimal import Decimal
        if isinstance(obj, dict):
            return {k: DBStockObjectGateway._json_safe(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [DBStockObjectGateway._json_safe(i) for i in obj]
        if isinstance(obj, Decimal):
            return float(obj)
        return obj

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
        fn = getattr(self._db, "upsert_stock_daily_strategy_snapshot_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_stock_daily_strategy_snapshot_rows")

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
        fn = getattr(self._db, "upsert_theme_mainline_identity_registry_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_theme_mainline_identity_registry_rows")

    async def upsert_mainline_identity_review_queue_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_mainline_identity_review_queue_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_mainline_identity_review_queue_rows")

    async def upsert_strong_watch_history_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_strong_watch_history_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_strong_watch_history_rows")

    async def upsert_theme_cycle_evidence_daily_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_theme_cycle_evidence_daily_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_theme_cycle_evidence_daily_rows")

    async def upsert_subject_stock_daily_snapshot(self, rows: list[dict[str, Any]]) -> int:
        return await self._db.upsert_subject_stock_daily_snapshot_rows(rows)

    async def upsert_stock_abnormal_events(self, rows: list[dict[str, Any]]) -> int:
        return await self._db.upsert_stock_abnormal_event_rows(rows)

    async def upsert_theme_stock_leaderboard(self, rows: list[dict[str, Any]]) -> int:
        return await self._db.upsert_theme_stock_leaderboard_rows(rows)

    async def upsert_pre_market_snapshot(self, row: dict[str, Any]) -> int:
        payload = self._to_dict(row)
        return await self._db.upsert_pre_market_brief_snapshot(payload)

    async def upsert_post_market_snapshot(self, row: dict[str, Any]) -> int:
        payload = self._json_safe(self._to_dict(row))
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

    async def upsert_auction_watch_universe_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_auction_watch_universe_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_auction_watch_universe_rows")

    async def upsert_stock_daily_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_stock_daily_snapshot_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_stock_daily_snapshot_rows")

    async def upsert_pre_market_auction_snapshot_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_pre_market_auction_snapshot_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_pre_market_auction_snapshot_rows")

    async def upsert_dragon_tiger_object_rows(self, rows: list[dict[str, Any]]) -> int:
        fn = getattr(self._db, "upsert_dragon_tiger_object_rows", None)
        if callable(fn):
            return await fn(rows)
        raise RuntimeError("DatabaseGateway missing upsert_dragon_tiger_object_rows")

    async def query_theme_stock_leaderboard(self, trade_date: date) -> list[dict[str, Any]]:
        row = await self._db.get_existing_post_market_recap_snapshot(trade_date)
        if not row:
            return []
        payload = row.get("payload") or {}
        return payload.get("theme_stock_leaderboard_rows", [])

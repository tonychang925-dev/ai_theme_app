from __future__ import annotations

from datetime import date
from typing import Any

class DBThemeDataGateway:
    """Adapter over DatabaseGateway for theme-domain data."""

    def __init__(self, db_gateway: Any) -> None:
        self._db = db_gateway

    async def get_trade_calendar(self, trade_date: date) -> dict[str, Any]:
        return await self._db.get_trade_calendar(trade_date)

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return await self._db.get_stock_daily_bars(trade_date, stock_ids=stock_ids)

    async def get_stock_auction_snapshot(self, trade_date: date, stock_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return await self._db.get_stock_auction_snapshot(trade_date, stock_ids=stock_ids)

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date) -> list[dict[str, Any]]:
        rows = await self._db.get_subject_stock_pool_by_trade_date(trade_date)
        return [dict(row) for row in rows]

    async def get_subject_context_by_subject_keys(self, subject_keys: list[str], trade_date: date) -> list[dict[str, Any]]:
        rows = await self._db.get_subject_context_by_subject_keys(subject_keys, trade_date)
        return [dict(row) for row in rows]

    async def get_prior_stock_daily_snapshots(
        self,
        trade_date: date,
        lookback_days: int,
        stock_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        rows = await self._db.get_prior_stock_daily_snapshots(
            trade_date=trade_date,
            lookback_days=lookback_days,
            stock_ids=stock_ids,
        )
        return [dict(row) for row in rows]

    async def get_existing_pre_market_brief_snapshot(self, trade_date: date) -> dict[str, Any] | None:
        row = await self._db.get_existing_pre_market_brief_snapshot(trade_date)
        return dict(row) if row else None

    async def get_existing_post_market_recap_snapshot(self, trade_date: date) -> dict[str, Any] | None:
        row = await self._db.get_existing_post_market_recap_snapshot(trade_date)
        return dict(row) if row else None

    async def get_theme_events(self, trade_date: date) -> list[dict[str, Any]]:
        snapshot = await self._db.get_existing_post_market_recap_snapshot(trade_date)
        if not snapshot:
            return []
        payload = snapshot.get("payload") or {}
        return payload.get("theme_events", [])

    async def get_theme_stock_pool(self, trade_date: date) -> list[dict[str, Any]]:
        return await self.get_subject_stock_pool_by_trade_date(trade_date)

    async def get_theme_tree(self, trade_date: date | None = None) -> list[dict[str, Any]]:
        themes = await self._db.get_all_active_themes(limit=5000)
        result: list[dict[str, Any]] = []
        for theme in themes:
            if isinstance(theme, dict):
                result.append(dict(theme))
            else:
                result.append(theme.to_dict())
        return result

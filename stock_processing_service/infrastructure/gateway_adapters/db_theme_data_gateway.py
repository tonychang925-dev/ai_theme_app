from __future__ import annotations

from datetime import date
from typing import Any

class DBThemeDataGateway:
    """Adapter over DatabaseGateway for theme-domain data."""

    def __init__(self, db_gateway: Any) -> None:
        self._db = db_gateway

    @staticmethod
    def _as_dict(row: Any) -> dict[str, Any]:
        """Convert asyncpg Record or dict to plain dict."""
        if row is None:
            return {}
        if isinstance(row, dict):
            return row
        return dict(row)

    async def get_trade_calendar(self, trade_date: date) -> dict[str, Any]:
        return await self._db.get_trade_calendar(trade_date)

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[dict[str, Any]]:
        return await self._db.get_stock_daily_bars(trade_date, stock_ids=stock_ids)

    async def get_stock_daily_bars_range(
        self,
        start_date: date,
        end_date: date,
        stock_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        return await self._db.get_stock_daily_bars_range(start_date, end_date, stock_ids=stock_ids)

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

    async def get_mainline_identity_by_subject_keys(
        self,
        subject_keys: list[str],
        trade_date: date,
    ) -> list[dict[str, Any]]:
        rows = await self._db.get_mainline_identity_by_subject_keys(subject_keys, trade_date)
        return [dict(row) for row in rows]

    async def get_mainline_cycle_by_subject_keys(
        self,
        subject_keys: list[str],
        trade_date: date,
    ) -> list[dict[str, Any]]:
        rows = await self._db.get_mainline_cycle_by_subject_keys(subject_keys, trade_date)
        return [dict(row) for row in rows]

    async def get_theme_events(self, trade_date: date) -> list[dict[str, Any]]:
        snapshot = await self._db.get_existing_post_market_recap_snapshot(trade_date)
        if not snapshot:
            return []
        payload = snapshot.get("payload") or {}
        return payload.get("theme_events", [])

    async def get_subject_event_stats(
        self,
        trade_date,
        subject_keys: list[str] | None = None,
        lookback_days: int = 7,
    ) -> list:
        """按 subject_keys 聚合事件统计 → SubjectEventStatsDTO 列表。"""
        from stock_processing_service.contracts.dto import SubjectEventStatsDTO

        rows = await self._db.get_subject_event_stats(
            trade_date=trade_date,
            subject_keys=subject_keys,
            lookback_days=lookback_days,
        )
        results: list = []
        for row in rows:
            r = self._as_dict(row)
            results.append(
                SubjectEventStatsDTO(
                    subject_key=str(r.get("subject_key", "")),
                    theme_name=str(r.get("theme_name", "")),
                    today_event_count=int(r.get("today_event_count") or 0),
                    recent_event_count=int(r.get("recent_event_count") or 0),
                    distinct_event_days=int(r.get("distinct_event_days") or 0),
                    key_event_count=int(r.get("key_event_count") or 0),
                    sample_summaries=list(r.get("sample_summaries") or []),
                )
            )
        return results

    async def get_subject_cycle_evidence_daily(
        self,
        trade_date,
        subject_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """读取旧链 theme_cycle_evidence_daily 预计算证据。"""
        rows = await self._db.get_subject_cycle_evidence_daily(
            trade_date=trade_date,
            subject_keys=subject_keys,
        )
        return [self._as_dict(r) for r in rows]

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

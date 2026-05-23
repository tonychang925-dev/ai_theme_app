from __future__ import annotations

from datetime import date
from typing import Any

class DBThemeDataGateway:
    """Adapter over DatabaseGateway for theme-domain data."""

    def __init__(self, db_gateway: Any) -> None:
        self._db = db_gateway

    def __getattr__(self, name: str):
        """将未显式定义的方法委托给底层 DatabaseGateway。"""
        if name.startswith("_"):
            raise AttributeError(name)
        attr = getattr(self._db, name, None)
        if attr is None:
            raise AttributeError(f"DatabaseGateway missing method: {name}")
        return attr

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

    async def get_mainline_identity_rule_inputs(
        self,
        trade_date: date,
        subject_keys: list[str],
    ) -> list[dict[str, Any]]:
        rows = await self._db.get_mainline_identity_rule_inputs(
            trade_date=trade_date,
            subject_keys=subject_keys,
        )
        return [self._as_dict(row) for row in rows]

    async def get_mainline_cycle_by_subject_keys(
        self,
        subject_keys: list[str],
        trade_date: date,
    ) -> list[dict[str, Any]]:
        rows = await self._db.get_mainline_cycle_by_subject_keys(subject_keys, trade_date)
        return [dict(row) for row in rows]

    async def get_prior_mainline_state_daily(self, trade_date: date) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_prior_mainline_state_daily", None)
        if callable(fn):
            rows = await fn(trade_date)
            return [self._as_dict(r) for r in rows]
        return []

    async def get_prior_strong_watch_pool_rows(
        self,
        trade_date: date,
        lookback_days: int,
    ) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_prior_strong_watch_pool_rows", None)
        if not callable(fn):
            raise RuntimeError("DatabaseGateway missing get_prior_strong_watch_pool_rows")
        rows = await fn(trade_date=trade_date, lookback_days=lookback_days)
        return [self._as_dict(row) for row in rows]

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

    async def get_subject_market_stats(
        self, trade_date, subject_keys: list[str] | None = None, lookback_days: int = 7
    ) -> list[dict[str, Any]]:
        """批量查询 subject 级市场统计。"""
        rows = await self._db.get_subject_market_stats(
            trade_date=trade_date, subject_keys=subject_keys, lookback_days=lookback_days
        )
        return [self._as_dict(r) for r in rows]

    async def get_subject_heat_stats(
        self, trade_date, subject_keys: list[str] | None = None, lookback_days: int = 5
    ) -> list[dict[str, Any]]:
        """批量查询 subject 级热度统计。"""
        rows = await self._db.get_subject_heat_stats(
            trade_date=trade_date, subject_keys=subject_keys, lookback_days=lookback_days
        )
        return [self._as_dict(r) for r in rows]

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

    async def get_auction_board_leaders(self, trade_date) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_auction_board_leaders", None)
        if callable(fn):
            return [self._as_dict(r) for r in await fn(trade_date)]
        raise RuntimeError("DatabaseGateway missing get_auction_board_leaders")

    async def get_auction_mainlines(self, trade_date) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_auction_mainlines", None)
        if callable(fn):
            return [self._as_dict(r) for r in await fn(trade_date)]
        raise RuntimeError("DatabaseGateway missing get_auction_mainlines")

    async def get_auction_cycles(self, trade_date) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_auction_cycles", None)
        if callable(fn):
            return [self._as_dict(r) for r in await fn(trade_date)]
        raise RuntimeError("DatabaseGateway missing get_auction_cycles")

    async def get_auction_watch_universe(self, trade_date) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_auction_watch_universe", None)
        if callable(fn):
            return [self._as_dict(r) for r in await fn(trade_date)]
        raise RuntimeError("DatabaseGateway missing get_auction_watch_universe")

    async def get_w2s_candidates_by_next_date(self, confirm_date) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_w2s_candidates_by_next_date", None)
        if callable(fn):
            return [self._as_dict(r) for r in await fn(confirm_date)]
        raise RuntimeError("DatabaseGateway missing get_w2s_candidates_by_next_date")

    async def get_strong_watch_seed_rows(self, trade_date, lookback_days: int = 7) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_strong_watch_seed_rows", None)
        if callable(fn):
            return [self._as_dict(r) for r in await fn(trade_date, lookback_days)]
        raise RuntimeError("DatabaseGateway missing get_strong_watch_seed_rows")

    async def get_subject_board_stats(self, trade_date) -> list[dict[str, Any]]:
        fn = getattr(self._db, "get_subject_board_stats", None)
        if callable(fn):
            return [self._as_dict(r) for r in await fn(trade_date)]
        raise RuntimeError("DatabaseGateway missing get_subject_board_stats")

    async def get_post_market_report_context(
        self,
        trade_date,
        subject_keys: list[str] | None = None,
        stock_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """显式委托到 DatabaseGateway.get_post_market_report_context。

        不依赖 __getattr__ 双跳，确保 BuildPostMarketRecapJob 能可靠获取复盘上下文。
        """
        fn = getattr(self._db, "get_post_market_report_context", None)
        if callable(fn):
            return await fn(
                trade_date=trade_date,
                subject_keys=subject_keys,
                stock_ids=stock_ids,
            )
        raise RuntimeError("DatabaseGateway missing get_post_market_report_context")

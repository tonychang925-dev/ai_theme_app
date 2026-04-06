import asyncio
import json
from typing import Any, Dict, List, Optional

import asyncpg

from stock_service.config import DEFAULT_CONFIG
from stock_service.repositories.report_repository import ReportRepository
from stock_service.services.recap_service import RecapService
from theme_service.repositories.phase1_read_repository import Phase1ReadRepository


class FrontendBffRepository:
    def __init__(self, database_url: Optional[str] = None):
        self.phase1_repo = Phase1ReadRepository(database_url=database_url)
        self.report_repo = ReportRepository(DEFAULT_CONFIG)
        self.recap_service = RecapService(self.report_repo)

    async def initialize(self) -> None:
        await self.phase1_repo.initialize()
        await self.report_repo.initialize()

    async def close(self) -> None:
        await self.phase1_repo.close()
        await self.report_repo.close()

    @property
    def _pool(self) -> asyncpg.Pool:
        return self.phase1_repo._pool

    async def fetch_intel_feed_view(
        self,
        feed_date: Optional[str] = None,
        session: str = "all",
        item_type: str = "all",
        subject_key: Optional[str] = None,
        stock_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        target_date = feed_date
        fallback_from: Optional[str] = None

        items = await self.phase1_repo.fetch_intel_feed(
            feed_date=target_date,
            session=session,
            item_type=item_type,
            subject_key=subject_key,
            stock_id=stock_id,
            limit=limit,
        )

        if item_type in {"all", "event"} and not items and not feed_date:
            latest_date = await self.phase1_repo.fetch_latest_intel_event_date(
                subject_key=subject_key,
                stock_id=stock_id,
            )
            if latest_date and latest_date != target_date:
                fallback_from = target_date
                target_date = latest_date
                items = await self.phase1_repo.fetch_intel_feed(
                    feed_date=target_date,
                    session=session,
                    item_type=item_type,
                    subject_key=subject_key,
                    stock_id=stock_id,
                    limit=limit,
                )

        sources = sorted({str(item.get("source_type")) for item in items if item.get("source_type")})
        return {
            "items": items,
            "count": len(items),
            "date": target_date,
            "session": session,
            "type": item_type,
            "diagnostics": {
                "partial": False,
                "sources": sources,
                "fallback_from": fallback_from,
            },
        }

    async def fetch_theme_workspace_view(
        self,
        subject_key: str,
        include_history: bool = True,
        include_children: bool = True,
        include_stocks: bool = True,
        include_leaders: bool = False,
        stock_mapping_scope: str = "pool",
        history_limit: int = 20,
        children_limit: int = 50,
        stocks_limit: int = 50,
    ) -> Optional[Dict[str, Any]]:
        detail = await self.phase1_repo.fetch_theme_detail(subject_key)
        if not detail:
            return None

        partial = False
        missing_sections: List[str] = []

        async def safe_fetch(name: str, coro):
            nonlocal partial
            try:
                return await coro
            except Exception:
                partial = True
                missing_sections.append(name)
                return None

        history = None
        children = None
        stocks = None

        tasks = []
        if include_history:
            tasks.append(("history", safe_fetch("history", self.phase1_repo.fetch_history(subject_key, limit=history_limit))))
        if include_children:
            tasks.append(("children", safe_fetch("children", self.phase1_repo.fetch_children(subject_key, limit=children_limit))))
        if include_stocks:
            tasks.append((
                "stocks",
                safe_fetch(
                    "stocks",
                    self.phase1_repo.fetch_stocks_by_theme(
                        subject_key,
                        mapping_scope=stock_mapping_scope,
                        include_leaders=include_leaders,
                        limit=stocks_limit,
                    ),
                ),
            ))

        if tasks:
            results = await asyncio.gather(*(task for _, task in tasks))
            for (name, _), result in zip(tasks, results):
                if name == "history":
                    history = result
                elif name == "children":
                    children = result
                elif name == "stocks":
                    stocks = result

        return {
            "subject_key": subject_key,
            "detail": detail,
            "history": history,
            "children": children,
            "stocks": stocks,
            "diagnostics": {
                "partial": partial,
                "missing_sections": missing_sections,
            },
        }

    async def fetch_stock_detail_simple(self, stock_id: str) -> Optional[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            stock_id,
            name,
            price,
            pct_chg,
            amount,
            market_value,
            high,
            low,
            vol,
            source_updated_at,
            updated_at
        FROM stocks
        WHERE stock_id = $1
        LIMIT 1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, stock_id)
        return dict(row) if row else None

    async def fetch_stock_money_flow_view(self, stock_id: str) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            trade_date,
            subject_key,
            theme_name,
            role_label,
            role_enhanced,
            candidate_rank,
            money_flow_score,
            money_flow_tier,
            explanation,
            sources
        FROM money_flow_enhanced
        WHERE split_part(stock_id, '.', 1) = $1
        ORDER BY trade_date DESC, money_flow_score DESC, candidate_rank ASC
        LIMIT 20
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, stock_id)
        results = []
        for row in rows:
            item = dict(row)
            if isinstance(item.get("explanation"), str):
                try:
                    item["explanation"] = json.loads(item["explanation"])
                except Exception:
                    item["explanation"] = []
            if isinstance(item.get("sources"), str):
                try:
                    item["sources"] = json.loads(item["sources"])
                except Exception:
                    item["sources"] = []
            results.append(item)
        return results

    async def fetch_stock_dragon_tiger_view(self, stock_id: str) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            trade_date,
            stock_name,
            reason,
            net_amount,
            institution_seat_count,
            seat_summary,
            source_trace_id
        FROM dragon_tiger_object
        WHERE split_part(stock_id, '.', 1) = $1
        ORDER BY trade_date DESC, ABS(net_amount) DESC
        LIMIT 10
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, stock_id)
        results = []
        for row in rows:
            item = dict(row)
            if isinstance(item.get("seat_summary"), str):
                try:
                    item["seat_summary"] = json.loads(item["seat_summary"])
                except Exception:
                    item["seat_summary"] = []
            results.append(item)
        return results

    async def fetch_stock_auction_validation_view(self, stock_id: str) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
            trade_date,
            theme_name,
            role_label,
            auction_signal_level,
            auction_signal_score,
            signal_type,
            action_today,
            close_pct,
            hit_limit_up,
            validation_result,
            signal_validated,
            validation_note
        FROM pre_market_auction_signal_validation
        WHERE split_part(stock_id, '.', 1) = $1
        ORDER BY trade_date DESC, auction_signal_score DESC
        LIMIT 20
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, stock_id)
        return [dict(row) for row in rows]

    async def fetch_stock_kline_view(self, stock_id: str) -> Dict[str, Any]:
        await self.initialize()
        position_sql = """
        SELECT
            trade_date,
            stock_name,
            position_label,
            distance_to_20d_high,
            distance_to_60d_high,
            distance_to_120d_high,
            distance_to_all_time_high,
            ma_alignment_status,
            trend_strength_score,
            conclusion,
            evidence
        FROM stock_position_judgement
        WHERE split_part(stock_id, '.', 1) = $1
        ORDER BY trade_date DESC
        LIMIT 1
        """
        pattern_sql = """
        SELECT
            trade_date,
            stock_name,
            pattern_labels,
            volume_pattern_status,
            breakout_status,
            pullback_status,
            risk_pattern_status,
            conclusion,
            evidence
        FROM stock_pattern_judgement
        WHERE split_part(stock_id, '.', 1) = $1
        ORDER BY trade_date DESC
        LIMIT 1
        """
        async with self._pool.acquire() as conn:
            position_row = await conn.fetchrow(position_sql, stock_id)
            pattern_row = await conn.fetchrow(pattern_sql, stock_id)
        position = dict(position_row) if position_row else None
        pattern = dict(pattern_row) if pattern_row else None
        for item in (position, pattern):
            if not item:
                continue
            for key in ("evidence", "pattern_labels"):
                if isinstance(item.get(key), str):
                    try:
                        item[key] = json.loads(item[key])
                    except Exception:
                        item[key] = []
        return {
            "position": position,
            "pattern": pattern,
        }

    async def fetch_stock_workspace_view(
        self,
        stock_id: str,
        include_themes: bool = True,
        include_leaders: bool = False,
        mapping_scope: str = "pool",
        themes_limit: int = 50,
    ) -> Optional[Dict[str, Any]]:
        stock_detail = await self.fetch_stock_detail_simple(stock_id)
        partial = False
        missing_sections: List[str] = []
        themes = None
        money_flow = None
        dragon_tiger = None
        auction_validation = None
        kline = None

        if include_themes:
            try:
                themes = await self.phase1_repo.fetch_themes_by_stock(
                    stock_id,
                    mapping_scope=mapping_scope,
                    include_leaders=include_leaders,
                    limit=themes_limit,
                )
                if not themes and mapping_scope == "pool":
                    themes = await self.phase1_repo.fetch_themes_by_stock(
                        stock_id,
                        mapping_scope="all",
                        include_leaders=include_leaders,
                        limit=themes_limit,
                    )
            except Exception:
                partial = True
                missing_sections.append("themes")
                themes = None

        try:
            money_flow = await self.fetch_stock_money_flow_view(stock_id)
        except Exception:
            partial = True
            missing_sections.append("money_flow")
            money_flow = None

        try:
            dragon_tiger = await self.fetch_stock_dragon_tiger_view(stock_id)
        except Exception:
            partial = True
            missing_sections.append("dragon_tiger")
            dragon_tiger = None

        try:
            auction_validation = await self.fetch_stock_auction_validation_view(stock_id)
        except Exception:
            partial = True
            missing_sections.append("auction_validation")
            auction_validation = None

        try:
            kline = await self.fetch_stock_kline_view(stock_id)
        except Exception:
            partial = True
            missing_sections.append("kline")
            kline = None

        if not stock_detail and not themes and not money_flow and not dragon_tiger and not auction_validation and not kline:
            return None

        return {
            "stock_id": stock_id,
            "stock_detail": stock_detail,
            "themes": themes,
            "money_flow": money_flow,
            "dragon_tiger": dragon_tiger,
            "auction_validation": auction_validation,
            "kline": kline,
            "diagnostics": {
                "partial": partial,
                "missing_sections": missing_sections,
            },
        }

    async def fetch_recap_view(
        self,
        trade_date: str,
        report_type: str = "post_market",
    ) -> Dict[str, Any]:
        if report_type == "pre_market":
            report = await self.recap_service.build_pre_market_report(trade_date)
        else:
            report = await self.recap_service.build_post_market_report(trade_date)
        return {
            "report_type": report.report_type,
            "trade_date": report.trade_date,
            "title": report.title,
            "summary": report.summary,
            "highlights": report.highlights,
            "sections": [
                {"heading": heading, "items": items}
                for heading, items in report.sections
            ],
        }

    async def fetch_recap_defaults(self) -> Dict[str, Any]:
        await self.report_repo.initialize()
        sql = """
        SELECT
          (SELECT MAX(trade_date)::text FROM theme_mainline_judgement) AS latest_post_market_date,
          (SELECT MAX(trade_date)::text FROM pre_market_execution_plan) AS latest_pre_market_date
        """
        assert self.report_repo.pool is not None
        async with self.report_repo.pool.acquire() as conn:
            row = await conn.fetchrow(sql)
        payload = dict(row) if row else {}
        return {
            "latest_post_market_date": payload.get("latest_post_market_date"),
            "latest_pre_market_date": payload.get("latest_pre_market_date"),
        }

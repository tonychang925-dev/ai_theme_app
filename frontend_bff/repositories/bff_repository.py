import asyncio
import json
from datetime import date
from pathlib import Path
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

    def _load_abnormal_fallback_lines(self, trade_date: str) -> List[str]:
        path = Path(
            f"/Users/admin/Desktop/ai_theme_app/tmp/stock_abnormal_fallback_{trade_date}.json"
        )
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

        rows = payload.get("rows") or []
        lines: List[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            labels = [
                str(item).strip()
                for item in (row.get("abnormal_labels") or [])
                if str(item).strip()
            ]
            evidence = [
                str(item).strip()
                for item in (row.get("evidence") or [])
                if str(item).strip()
            ]
            capital_note_parts = []
            hot_names = [
                str(item).strip()
                for item in (row.get("hot_money_buy_names") or [])
                if str(item).strip()
            ]
            if int(row.get("main_net_inflow_rank_in_theme") or 0) > 0:
                capital_note_parts.append(
                    f"题材内净流入排名 {int(row.get('main_net_inflow_rank_in_theme') or 0)}"
                )
            if hot_names:
                capital_note_parts.append(f"游资买入 {'/'.join(hot_names[:3])}")
            if int(row.get("institution_seat_count") or 0) > 0:
                capital_note_parts.append(
                    f"机构席位 {int(row.get('institution_seat_count') or 0)}"
                )

            volume_ratio = next(
                (
                    item.replace("量比 ", "")
                    for item in evidence
                    if item.startswith("量比 ")
                ),
                "--",
            )
            lines.append(
                f"{row.get('theme_name') or '未分类'}："
                f"{row.get('stock_name') or '--'}({row.get('stock_id') or '--'})；"
                f"异动分 {float(row.get('abnormal_composite_score') or 0):.2f}；"
                f"换手率 {float(row.get('turnover_rate') or 0):.2f}%；"
                f"量比 {volume_ratio}；"
                f"成交量/50日均量 {float(row.get('volume_ratio_to_ma50') or 0):.2f}；"
                f"资金 {'；'.join(capital_note_parts) if capital_note_parts else '--'}；"
                f"标签 {'/'.join(labels) if labels else '--'}；"
                f"结论 {row.get('conclusion') or '--'}"
            )
        return lines

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

        if item_type in {"all", "event", "event_review"} and not items and not feed_date:
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
        source_channels = sorted(
            {str(item.get("source_channel")) for item in items if item.get("source_channel")}
        )
        source_channel_counts: Dict[str, int] = {}
        for item in items:
            channel = str(item.get("source_channel") or "")
            if not channel:
                continue
            source_channel_counts[channel] = source_channel_counts.get(channel, 0) + 1
        return {
            "items": items,
            "count": len(items),
            "date": target_date,
            "session": session,
            "type": item_type,
            "diagnostics": {
                "partial": False,
                "sources": sources,
                "source_channels": source_channels,
                "source_channel_counts": source_channel_counts,
                "fallback_from": fallback_from,
            },
        }

    async def fetch_theme_workspace_view(
        self,
        subject_key: str,
        trade_date: Optional[str] = None,
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
        analytics = None

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

        try:
            analytics = await self.fetch_theme_analytics_view(subject_key, trade_date=trade_date)
        except Exception as exc:
            partial = True
            missing_sections.append(f"analytics:{type(exc).__name__}:{exc}")
            analytics = None

        return {
            "subject_key": subject_key,
            "trade_date": trade_date,
            "detail": detail,
            "history": history,
            "children": children,
            "stocks": stocks,
            "analytics": analytics,
            "diagnostics": {
                "partial": partial,
                "missing_sections": missing_sections,
            },
        }

    async def _resolve_theme_trade_date(self, subject_key: str, trade_date: Optional[str]) -> Optional[str]:
        await self.initialize()
        if trade_date:
            return trade_date
        sql = """
        SELECT MAX(trade_date)::text AS trade_date
        FROM theme_mainline_judgement
        WHERE subject_key = $1
        """
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, subject_key)

    async def fetch_theme_analytics_view(self, subject_key: str, trade_date: Optional[str] = None) -> Dict[str, Any]:
        await self.initialize()
        resolved_trade_date = await self._resolve_theme_trade_date(subject_key, trade_date)
        if not resolved_trade_date:
            return {
                "trade_date": trade_date,
                "summary": None,
                "recent_rank": [],
                "leader_stocks": [],
            }
        query_trade_date = date.fromisoformat(resolved_trade_date)

        summary_sql = """
        SELECT
            tmj.trade_date::text AS trade_date,
            tmj.subject_key,
            tmj.theme_name,
            tmj.theme_tier,
            tmj.event_chain_score,
            tmj.market_recognition_score,
            tmj.mainline_stability_score,
            tcj.primary_cycle_stage,
            tcj.action_bias,
            tcj.conclusion,
            te.action_bias AS theme_action_bias,
            te.board_health_status,
            te.board_effect_status,
            te.leader_support_status,
            te.follow_strength_status,
            srd.pct_chg AS latest_pct_chg,
            srd.his_pct_chg AS latest_his_pct_chg,
            srd.heat_name,
            COALESCE(flow.main_net_inflow_sum, 0) AS main_net_inflow_sum,
            COALESCE(flow.top3_main_net_inflow_sum, 0) AS top3_main_net_inflow_sum,
            COALESCE(flow.leader_main_net_inflow, 0) AS leader_main_net_inflow
        FROM theme_mainline_judgement tmj
        LEFT JOIN theme_cycle_judgement tcj
          ON tcj.trade_date = tmj.trade_date
         AND tcj.subject_key = tmj.subject_key
        LEFT JOIN theme_environment_judgement te
          ON te.trade_date = tmj.trade_date
         AND te.subject_key = tmj.subject_key
        LEFT JOIN subject_rank_daily srd
          ON srd.rank_date = tmj.trade_date
         AND srd.subject_key = tmj.subject_key
        LEFT JOIN (
            SELECT
                subject_key,
                trade_date,
                SUM(COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric) AS main_net_inflow_sum,
                SUM(CASE WHEN rank_order <= 3 THEN COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric ELSE 0 END) AS top3_main_net_inflow_sum,
                COALESCE(MAX(CASE WHEN is_leader THEN COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric END), 0) AS leader_main_net_inflow
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $2::date
            GROUP BY subject_key, trade_date
        ) flow
          ON flow.trade_date = tmj.trade_date
         AND flow.subject_key = tmj.subject_key
        WHERE tmj.subject_key = $1
          AND tmj.trade_date = $2::date
        LIMIT 1
        """

        recent_rank_sql = """
        SELECT
            rank_date::text AS rank_date,
            pct_chg,
            his_pct_chg,
            CASE WHEN COALESCE(pct_chg, 0) > 0 THEN TRUE ELSE FALSE END AS red,
            heat_name,
            description
        FROM (
            SELECT
                h.rank_date,
                h.pct_chg,
                h.his_pct_chg,
                h.heat_name,
                h.description,
                h.source_ref,
                ROW_NUMBER() OVER (
                    PARTITION BY
                        h.subject_key,
                        h.rank_date,
                        COALESCE(NULLIF(BTRIM(h.description), ''), '__empty__')
                    ORDER BY
                        CASE h.source_type
                            WHEN 'jyhf_history' THEN 0
                            WHEN 'jyhf_rank_daily' THEN 1
                            WHEN 'event_theme_map' THEN 2
                            ELSE 9
                        END,
                        h.source_ref DESC
                ) AS rn
            FROM vw_theme_history_candidate h
            WHERE h.subject_key = $1
              AND h.rank_date <= $2::date
        ) dedup
        WHERE rn = 1
        ORDER BY rank_date DESC, source_ref DESC
        LIMIT 5
        """

        leader_stocks_sql = """
        SELECT
            c.trade_date::text AS trade_date,
            c.stock_id,
            c.stock_name,
            s.rank_order,
            s.is_leader,
            s.pct_chg,
            s.amount,
            c.turnover_rate,
            c.volume_ratio,
            COALESCE(NULLIF(s.raw_json->>20, ''), '0')::integer AS current_flag,
            COALESCE(NULLIF(s.raw_json->>35, ''), '0')::numeric AS main_net_inflow,
            sp.position_label,
            sp.trend_strength_score,
            spp.pattern_labels,
            mfe.money_flow_tier,
            mfe.role_enhanced
        FROM theme_leader_candidate c
        JOIN subject_stock_daily_snapshot s
          ON s.trade_date = c.trade_date
         AND s.subject_key = c.subject_key
         AND split_part(s.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
        LEFT JOIN stock_position_judgement sp
          ON sp.trade_date = c.trade_date
         AND split_part(sp.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
        LEFT JOIN stock_pattern_judgement spp
          ON spp.trade_date = c.trade_date
         AND split_part(spp.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
        LEFT JOIN money_flow_enhanced mfe
          ON mfe.trade_date = c.trade_date
         AND mfe.subject_key = c.subject_key
         AND split_part(mfe.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
        WHERE c.subject_key = $1
          AND c.trade_date = $2::date
        ORDER BY
            CASE WHEN s.is_leader THEN 0 ELSE 1 END,
            c.candidate_rank ASC,
            COALESCE(NULLIF(s.raw_json->>35, ''), '0')::numeric DESC
        LIMIT 12
        """

        async with self._pool.acquire() as conn:
            summary_row = await conn.fetchrow(summary_sql, subject_key, query_trade_date)
            recent_rank_rows = await conn.fetch(recent_rank_sql, subject_key, query_trade_date)
            leader_stock_rows = await conn.fetch(leader_stocks_sql, subject_key, query_trade_date)

        recent_rank = [dict(row) for row in recent_rank_rows]
        leader_stocks: List[Dict[str, Any]] = []
        for row in leader_stock_rows:
            item = dict(row)
            if isinstance(item.get("pattern_labels"), str):
                try:
                    item["pattern_labels"] = json.loads(item["pattern_labels"])
                except Exception:
                    item["pattern_labels"] = []
            leader_stocks.append(item)

        return {
            "trade_date": resolved_trade_date,
            "summary": dict(summary_row) if summary_row else None,
            "recent_rank": recent_rank,
            "leader_stocks": leader_stocks,
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
        sections = [
            {"heading": heading, "items": items}
            for heading, items in report.sections
        ]
        if report_type == "post_market":
            for section in sections:
                if section["heading"] == "当日异动股与资金行为" and not section["items"]:
                    fallback_lines = self._load_abnormal_fallback_lines(trade_date)
                    if fallback_lines:
                        section["items"] = [
                            "补充说明：当日正式异动口径因缺少龙虎榜/机构/游资等资金聚焦证据未产出结果，以下为按行为异动分排序的补充清单。",
                            *fallback_lines,
                        ]
                if section["heading"] == "龙虎榜" and not section["items"]:
                    section["items"] = [
                        "说明：当日本地龙虎榜原始快照为空，前端暂不展示席位明细。"
                    ]
        return {
            "report_type": report.report_type,
            "trade_date": report.trade_date,
            "title": report.title,
            "summary": report.summary,
            "highlights": report.highlights,
            "sections": sections,
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

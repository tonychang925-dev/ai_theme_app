import asyncio
import json
import logging
import os
import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg

from stock_service.config import DEFAULT_CONFIG
from stock_service.repositories.report_repository import ReportRepository
from stock_service.services.recap_service import RecapService
from theme_service.repositories.phase1_read_repository import Phase1ReadRepository

logger = logging.getLogger(__name__)

# BFF read-source governance switches.
# Default behavior: audit only (no blocking). Set strict=true to hard block process-table reads.
BFF_STRICT_FROZEN_OBJECT_READ = str(os.getenv("BFF_STRICT_FROZEN_OBJECT_READ", "false")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}
BFF_AUDIT_PROCESS_TABLE_READ = str(os.getenv("BFF_AUDIT_PROCESS_TABLE_READ", "true")).lower() in {
    "1",
    "true",
    "yes",
    "on",
}

FROZEN_OBJECT_TABLES = {
    "stock_daily_snapshot",
    "subject_stock_daily_snapshot",
    "stock_abnormal_event",
    "theme_stock_leaderboard",
    "pre_market_brief_snapshot",
    "post_market_recap_snapshot",
}

PROCESS_STATE_TABLES = {
    "theme_mainline_identity_registry",
    "mainline_identity_review_queue",
    "theme_cycle_judgement_v2",
    "mainline_state_daily",
    "mainline_state_transition",
    "strong_stock_watch_pool",
    "strong_stock_watch_history",
    "weak_to_strong_candidate_pool",
    "weak_to_strong_auction_signal",
    "pre_market_execution_plan",
    "pre_market_auction_signal_validation",
}

_TABLE_PATTERN = re.compile(r"\b(?:from|join)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


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

    def _extract_tables(self, sql: str) -> set[str]:
        return {m.group(1).lower() for m in _TABLE_PATTERN.finditer(sql or "")}

    def _audit_and_guard_sql(self, *, endpoint: str, sql: str) -> None:
        tables = self._extract_tables(sql)
        process_hits = sorted(t for t in tables if t in PROCESS_STATE_TABLES)
        if not process_hits:
            return

        if BFF_AUDIT_PROCESS_TABLE_READ:
            logger.warning(
                "[BFF_READ_AUDIT] endpoint=%s reads process tables=%s strict=%s",
                endpoint,
                ",".join(process_hits),
                BFF_STRICT_FROZEN_OBJECT_READ,
            )

        if BFF_STRICT_FROZEN_OBJECT_READ:
            raise PermissionError(
                f"blocked process-table read in endpoint={endpoint}, tables={process_hits}. "
                f"Only frozen objects should be externally consumed: {sorted(FROZEN_OBJECT_TABLES)}"
            )

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

    async def fetch_strong_stock_watch_view(
        self,
        trade_date: Optional[str] = None,
        window_days: int = 7,
        limit: int = 200,
        latest_per_stock: bool = True,
        include_removed: bool = False,
        stock_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.initialize()
        safe_window = min(max(int(window_days), 1), 30)
        safe_limit = min(max(int(limit), 1), 500)

        if trade_date:
            try:
                end_date = date.fromisoformat(trade_date)
            except ValueError:
                raise ValueError(f"invalid trade_date: {trade_date}")
        else:
            sql_latest = """
            SELECT MAX(trade_date) AS trade_date
            FROM strong_stock_watch_history
            """
            async with self._pool.acquire() as conn:
                self._audit_and_guard_sql(endpoint="fetch_strong_stock_watch_view.latest_date", sql=sql_latest)
                latest = await conn.fetchval(sql_latest)
            end_date = latest or date.today()

        if not include_removed:
            # 默认口径：
            # 1) 仅展示当前仍在池内（active/weakening）的股票
            # 2) 每只股票只展示历史真实首次入选日（MIN(history.trade_date)）
            #    不使用 pool.watch_start_date（该字段可能被重置为最新日）
            sql = """
            WITH selected_trade_dates AS (
                SELECT DISTINCT trade_date
                FROM strong_stock_watch_history
                WHERE trade_date <= $1::date
                ORDER BY trade_date DESC
                LIMIT $2
            ),
            active_pool AS (
                SELECT
                    p.*,
                    split_part(p.stock_id, '.', 1) AS stock_code
                FROM strong_stock_watch_pool p
                WHERE p.watch_status IN ('active', 'weakening')
                  AND split_part(p.stock_id, '.', 1) !~ '^688'
                  AND UPPER(COALESCE(p.stock_name, '')) NOT LIKE 'ST%'
                  AND UPPER(COALESCE(p.stock_name, '')) NOT LIKE '*ST%'
                  AND ($3::text IS NULL OR split_part(p.stock_id, '.', 1) = split_part($3::text, '.', 1))
            ),
            first_seen AS (
                SELECT
                    split_part(h.stock_id, '.', 1) AS stock_code,
                    MIN(h.trade_date) AS first_trade_date
                FROM strong_stock_watch_history h
                JOIN (SELECT DISTINCT stock_code FROM active_pool) a
                  ON a.stock_code = split_part(h.stock_id, '.', 1)
                WHERE h.watch_status IN ('active', 'weakening')
                  AND h.trade_date <= $1::date
                GROUP BY split_part(h.stock_id, '.', 1)
            ),
            ranked AS (
                SELECT
                    fs.first_trade_date::text AS trade_date,
                    p.stock_id,
                    p.stock_name,
                    p.subject_key,
                    COALESCE(
                        CASE
                            WHEN NULLIF(BTRIM(p.theme_name), '') IS NULL THEN NULL
                            WHEN BTRIM(p.theme_name) ~ '^[0-9]+$' THEN NULL
                            ELSE BTRIM(p.theme_name)
                        END,
                        CASE
                            WHEN NULLIF(BTRIM(v.theme_name), '') IS NULL THEN NULL
                            WHEN BTRIM(v.theme_name) ~ '^[0-9]+$' THEN NULL
                            ELSE BTRIM(v.theme_name)
                        END,
                        p.subject_key
                    ) AS theme_name,
                    p.watch_status,
                    p.watch_score,
                    p.watch_priority,
                    p.relay_role,
                    p.pool_entry_type,
                    p.cycle_state,
                    p.mainline_strength_score,
                    p.fade_watch,
                    p.fade_confirmed,
                    p.candidate_promoted AS promoted_to_candidate,
                    p.support_type,
                    p.support_level,
                    p.support_score,
                    p.labels_json,
                    p.evidence_json,
                    fs.first_trade_date::text AS watch_start_date,
                    p.last_trade_date::text AS last_trade_date,
                    p.watch_window_days,
                    s.pct_chg,
                    CASE
                        WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 20
                            THEN NULLIF(s.raw_json->>20, '')::integer
                        ELSE NULL
                    END AS current_flag,
                    NULL::numeric AS turnover_rate,
                    COALESCE(NULLIF(s.raw_json->>35, ''), '0')::numeric AS main_net_inflow,
                    ROW_NUMBER() OVER (
                        PARTITION BY split_part(p.stock_id, '.', 1)
                        ORDER BY p.watch_score DESC, p.watch_priority DESC, p.last_trade_date DESC
                    ) AS stock_rn
                FROM active_pool p
                JOIN first_seen fs
                  ON fs.stock_code = p.stock_code
                LEFT JOIN subject_stock_daily_snapshot s
                  ON s.trade_date = p.last_trade_date
                 AND split_part(s.stock_id, '.', 1) = split_part(p.stock_id, '.', 1)
                LEFT JOIN LATERAL (
                    SELECT theme_name
                    FROM vw_subject_theme_binding v
                    WHERE v.subject_key = p.subject_key
                    ORDER BY theme_name
                    LIMIT 1
                ) v ON TRUE
                WHERE fs.first_trade_date IN (SELECT trade_date FROM selected_trade_dates)
            )
            SELECT
                trade_date,
                stock_id,
                stock_name,
                subject_key,
                theme_name,
                watch_status,
                watch_score,
                watch_priority,
                relay_role,
                pool_entry_type,
                cycle_state,
                mainline_strength_score,
                fade_watch,
                fade_confirmed,
                promoted_to_candidate,
                support_type,
                support_level,
                support_score,
                labels_json,
                evidence_json,
                watch_start_date,
                last_trade_date,
                watch_window_days,
                pct_chg,
                current_flag,
                turnover_rate,
                main_net_inflow
            FROM ranked
            WHERE stock_rn = 1
            ORDER BY theme_name ASC, watch_start_date DESC, watch_score DESC, watch_priority DESC
            LIMIT $4
            """
            async with self._pool.acquire() as conn:
                self._audit_and_guard_sql(endpoint="fetch_strong_stock_watch_view.active_only", sql=sql)
                rows = await conn.fetch(
                    sql,
                    end_date,
                    safe_window,
                    stock_id,
                    safe_limit,
                )
        else:
            sql = """
            WITH selected_trade_dates AS (
                SELECT DISTINCT trade_date
                FROM strong_stock_watch_history
                WHERE trade_date <= $1::date
                ORDER BY trade_date DESC
                LIMIT $2
            ),
            base AS (
                SELECT
                    h.trade_date,
                    h.stock_id,
                    h.stock_name,
                    h.subject_key,
                    CASE
                        WHEN NULLIF(BTRIM(h.theme_name), '') IS NULL THEN NULL
                        WHEN BTRIM(h.theme_name) ~ '^[0-9]+$' THEN NULL
                        ELSE BTRIM(h.theme_name)
                    END AS raw_theme_name,
                    h.watch_status,
                    h.watch_score,
                    h.watch_priority,
                    h.relay_role,
                    h.pool_entry_type,
                    h.cycle_state,
                    h.mainline_strength_score,
                    h.fade_watch,
                    h.fade_confirmed,
                    h.promoted_to_candidate,
                    h.support_type,
                    h.support_level,
                    h.support_score,
                    h.labels_json,
                    h.evidence_json,
                    p.watch_start_date,
                    p.last_trade_date,
                    p.watch_window_days,
                    s.pct_chg,
                    CASE
                        WHEN jsonb_typeof(s.raw_json) = 'array' AND jsonb_array_length(s.raw_json) > 20
                            THEN NULLIF(s.raw_json->>20, '')::integer
                        ELSE NULL
                    END AS current_flag,
                    NULL::numeric AS turnover_rate,
                    COALESCE(NULLIF(s.raw_json->>35, ''), '0')::numeric AS main_net_inflow,
                    ROW_NUMBER() OVER (
                        PARTITION BY split_part(h.stock_id, '.', 1)
                        ORDER BY h.trade_date DESC, h.watch_score DESC, h.watch_priority DESC
                    ) AS rn,
                    ROW_NUMBER() OVER (
                        PARTITION BY h.trade_date, split_part(h.stock_id, '.', 1)
                        ORDER BY h.watch_score DESC, h.watch_priority DESC
                    ) AS day_rn
                FROM strong_stock_watch_history h
                LEFT JOIN strong_stock_watch_pool p
                  ON split_part(p.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
                LEFT JOIN subject_stock_daily_snapshot s
                  ON s.trade_date = h.trade_date
                 AND split_part(s.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
                WHERE h.trade_date IN (SELECT trade_date FROM selected_trade_dates)
                  AND ($3::boolean OR h.watch_status IN ('active', 'weakening'))
                  AND split_part(h.stock_id, '.', 1) !~ '^688'
                  AND UPPER(COALESCE(h.stock_name, '')) NOT LIKE 'ST%'
                  AND UPPER(COALESCE(h.stock_name, '')) NOT LIKE '*ST%'
                  AND ($5::text IS NULL OR split_part(h.stock_id, '.', 1) = split_part($5::text, '.', 1))
            )
            SELECT
                b.trade_date::text AS trade_date,
                b.stock_id,
                b.stock_name,
                b.subject_key,
                COALESCE(
                    b.raw_theme_name,
                    CASE
                        WHEN NULLIF(BTRIM(v.theme_name), '') IS NULL THEN NULL
                        WHEN BTRIM(v.theme_name) ~ '^[0-9]+$' THEN NULL
                        ELSE BTRIM(v.theme_name)
                    END,
                    b.subject_key
                ) AS theme_name,
                b.watch_status,
                b.watch_score,
                b.watch_priority,
                b.relay_role,
                b.pool_entry_type,
                b.cycle_state,
                b.mainline_strength_score,
                b.fade_watch,
                b.fade_confirmed,
                b.promoted_to_candidate,
                b.support_type,
                b.support_level,
                b.support_score,
                b.labels_json,
                b.evidence_json,
                b.watch_start_date::text AS watch_start_date,
                b.last_trade_date::text AS last_trade_date,
                b.watch_window_days,
                b.pct_chg,
                b.current_flag,
                b.turnover_rate,
                b.main_net_inflow
            FROM base b
            LEFT JOIN LATERAL (
                SELECT theme_name
                FROM vw_subject_theme_binding v
                WHERE v.subject_key = b.subject_key
                ORDER BY theme_name
                LIMIT 1
            ) v ON TRUE
            WHERE b.day_rn = 1
              AND ($4::boolean = FALSE OR b.rn = 1)
            ORDER BY theme_name ASC, b.trade_date DESC, b.watch_score DESC, b.watch_priority DESC
            LIMIT $6
            """
            async with self._pool.acquire() as conn:
                self._audit_and_guard_sql(endpoint="fetch_strong_stock_watch_view.include_removed", sql=sql)
                rows = await conn.fetch(
                    sql,
                    end_date,
                    safe_window,
                    include_removed,
                    latest_per_stock,
                    stock_id,
                    safe_limit,
                )

        items: List[Dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            labels_json = item.get("labels_json")
            evidence_json = item.get("evidence_json")
            if isinstance(labels_json, str):
                try:
                    labels_json = json.loads(labels_json)
                except Exception:
                    labels_json = {}
            if isinstance(evidence_json, str):
                try:
                    evidence_json = json.loads(evidence_json)
                except Exception:
                    evidence_json = {}
            if not isinstance(labels_json, dict):
                labels_json = {}
            if not isinstance(evidence_json, dict):
                evidence_json = {}

            reason_parts: List[str] = []
            if labels_json.get("seed_reason"):
                reason_parts.append(str(labels_json.get("seed_reason")))
            relay_role = item.get("relay_role")
            if relay_role:
                reason_parts.append(f"角色:{relay_role}")
            if item.get("watch_status"):
                reason_parts.append(f"状态:{item.get('watch_status')}")
            selected_reason = " | ".join(reason_parts) if reason_parts else "系统自动纳入强势股跟踪池"

            item["labels_json"] = labels_json
            item["evidence_json"] = evidence_json
            item["selected_reason"] = selected_reason
            items.append(item)

        trade_dates = sorted({str(item.get("trade_date") or "") for item in items if str(item.get("trade_date") or "")})
        date_from = trade_dates[0] if trade_dates else end_date.isoformat()

        return {
            "date_from": date_from,
            "date_to": end_date.isoformat(),
            "window_days": safe_window,
            "latest_per_stock": bool(latest_per_stock),
            "include_removed": bool(include_removed),
            "count": len(items),
            "items": items,
            "diagnostics": {
                "partial": False,
                "source": "strong_stock_watch_history",
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
        FROM theme_cycle_judgement_v2
        WHERE subject_key = $1
        """
        async with self._pool.acquire() as conn:
            self._audit_and_guard_sql(endpoint="_resolve_theme_trade_date", sql=sql)
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
            v2.trade_date::text AS trade_date,
            v2.subject_key,
            COALESCE(NULLIF(BTRIM(v2.theme_name), ''), v2.subject_key) AS theme_name,
            CASE WHEN COALESCE(msd.is_mainline, FALSE) THEN 'mainline_alive' ELSE 'inactive' END AS theme_tier,
            COALESCE(msd.state, v2.final_cycle_state) AS final_cycle_state,
            COALESCE(msd.is_mainline, v2.final_mainline_alive, FALSE) AS final_mainline_alive,
            COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) AS mainline_strength_score,
            v2.fade_risk_score,
            v2.confidence_score,
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
        FROM theme_cycle_judgement_v2 v2
        LEFT JOIN mainline_state_daily msd
          ON msd.trade_date = v2.trade_date
         AND msd.subject_key = v2.subject_key
        LEFT JOIN theme_cycle_judgement tcj
          ON tcj.trade_date = v2.trade_date
         AND tcj.subject_key = v2.subject_key
        LEFT JOIN theme_environment_judgement te
          ON te.trade_date = v2.trade_date
         AND te.subject_key = v2.subject_key
        LEFT JOIN subject_rank_daily srd
          ON srd.rank_date = v2.trade_date
         AND srd.subject_key = v2.subject_key
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
          ON flow.trade_date = v2.trade_date
         AND flow.subject_key = v2.subject_key
        WHERE v2.subject_key = $1
          AND v2.trade_date = $2::date
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
            self._audit_and_guard_sql(endpoint="fetch_theme_analytics_view.summary", sql=summary_sql)
            self._audit_and_guard_sql(endpoint="fetch_theme_analytics_view.recent_rank", sql=recent_rank_sql)
            self._audit_and_guard_sql(endpoint="fetch_theme_analytics_view.leader_stocks", sql=leader_stocks_sql)
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
            self._audit_and_guard_sql(endpoint="fetch_stock_detail_simple", sql=sql)
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
            self._audit_and_guard_sql(endpoint="fetch_stock_money_flow_view", sql=sql)
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
            self._audit_and_guard_sql(endpoint="fetch_stock_dragon_tiger_view", sql=sql)
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
            self._audit_and_guard_sql(endpoint="fetch_stock_auction_validation_view", sql=sql)
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
            self._audit_and_guard_sql(endpoint="fetch_stock_kline_view.position", sql=position_sql)
            self._audit_and_guard_sql(endpoint="fetch_stock_kline_view.pattern", sql=pattern_sql)
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
        await self.initialize()
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

    async def resolve_theme_name_map(
        self, subject_keys: List[str], trade_date: Optional[date] = None
    ) -> Dict[str, str]:
        await self.initialize()
        keys = [str(k).strip() for k in subject_keys if str(k).strip()]
        if not keys:
            return {}
        sql = """
        WITH keyset AS (
          SELECT DISTINCT unnest($1::text[]) AS subject_key
        )
        SELECT
          k.subject_key,
          COALESCE(
            (
              SELECT NULLIF(v2.theme_name, '')
              FROM theme_cycle_judgement_v2 v2
              WHERE v2.subject_key = k.subject_key
                AND NULLIF(v2.theme_name, '') IS NOT NULL
                AND v2.theme_name !~ '^[0-9]+$'
                AND ($2::date IS NULL OR v2.trade_date <= $2::date)
              ORDER BY v2.trade_date DESC
              LIMIT 1
            ),
            (
              SELECT NULLIF(sh.subject_name, '')
              FROM subject_history_staging sh
              WHERE sh.subject_key = k.subject_key
                AND NULLIF(sh.subject_name, '') IS NOT NULL
                AND ($2::date IS NULL OR sh.rank_date <= $2::date)
              ORDER BY sh.rank_date DESC
              LIMIT 1
            ),
            k.subject_key
          ) AS theme_name
        FROM keyset k
        """
        self._audit_and_guard_sql(endpoint="resolve_theme_name_map", sql=sql)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, keys, trade_date)
        return {str(r["subject_key"]): str(r["theme_name"] or r["subject_key"]) for r in rows}

    async def resolve_prev_trade_date(self, trade_date: date) -> date:
        await self.initialize()
        sql = """
        SELECT MAX(trade_date) AS prev_trade_date
        FROM subject_stock_daily_snapshot
        WHERE trade_date < $1::date
        """
        self._audit_and_guard_sql(endpoint="resolve_prev_trade_date", sql=sql)
        async with self._pool.acquire() as conn:
            prev_day = await conn.fetchval(sql, trade_date)
        return prev_day or trade_date

    async def resolve_next_trade_date(self, trade_date: date) -> Optional[date]:
        await self.initialize()
        sql = """
        SELECT MIN(trade_date) AS next_trade_date
        FROM subject_stock_daily_snapshot
        WHERE trade_date > $1::date
        """
        self._audit_and_guard_sql(endpoint="resolve_next_trade_date", sql=sql)
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, trade_date)

    async def fetch_recap_defaults(self) -> Dict[str, Any]:
        await self.report_repo.initialize()
        sql_frozen = """
        SELECT
          (SELECT MAX(trade_date)::text FROM post_market_recap_snapshot) AS latest_post_market_date,
          (SELECT MAX(trade_date)::text FROM pre_market_brief_snapshot) AS latest_pre_market_date
        """
        sql_legacy_fallback = """
        SELECT
          (SELECT MAX(trade_date)::text FROM theme_cycle_judgement_v2) AS latest_post_market_date,
          (SELECT MAX(trade_date)::text FROM pre_market_execution_plan) AS latest_pre_market_date
        """
        assert self.report_repo.pool is not None
        async with self.report_repo.pool.acquire() as conn:
            self._audit_and_guard_sql(endpoint="fetch_recap_defaults.frozen", sql=sql_frozen)
            row = await conn.fetchrow(sql_frozen)
            payload = dict(row) if row else {}

            # Transition fallback: keep legacy defaults only when strict-block is disabled.
            # This preserves current business continuity while frozen snapshots warm up.
            if (
                not BFF_STRICT_FROZEN_OBJECT_READ
                and not payload.get("latest_post_market_date")
                and not payload.get("latest_pre_market_date")
            ):
                self._audit_and_guard_sql(endpoint="fetch_recap_defaults.legacy_fallback", sql=sql_legacy_fallback)
                legacy_row = await conn.fetchrow(sql_legacy_fallback)
                legacy_payload = dict(legacy_row) if legacy_row else {}
                payload["latest_post_market_date"] = legacy_payload.get("latest_post_market_date")
                payload["latest_pre_market_date"] = legacy_payload.get("latest_pre_market_date")

        return {
            "latest_post_market_date": payload.get("latest_post_market_date"),
            "latest_pre_market_date": payload.get("latest_pre_market_date"),
        }

    async def infer_confirm_trade_date_from_candidate_trade_date(
        self, candidate_trade_date: date
    ) -> Optional[date]:
        await self.initialize()
        sql = """
        SELECT MAX(next_trade_date) AS confirm_trade_date
        FROM weak_to_strong_candidate_pool
        WHERE trade_date = $1::date
          AND next_trade_date > $1::date
        """
        self._audit_and_guard_sql(
            endpoint="infer_confirm_trade_date_from_candidate_trade_date",
            sql=sql,
        )
        async with self._pool.acquire() as conn:
            return await conn.fetchval(sql, candidate_trade_date)

    async def fetch_w2s_candidates_by_trade_date(
        self, candidate_trade_date: date, limit: int = 200
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
          id,
          trade_date,
          next_trade_date,
          stock_id,
          stock_name,
          subject_key,
          theme_name,
          candidate_score,
          pool_entry_type,
          candidate_type,
          weak_type,
          support_type,
          support_strength,
          expected_open_low,
          expected_open_high,
          evidence_json
        FROM weak_to_strong_candidate_pool
        WHERE trade_date = $1::date
        ORDER BY candidate_score DESC, id ASC
        LIMIT $2
        """
        self._audit_and_guard_sql(endpoint="fetch_w2s_candidates_by_trade_date", sql=sql)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, candidate_trade_date, max(int(limit), 1))
        return [dict(r) for r in rows]

    async def fetch_w2s_candidates_for_confirm_date(
        self, confirm_trade_date: date, limit: int = 200
    ) -> List[Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
          id,
          trade_date,
          next_trade_date,
          stock_id,
          stock_name,
          subject_key,
          theme_name,
          candidate_score,
          pool_entry_type,
          candidate_type,
          weak_type,
          support_type,
          support_strength,
          expected_open_low,
          expected_open_high,
          evidence_json
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
        ORDER BY candidate_score DESC, id ASC
        LIMIT $2
        """
        self._audit_and_guard_sql(endpoint="fetch_w2s_candidates_for_confirm_date", sql=sql)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, confirm_trade_date, max(int(limit), 1))
        return [dict(r) for r in rows]

    async def count_w2s_candidates_for_confirm_date(self, confirm_trade_date: date) -> int:
        await self.initialize()
        sql = """
        SELECT COUNT(*)::int AS cnt
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
        """
        self._audit_and_guard_sql(endpoint="count_w2s_candidates_for_confirm_date", sql=sql)
        async with self._pool.acquire() as conn:
            return int(await conn.fetchval(sql, confirm_trade_date) or 0)

    async def count_w2s_formal_candidates_for_confirm_date(self, confirm_trade_date: date) -> int:
        await self.initialize()
        sql = """
        SELECT COUNT(*)::int AS cnt
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
          AND COALESCE(NULLIF(LOWER(pool_entry_type), ''), 'formal') = 'formal'
        """
        self._audit_and_guard_sql(endpoint="count_w2s_formal_candidates_for_confirm_date", sql=sql)
        async with self._pool.acquire() as conn:
            return int(await conn.fetchval(sql, confirm_trade_date) or 0)

    async def fetch_w2s_candidates_by_ids(self, candidate_ids: List[int]) -> List[Dict[str, Any]]:
        await self.initialize()
        cleaned_ids = sorted({int(item) for item in candidate_ids if int(item) > 0})
        if not cleaned_ids:
            return []
        sql = """
        SELECT
          id,
          trade_date,
          next_trade_date,
          stock_id,
          stock_name,
          subject_key,
          theme_name,
          candidate_score,
          pool_entry_type,
          candidate_type,
          weak_type,
          support_type,
          support_strength,
          expected_open_low,
          expected_open_high,
          evidence_json
        FROM weak_to_strong_candidate_pool
        WHERE id = ANY($1::int[])
        ORDER BY candidate_score DESC, id ASC
        """
        self._audit_and_guard_sql(endpoint="fetch_w2s_candidates_by_ids", sql=sql)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, cleaned_ids)
        return [dict(r) for r in rows]

    async def fetch_w2s_signals(self, trade_date: date) -> Dict[int, Dict[str, Any]]:
        await self.initialize()
        sql = """
        SELECT
          candidate_id,
          signal_level,
          decision,
          confirmation_score,
          auction_open_pct,
          auction_close_pct,
          auction_pattern,
          last_minute_grab_score,
          plate_follow_score,
          risk_penalty,
          data_status,
          evidence_json
        FROM weak_to_strong_auction_signal
        WHERE trade_date = $1::date
        """
        self._audit_and_guard_sql(endpoint="fetch_w2s_signals", sql=sql)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        payload: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            payload[int(row["candidate_id"])] = dict(row)
        return payload

    async def get_w2s_snapshot_coverage(self, confirm_trade_date: date) -> Dict[str, int]:
        await self.initialize()
        sql = """
        SELECT
          COUNT(*)::int AS candidate_cnt,
          COUNT(*) FILTER (WHERE s.stock_id IS NOT NULL)::int AS snapshot_hit_cnt
        FROM weak_to_strong_candidate_pool c
        LEFT JOIN pre_market_auction_snapshot s
          ON split_part(s.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
         AND s.trade_date = c.next_trade_date
        WHERE c.next_trade_date = $1::date
          AND COALESCE(NULLIF(LOWER(c.pool_entry_type), ''), 'formal') = 'formal'
        """
        self._audit_and_guard_sql(endpoint="get_w2s_snapshot_coverage", sql=sql)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, confirm_trade_date)
        row_map = dict(row) if row else {}
        return {
            "candidate_cnt": int(row_map.get("candidate_cnt") or 0),
            "snapshot_hit_cnt": int(row_map.get("snapshot_hit_cnt") or 0),
        }

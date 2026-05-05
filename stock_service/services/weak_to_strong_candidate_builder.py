from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

from stock_service.config import StockServiceConfig
from stock_service.services.kline_data_service import KlineDataService
from stock_service.services.weak_to_strong_support_scorer import WeakToStrongSupportScorer
from stock_service.utils.security_id import normalize_stock_id


@dataclass
class CandidateBuildResult:
    trade_date: date
    next_trade_date: date
    total_scanned: int
    total_inserted: int
    candidates: List[Dict[str, Any]]


class WeakToStrongCandidateBuilder:
    """盘后弱转强候选池构建器（P1 MVP）"""

    RULE_VERSION = "weak_to_strong_candidate.v2"
    WATCH_SOURCE_TAG = "watch_pool"
    STATIC_SOURCE_TAG = "static_scan"
    HARD_MAX_CANDIDATES = 10

    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
        self.pool: Optional[asyncpg.Pool] = None
        # 灰度开关：
        # off  : 不启用 formal 来源门禁
        # soft : formal 非 S/A 白名单时降级 observe_only
        # hard : formal 非 S/A 白名单时直接剔除
        self.formal_sa_gate_mode = str(
            os.getenv("W2S_FORMAL_SA_GATE_MODE", "off")
        ).strip().lower()
        if self.formal_sa_gate_mode not in {"off", "soft", "hard"}:
            self.formal_sa_gate_mode = "off"
        # K线数据服务 - 用于支撑位分析
        self.kline_service = KlineDataService({
            "host": self.config.postgres_host,
            "port": self.config.postgres_port,
            "database": self.config.postgres_database,
            "user": self.config.postgres_user,
            "password": self.config.postgres_password
        })
        self.support_scorer = WeakToStrongSupportScorer(self.config)

    async def _ensure_pool(self) -> asyncpg.Pool:
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_database,
                user=self.config.postgres_user,
                password=self.config.postgres_password,
                min_size=1,
                max_size=3,
            )
        return self.pool

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
        if hasattr(self, 'kline_service') and self.kline_service:
            await self.kline_service.close()
        if hasattr(self, "support_scorer") and self.support_scorer:
            await self.support_scorer.close()

    async def resolve_next_trade_date(self, trade_date: date) -> date:
        pool = await self._ensure_pool()
        sql = """
        SELECT MIN(trade_date) AS next_trade_date
        FROM subject_stock_daily_snapshot
        WHERE trade_date > $1::date
        """
        async with pool.acquire() as conn:
            next_day = await conn.fetchval(sql, trade_date)
        if not next_day:
            raise ValueError(
                f"无法解析 {trade_date.isoformat()} 的下一交易日：subject_stock_daily_snapshot 不存在更晚交易日数据"
            )
        return next_day

    @staticmethod
    def _validate_trade_dates(trade_date: date, next_trade_date: date) -> None:
        if next_trade_date < trade_date:
            raise ValueError(
                "next_trade_date 非法：必须大于等于 candidate_trade_date "
                f"(candidate_trade_date={trade_date.isoformat()}, next_trade_date={next_trade_date.isoformat()})"
            )

    async def build(
        self,
        trade_date: date,
        *,
        next_trade_date: Optional[date] = None,
        max_candidates: int = 10,
    ) -> CandidateBuildResult:
        await self._ensure_pool()
        next_day = next_trade_date or await self.resolve_next_trade_date(trade_date)
        self._validate_trade_dates(trade_date, next_day)

        watch_rows = await self._fetch_watch_candidate_inputs(trade_date)
        candidates_by_stock: Dict[str, Dict[str, Any]] = {}

        # 强约束：弱转强候选只能来自强势股跟踪池，禁止静态全市场扫描源。
        for row in watch_rows:
            if self._is_disallowed_candidate_stock(
                str(row.get("stock_id") or row.get("stock_code") or ""),
                str(row.get("stock_name") or ""),
            ):
                continue
            if not self._quick_row_gate(row, source="watch"):
                continue
            candidate = await self._async_to_candidate(row, trade_date, next_day)
            if candidate is None:
                continue
            candidate = self._apply_watch_context(candidate, row)
            self._attach_source_metadata(
                candidate,
                source_tag=self.WATCH_SOURCE_TAG,
                source_meta={
                    "watch_score": float(row.get("watch_score") or 0.0),
                    "watch_priority": float(row.get("watch_priority") or 0.0),
                    "watch_pool_entry_type": str(row.get("watch_pool_entry_type") or "observe_only"),
                    "watch_status": str(row.get("watch_status") or "active"),
                    "watch_source_tag": str(row.get("watch_source_tag") or ""),
                    "strong_grade": str(self._coerce_json_dict(row.get("watch_labels_json")).get("strong_grade") or "").upper(),
                },
            )
            self._merge_candidate(candidates_by_stock, candidate)

        candidates = list(candidates_by_stock.values())
        candidates = self._enforce_formal_sa_whitelist(candidates)
        candidates.sort(key=lambda x: float(x["candidate_score"]), reverse=True)
        effective_max = min(max(max_candidates, 1), self.HARD_MAX_CANDIDATES)
        candidates = candidates[:effective_max]
        inserted = await self._replace_candidates(next_day, candidates)

        return CandidateBuildResult(
            trade_date=trade_date,
            next_trade_date=next_day,
            total_scanned=len(watch_rows),
            total_inserted=inserted,
            candidates=candidates,
        )

    async def build_with_strict_support(
        self,
        trade_date: date,
        *,
        next_trade_date: Optional[date] = None,
        max_candidates: int = 10,
    ) -> CandidateBuildResult:
        """兼容入口：当前已与 build() 使用同一套独立支撑评分口径。"""
        return await self.build(
            trade_date,
            next_trade_date=next_trade_date,
            max_candidates=max_candidates,
        )

    def _quick_row_gate(self, row: asyncpg.Record, *, source: str) -> bool:
        """支撑评分前的轻量门槛，防止阶段1全量重算导致超时。"""
        if source == "watch":
            watch_status = str(row.get("watch_status") or "")
            watch_pool_entry_type = str(row.get("watch_pool_entry_type") or "")
            return watch_status in {"active", "weakening"} and watch_pool_entry_type in {"formal", "observe_only"}

        is_leader = bool(row.get("is_leader") or False)
        limit_up = bool(row.get("limit_up") or False)
        rank_order = int(row.get("rank_order") or 999)
        recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
        prior7_limitup_days = int(row.get("prior7_limitup_days") or 0)
        prior7_strong_days = int(row.get("prior7_strong_days") or 0)
        pct_chg = float(row.get("pct_chg") or 0.0)
        is_main_theme = bool(row.get("is_main_theme") or False)
        identity_status = str(row.get("identity_status") or "").strip().lower()
        final_mainline_alive = bool(row.get("final_mainline_alive") or False)
        fade_watch = bool(row.get("fade_watch") or False)
        cycle_state = str(row.get("final_cycle_state") or "").lower()

        if not is_main_theme or identity_status != "confirmed":
            return False
        strong_background = (is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3)
        if not strong_background:
            return False
        # 主逻辑硬约束：强势股必须具备涨停基因（近7交易日至少1次涨停）。
        if prior7_limitup_days < 1:
            return False
        # 主逻辑硬约束：候选必须在近7个交易日内具备强势历史。
        if prior7_strong_days < 1:
            return False
        if not (
            final_mainline_alive
            or fade_watch
            or cycle_state in {"divergence", "repair", "分歧", "修复"}
        ):
            return False
        if rank_order > 20 and not is_leader and not limit_up and recent_limit_up_count < 3:
            return False
        return True

    def _is_disallowed_candidate_stock(self, stock_id: str, stock_name: str) -> bool:
        canonical = self._normalize_stock_id(stock_id, stock_id)
        code = canonical.split(".", 1)[0] if "." in canonical else canonical
        if code.startswith("688"):
            return True
        name = str(stock_name or "").strip().upper()
        if not name:
            return False
        if name.startswith("ST") or name.startswith("*ST"):
            return True
        return False

    async def _fetch_candidate_inputs(self, trade_date: date) -> List[asyncpg.Record]:
        pool = await self._ensure_pool()
        sql = """
        WITH stock_base AS (
            SELECT DISTINCT ON (split_part(s.stock_id, '.', 1), s.subject_key)
                split_part(s.stock_id, '.', 1) AS stock_code,
                s.stock_id,
                s.stock_name,
                s.subject_key,
                COALESCE(NULLIF(v2.theme_name, ''), s.subject_key) AS theme_name,
                s.rank_order,
                s.pct_chg,
                s.low_price,
                s.close_price,
                s.limit_up,
                s.is_leader,
                COALESCE(msd.is_mainline, FALSE) AS is_main_theme,
                CASE WHEN COALESCE(msd.is_mainline, FALSE) THEN 'confirmed' ELSE 'observed' END AS identity_status,
                COALESCE(v2.final_cycle_state, 'unknown') AS final_cycle_state,
                COALESCE(v2.final_mainline_alive, FALSE) AS final_mainline_alive,
                COALESCE(v2.fade_watch, FALSE) AS fade_watch,
                COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed,
                COALESCE(
                    v2.mainline_strength_score,
                    e.mainline_strength_score,
                    0
                ) AS mainline_strength_score,
                COALESCE(e.leader_alive_score, 0) AS leader_alive_score,
                COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
                COALESCE(v2.rule_reasons, '[]'::jsonb) AS v2_rule_reasons,
                COALESCE(e.event_evidence_refs, '[]'::jsonb) AS event_evidence_refs,
                COALESCE(e.leader_evidence_refs, '[]'::jsonb) AS leader_evidence_refs,
                COALESCE(e.board_structure_refs, '[]'::jsonb) AS board_structure_refs,
                COALESCE(e.theme_kline_refs, '[]'::jsonb) AS theme_kline_refs
            FROM subject_stock_daily_snapshot s
            LEFT JOIN mainline_state_daily msd
              ON msd.trade_date = s.trade_date
             AND msd.subject_key = s.subject_key
            LEFT JOIN theme_cycle_judgement_v2 v2
              ON v2.trade_date = s.trade_date
             AND v2.subject_key = s.subject_key
            LEFT JOIN theme_cycle_evidence_daily e
              ON e.trade_date = s.trade_date
             AND e.subject_key = s.subject_key
            WHERE s.trade_date = $1::date
              AND COALESCE(msd.is_mainline, FALSE) = TRUE
              AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
              AND (
                    COALESCE(v2.final_mainline_alive, FALSE) = TRUE
                    OR COALESCE(s.is_leader, FALSE) = TRUE
                    OR COALESCE(s.limit_up, FALSE) = TRUE
                    OR COALESCE(s.rank_order, 999) <= 30
                    OR COALESCE(s.pct_chg, 0) <= -2.0
                  )
        ),
        recent_stats AS (
            SELECT
                stock_id,
                COUNT(*) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE) AS recent_limit_up_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date <= $1::date
              AND trade_date > ($1::date - INTERVAL '30 days')
            GROUP BY stock_id
        ),
        prior7_stats AS (
            SELECT
                stock_id,
                subject_key,
                COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE) AS prior7_limitup_days,
                COUNT(DISTINCT trade_date) FILTER (
                    WHERE COALESCE(limit_up, FALSE) = TRUE
                       OR COALESCE(is_leader, FALSE) = TRUE
                       OR COALESCE(rank_order, 999) <= 3
                       OR COALESCE(pct_chg, 0) >= 7.0
                ) AS prior7_strong_days
            FROM subject_stock_daily_snapshot
            WHERE trade_date < $1::date
              AND trade_date >= ($1::date - INTERVAL '7 days')
            GROUP BY stock_id, subject_key
        ),
        prev_day AS (
            SELECT
                stock_id,
                pct_chg AS prev_day_pct_chg,
                limit_up AS prev_day_limit_up,
                low_price AS prev_day_low_price,
                close_price AS prev_day_close_price
            FROM (
                SELECT
                    stock_id,
                    pct_chg,
                    limit_up,
                    low_price,
                    close_price,
                    ROW_NUMBER() OVER (
                        PARTITION BY stock_id
                        ORDER BY trade_date DESC
                    ) AS rn
                FROM subject_stock_daily_snapshot
                WHERE trade_date < $1::date
            ) t
            WHERE rn = 1
        )
        SELECT
            b.*,
            COALESCE(rs.recent_limit_up_count, 0) AS recent_limit_up_count,
            COALESCE(p7.prior7_limitup_days, 0) AS prior7_limitup_days,
            COALESCE(p7.prior7_strong_days, 0) AS prior7_strong_days,
            pd.prev_day_pct_chg,
            pd.prev_day_limit_up,
            pd.prev_day_low_price,
            pd.prev_day_close_price
        FROM stock_base b
        LEFT JOIN recent_stats rs
          ON rs.stock_id = b.stock_id
        LEFT JOIN prior7_stats p7
          ON p7.stock_id = b.stock_id
         AND p7.subject_key = b.subject_key
        LEFT JOIN prev_day pd
          ON pd.stock_id = b.stock_id
        ORDER BY b.rank_order ASC NULLS LAST, b.pct_chg ASC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)
        return rows

    async def _fetch_watch_candidate_inputs(self, trade_date: date) -> List[asyncpg.Record]:
        pool = await self._ensure_pool()
        current_pool_sql = """
        WITH watch_base AS (
            SELECT
                split_part(w.stock_id, '.', 1) AS stock_code,
                w.stock_id,
                COALESCE(s.stock_name, w.stock_name) AS stock_name,
                COALESCE(NULLIF(w.subject_key, ''), s.subject_key) AS subject_key,
                COALESCE(NULLIF(w.theme_name, ''), NULLIF(v2.theme_name, ''), s.subject_key, w.subject_key) AS theme_name,
                COALESCE(s.rank_order, 999) AS rank_order,
                COALESCE(s.pct_chg, 0) AS pct_chg,
                COALESCE(s.low_price, 0) AS low_price,
                COALESCE(s.close_price, 0) AS close_price,
                COALESCE(s.limit_up, FALSE) AS limit_up,
                COALESCE(s.is_leader, FALSE) AS is_leader,
                COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
                COALESCE(mr.identity_status, 'observed') AS identity_status,
                COALESCE(v2.final_cycle_state, w.cycle_state, 'unknown') AS final_cycle_state,
                (
                    COALESCE(mr.is_main_theme, FALSE)
                    AND COALESCE(mr.identity_status, '') = 'confirmed'
                    AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, w.cycle_state, '')) <> 'fade_confirmed'
                    AND COALESCE(v2.fade_confirmed, w.fade_confirmed, FALSE) = FALSE
                ) AS final_mainline_alive,
                COALESCE(v2.fade_watch, w.fade_watch, FALSE) AS fade_watch,
                COALESCE(v2.fade_confirmed, w.fade_confirmed, FALSE) AS fade_confirmed,
                COALESCE(
                    v2.mainline_strength_score,
                    e.mainline_strength_score,
                    w.mainline_strength_score,
                    0
                ) AS mainline_strength_score,
                COALESCE(e.leader_alive_score, 0) AS leader_alive_score,
                COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
                COALESCE(v2.rule_reasons, '[]'::jsonb) AS v2_rule_reasons,
                COALESCE(e.event_evidence_refs, '[]'::jsonb) AS event_evidence_refs,
                COALESCE(e.leader_evidence_refs, '[]'::jsonb) AS leader_evidence_refs,
                COALESCE(e.board_structure_refs, '[]'::jsonb) AS board_structure_refs,
                COALESCE(e.theme_kline_refs, '[]'::jsonb) AS theme_kline_refs,
                w.watch_score,
                w.watch_priority,
                w.pool_entry_type AS watch_pool_entry_type,
                w.watch_status,
                w.source_tag AS watch_source_tag,
                w.labels_json AS watch_labels_json
            FROM strong_stock_watch_pool w
            LEFT JOIN subject_stock_daily_snapshot s
              ON s.trade_date = $1::date
             AND split_part(s.stock_id, '.', 1) = split_part(w.stock_id, '.', 1)
             AND (
                    COALESCE(NULLIF(w.subject_key, ''), s.subject_key) = s.subject_key
                 )
            LEFT JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = COALESCE(NULLIF(w.subject_key, ''), s.subject_key)
            LEFT JOIN mainline_state_daily msd
              ON msd.trade_date = $1::date
             AND msd.subject_key = COALESCE(NULLIF(w.subject_key, ''), s.subject_key)
            LEFT JOIN theme_cycle_judgement_v2 v2
              ON v2.trade_date = $1::date
             AND v2.subject_key = COALESCE(NULLIF(w.subject_key, ''), s.subject_key)
            LEFT JOIN theme_cycle_evidence_daily e
              ON e.trade_date = $1::date
             AND e.subject_key = COALESCE(NULLIF(w.subject_key, ''), s.subject_key)
            WHERE w.watch_status IN ('active', 'weakening')
              AND w.pool_entry_type IN ('formal', 'observe_only')
              -- 统一口径：弱转强候选只消费强势股池，不在此层重复做主线状态硬筛选。
              -- 主线身份与周期状态在强势股池入池/维护阶段控制；候选层仅做弱+支撑+强势基因判定。
              AND w.last_trade_date <= $1::date
        ),
        recent_stats AS (
            SELECT
                stock_id,
                COUNT(*) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE) AS recent_limit_up_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date <= $1::date
              AND trade_date > ($1::date - INTERVAL '30 days')
            GROUP BY stock_id
        ),
        prior7_stats AS (
            SELECT
                stock_id,
                subject_key,
                COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE) AS prior7_limitup_days,
                COUNT(DISTINCT trade_date) FILTER (
                    WHERE COALESCE(limit_up, FALSE) = TRUE
                       OR COALESCE(is_leader, FALSE) = TRUE
                       OR COALESCE(rank_order, 999) <= 3
                       OR COALESCE(pct_chg, 0) >= 7.0
                ) AS prior7_strong_days
            FROM subject_stock_daily_snapshot
            WHERE trade_date < $1::date
              AND trade_date >= ($1::date - INTERVAL '7 days')
            GROUP BY stock_id, subject_key
        ),
        prev_day AS (
            SELECT
                stock_id,
                pct_chg AS prev_day_pct_chg,
                limit_up AS prev_day_limit_up,
                low_price AS prev_day_low_price,
                close_price AS prev_day_close_price
            FROM (
                SELECT
                    stock_id,
                    pct_chg,
                    limit_up,
                    low_price,
                    close_price,
                    ROW_NUMBER() OVER (
                        PARTITION BY stock_id
                        ORDER BY trade_date DESC
                    ) AS rn
                FROM subject_stock_daily_snapshot
                WHERE trade_date < $1::date
            ) t
            WHERE rn = 1
        )
        SELECT
            b.*,
            COALESCE(rs.recent_limit_up_count, 0) AS recent_limit_up_count,
            COALESCE(p7.prior7_limitup_days, 0) AS prior7_limitup_days,
            COALESCE(p7.prior7_strong_days, 0) AS prior7_strong_days,
            pd.prev_day_pct_chg,
            pd.prev_day_limit_up,
            pd.prev_day_low_price,
            pd.prev_day_close_price
        FROM watch_base b
        LEFT JOIN recent_stats rs
          ON split_part(rs.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        LEFT JOIN prior7_stats p7
          ON split_part(p7.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
         AND p7.subject_key = b.subject_key
        LEFT JOIN prev_day pd
          ON split_part(pd.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        ORDER BY b.watch_priority DESC NULLS LAST, b.watch_score DESC NULLS LAST
        """
        history_sql = """
        WITH watch_base AS (
            SELECT
                split_part(h.stock_id, '.', 1) AS stock_code,
                h.stock_id,
                COALESCE(s.stock_name, h.stock_name) AS stock_name,
                COALESCE(NULLIF(h.subject_key, ''), s.subject_key) AS subject_key,
                COALESCE(NULLIF(h.theme_name, ''), NULLIF(v2.theme_name, ''), s.subject_key, h.subject_key) AS theme_name,
                COALESCE(s.rank_order, 999) AS rank_order,
                COALESCE(s.pct_chg, 0) AS pct_chg,
                COALESCE(s.low_price, 0) AS low_price,
                COALESCE(s.close_price, 0) AS close_price,
                COALESCE(s.limit_up, FALSE) AS limit_up,
                COALESCE(s.is_leader, FALSE) AS is_leader,
                COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
                COALESCE(mr.identity_status, 'observed') AS identity_status,
                COALESCE(v2.final_cycle_state, h.cycle_state, 'unknown') AS final_cycle_state,
                (
                    COALESCE(mr.is_main_theme, FALSE)
                    AND COALESCE(mr.identity_status, '') = 'confirmed'
                    AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, h.cycle_state, '')) <> 'fade_confirmed'
                    AND COALESCE(v2.fade_confirmed, h.fade_confirmed, FALSE) = FALSE
                ) AS final_mainline_alive,
                COALESCE(v2.fade_watch, h.fade_watch, FALSE) AS fade_watch,
                COALESCE(v2.fade_confirmed, h.fade_confirmed, FALSE) AS fade_confirmed,
                COALESCE(
                    v2.mainline_strength_score,
                    e.mainline_strength_score,
                    h.mainline_strength_score,
                    0
                ) AS mainline_strength_score,
                COALESCE(e.leader_alive_score, 0) AS leader_alive_score,
                COALESCE(e.event_continuity_score, 0) AS event_continuity_score,
                COALESCE(v2.rule_reasons, '[]'::jsonb) AS v2_rule_reasons,
                COALESCE(e.event_evidence_refs, '[]'::jsonb) AS event_evidence_refs,
                COALESCE(e.leader_evidence_refs, '[]'::jsonb) AS leader_evidence_refs,
                COALESCE(e.board_structure_refs, '[]'::jsonb) AS board_structure_refs,
                COALESCE(e.theme_kline_refs, '[]'::jsonb) AS theme_kline_refs,
                h.watch_score,
                h.watch_priority,
                h.pool_entry_type AS watch_pool_entry_type,
                h.watch_status,
                'history_snapshot'::text AS watch_source_tag,
                h.labels_json AS watch_labels_json
            FROM strong_stock_watch_history h
            LEFT JOIN subject_stock_daily_snapshot s
              ON s.trade_date = $1::date
             AND split_part(s.stock_id, '.', 1) = split_part(h.stock_id, '.', 1)
             AND (
                    COALESCE(NULLIF(h.subject_key, ''), s.subject_key) = s.subject_key
                 )
            LEFT JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = COALESCE(NULLIF(h.subject_key, ''), s.subject_key)
            LEFT JOIN mainline_state_daily msd
              ON msd.trade_date = $1::date
             AND msd.subject_key = COALESCE(NULLIF(h.subject_key, ''), s.subject_key)
            LEFT JOIN theme_cycle_judgement_v2 v2
              ON v2.trade_date = $1::date
             AND v2.subject_key = COALESCE(NULLIF(h.subject_key, ''), s.subject_key)
            LEFT JOIN theme_cycle_evidence_daily e
              ON e.trade_date = $1::date
             AND e.subject_key = COALESCE(NULLIF(h.subject_key, ''), s.subject_key)
            WHERE h.trade_date = $1::date
              AND h.watch_status IN ('active', 'weakening')
              AND h.pool_entry_type IN ('formal', 'observe_only')
        ),
        recent_stats AS (
            SELECT
                stock_id,
                COUNT(*) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE) AS recent_limit_up_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date <= $1::date
              AND trade_date > ($1::date - INTERVAL '30 days')
            GROUP BY stock_id
        ),
        prior7_stats AS (
            SELECT
                stock_id,
                subject_key,
                COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE) = TRUE) AS prior7_limitup_days,
                COUNT(DISTINCT trade_date) FILTER (
                    WHERE COALESCE(limit_up, FALSE) = TRUE
                       OR COALESCE(is_leader, FALSE) = TRUE
                       OR COALESCE(rank_order, 999) <= 3
                       OR COALESCE(pct_chg, 0) >= 7.0
                ) AS prior7_strong_days
            FROM subject_stock_daily_snapshot
            WHERE trade_date < $1::date
              AND trade_date >= ($1::date - INTERVAL '7 days')
            GROUP BY stock_id, subject_key
        ),
        prev_day AS (
            SELECT
                stock_id,
                pct_chg AS prev_day_pct_chg,
                limit_up AS prev_day_limit_up,
                low_price AS prev_day_low_price,
                close_price AS prev_day_close_price
            FROM (
                SELECT
                    stock_id,
                    pct_chg,
                    limit_up,
                    low_price,
                    close_price,
                    ROW_NUMBER() OVER (
                        PARTITION BY stock_id
                        ORDER BY trade_date DESC
                    ) AS rn
                FROM subject_stock_daily_snapshot
                WHERE trade_date < $1::date
            ) t
            WHERE rn = 1
        )
        SELECT
            b.*,
            COALESCE(rs.recent_limit_up_count, 0) AS recent_limit_up_count,
            COALESCE(p7.prior7_limitup_days, 0) AS prior7_limitup_days,
            COALESCE(p7.prior7_strong_days, 0) AS prior7_strong_days,
            pd.prev_day_pct_chg,
            pd.prev_day_limit_up,
            pd.prev_day_low_price,
            pd.prev_day_close_price
        FROM watch_base b
        LEFT JOIN recent_stats rs
          ON split_part(rs.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        LEFT JOIN prior7_stats p7
          ON split_part(p7.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
         AND p7.subject_key = b.subject_key
        LEFT JOIN prev_day pd
          ON split_part(pd.stock_id, '.', 1) = split_part(b.stock_id, '.', 1)
        ORDER BY b.watch_priority DESC NULLS LAST, b.watch_score DESC NULLS LAST
        """
        async with pool.acquire() as conn:
            latest_pool_trade_date = await conn.fetchval(
                """
                SELECT MAX(last_trade_date) AS latest_trade_date
                FROM strong_stock_watch_pool
                """
            )
            if latest_pool_trade_date and trade_date < latest_pool_trade_date:
                return await conn.fetch(history_sql, trade_date)
            return await conn.fetch(current_pool_sql, trade_date)

    def _to_candidate(
        self,
        row: asyncpg.Record,
        trade_date: date,
        next_trade_date: date,
        *,
        support_type_override: Optional[str] = None,
        support_level_override: Optional[float] = None,
        support_strength_override: Optional[float] = None,
        support_breakdown: Optional[Dict[str, Any]] = None,
        support_refs: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        pct_chg = float(row.get("pct_chg") or 0.0)
        is_leader = bool(row.get("is_leader") or False)
        limit_up = bool(row.get("limit_up") or False)
        rank_order = int(row.get("rank_order") or 999)
        recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
        prior7_limitup_days = int(row.get("prior7_limitup_days") or 0)
        prior7_strong_days = int(row.get("prior7_strong_days") or 0)
        prev_day_pct = float(row.get("prev_day_pct_chg") or 0.0)
        prev_day_limit_up = bool(row.get("prev_day_limit_up") or False)

        cycle_state = str(row.get("final_cycle_state") or "").lower()
        is_main_theme = bool(row.get("is_main_theme") or False)
        identity_status = str(row.get("identity_status") or "").strip().lower()
        final_mainline_alive = bool(row.get("final_mainline_alive") or False)
        fade_watch = bool(row.get("fade_watch") or False)
        fade_confirmed = bool(row.get("fade_confirmed") or False)
        mainline_strength_score = float(row.get("mainline_strength_score") or 0.0)
        leader_alive_score = float(row.get("leader_alive_score") or 0.0)
        event_continuity_score = float(row.get("event_continuity_score") or 0.0)
        v2_rule_reasons = list(row.get("v2_rule_reasons") or [])
        cycle_evidence_refs = {
            "event": list(row.get("event_evidence_refs") or []),
            "leader": list(row.get("leader_evidence_refs") or []),
            "board": list(row.get("board_structure_refs") or []),
            "kline": list(row.get("theme_kline_refs") or []),
        }

        # 从“连续两天弱势硬拒”改为评分项
        day_weak_score = self._day_weak_score(pct_chg)
        prev_day_weak_score = self._prev_day_weak_score(prev_day_pct)

        # 主逻辑硬约束：弱转强前提必须“先弱”。
        # 当天上涨（含平盘）不应作为盘后弱转强候选进入阶段2。
        if pct_chg >= 0.0 or limit_up:
            return None
        # 进一步收紧“弱”定义，避免微跌噪声样本挤满候选池。
        if pct_chg > -1.0:
            return None
        strong_background = (is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3)
        strong_history = (is_leader or prev_day_limit_up or recent_limit_up_count >= 1 or rank_order <= 5)
        recent_strong_history = prior7_strong_days >= 1
        has_limitup_gene = prior7_limitup_days >= 1
        # 主逻辑硬约束：必须具备前期龙头/强势股背景，普通弱势票不进入弱转强候选。
        if not strong_history:
            return None
        # 主逻辑硬约束：无涨停基因不属于强势股，不进入弱转强候选。
        if not has_limitup_gene:
            return None
        # 主逻辑硬约束：最近一周至少有1个交易日处于强势态（涨停/龙头/前排/强涨）。
        if not recent_strong_history:
            return None
        # 弱转强候选层只关注个股弱转强逻辑，不再耦合主线周期状态判定。
        repair_window_base = False

        weak_type, weak_intensity = self._classify_weak_type(pct_chg, prev_day_pct, prev_day_limit_up)
        candidate_type = self._classify_candidate_type(
            is_leader=is_leader,
            recent_limit_up_count=recent_limit_up_count,
            weak_type=weak_type,
            rank_order=rank_order,
        )
        expected_open_low, expected_open_high = self._expected_open_range(candidate_type)
        expected_pattern = self._expected_pattern(candidate_type)

        support_type = support_type_override if support_type_override is not None else self._support_type_from_row(pct_chg, prev_day_pct)
        support_strength = (
            float(support_strength_override)
            if support_strength_override is not None
            else self._support_strength(pct_chg, prev_day_pct, support_type)
        )
        support_available = support_type not in {"", "none"} and support_strength >= 45.0
        if not support_available:
            return None
        weekly_gate_passed, weekly_gate_diag = self._weekly_midterm_gate(support_breakdown)
        if not weekly_gate_passed:
            return None
        support_level = float(support_level_override) if support_level_override is not None else 0.0
        repair_window = repair_window_base

        pool_entry_type, entry_confidence, entry_components = self.classify_pool_entry(
            is_main_theme=is_main_theme,
            final_mainline_alive=final_mainline_alive,
            fade_confirmed=fade_confirmed,
            fade_watch=fade_watch,
            mainline_strength_score=mainline_strength_score,
            leader_alive_score=leader_alive_score,
            event_continuity_score=event_continuity_score,
            strong_background=strong_background,
            repair_window=repair_window,
            support_strength=support_strength,
            support_available=support_available,
            recent_limit_up_count=recent_limit_up_count,
            day_pct_chg=pct_chg,
            prev_day_pct_chg=prev_day_pct,
            day_weak_score=day_weak_score,
            prev_day_weak_score=prev_day_weak_score,
        )
        if pool_entry_type == "reject":
            return None
        formal_eligibility = pool_entry_type == "formal"
        observe_only_reason = "" if formal_eligibility else (
            "fade_watch_or_mid_cycle" if pool_entry_type == "observe_only" else "rejected_by_entry_classifier"
        )

        score = self._candidate_score(
            is_leader=is_leader,
            limit_up=limit_up,
            recent_limit_up_count=recent_limit_up_count,
            rank_order=rank_order,
            stage=cycle_state,
            weak_intensity=weak_intensity,
            support_strength=support_strength,
            day_weak_score=day_weak_score,
            prev_day_weak_score=prev_day_weak_score,
            mainline_strength_score=mainline_strength_score,
            fade_watch=fade_watch,
        )
        fade_watch_penalty = self._fade_watch_penalty(
            fade_watch=fade_watch,
            mainline_strength_score=mainline_strength_score,
        )
        if pool_entry_type == "observe_only":
            score = min(score, 69.0)

        stock_id = self._normalize_stock_id(str(row.get("stock_id") or ""), str(row.get("stock_code") or ""))
        if not stock_id:
            return None

        evidence = {
            "schema_version": "evidence_schema.v1",
            "trace": {
                "trade_date": trade_date.isoformat(),
                "stock_id": stock_id,
                "candidate_id": "",
                "source_snapshot_id": f"candidate_{trade_date.isoformat()}_{stock_id}",
            },
            "inputs": {
                "candidate_type": candidate_type,
                "rule_version": self.RULE_VERSION,
                "weak_type": weak_type,
                "support_type": support_type,
                "expected_auction_pattern": expected_pattern,
            },
            "scores": {
                "price_strength": 0.0,
                "pattern_stability": 0.0,
                "last_minute_grab": 0.0,
                "plate_follow": 0.0,
                "risk_penalty": 0.0,
                "confirmation_score": 0.0,
                "breakdown": {
                    "candidate_score": score,
                    "repair_window": repair_window,
                    "repair_window_base": repair_window_base,
                    "strong_background": strong_background,
                    "strong_history": strong_history,
                    "has_limitup_gene": has_limitup_gene,
                    "recent_strong_history": recent_strong_history,
                    "prior7_limitup_days": prior7_limitup_days,
                    "prior7_strong_days": prior7_strong_days,
                    "day_weak_score": day_weak_score,
                    "prev_day_weak_score": prev_day_weak_score,
                    "fade_watch_penalty": fade_watch_penalty,
                    "entry_confidence": entry_confidence,
                    "entry_components": entry_components,
                    "weekly_gate": weekly_gate_diag,
                    "pool_entry_type": pool_entry_type,
                    "formal_eligibility": formal_eligibility,
                    "observe_only_reason": observe_only_reason,
                    "support_breakdown": support_breakdown or {},
                    "support_refs": support_refs or [],
                },
            },
            "rules": {
                "hard_rule_results": [
                    {"rule": "strong_background", "passed": strong_background, "reason": ""},
                    {"rule": "strong_history", "passed": strong_history, "reason": ""},
                    {"rule": "prior7_limitup_gene", "passed": has_limitup_gene, "reason": ""},
                    {"rule": "prior7_strong_history", "passed": recent_strong_history, "reason": ""},
                    {"rule": "weekly_midterm_gate", "passed": weekly_gate_passed, "reason": str(weekly_gate_diag.get("reason") or "")},
                    {"rule": "repair_window", "passed": repair_window, "reason": ""},
                    {"rule": "fade_confirmed", "passed": not fade_confirmed, "reason": ""},
                ],
                "mapping_warnings": [],
            },
            "cycle_diagnostics": {
                "thresholds": {
                    "entry_formal_confidence_min": 0.67,
                    "entry_observe_confidence_min": 0.50,
                    "entry_support_floor": 45.0,
                    "weekly_position_max": 0.72,
                    "weekly_pullback_min": 0.01,
                    "weekly_pullback_max": 0.30,
                },
                "values": {
                    "cycle_state": cycle_state,
                    "final_mainline_alive": final_mainline_alive,
                    "identity_status": identity_status,
                    "mainline_strength_score": mainline_strength_score,
                    "leader_alive_score": leader_alive_score,
                    "event_continuity_score": event_continuity_score,
                    "support_strength": support_strength,
                    "fade_watch": fade_watch,
                    "fade_confirmed": fade_confirmed,
                },
                "decision": {
                    "pool_entry_type": pool_entry_type,
                    "repair_window": repair_window,
                    "strong_background": strong_background,
                    "entry_confidence": entry_confidence,
                },
                "v2_rule_reasons": v2_rule_reasons,
                "evidence_refs": cycle_evidence_refs,
            },
            "cycle_refs": {
                "rule_reasons": v2_rule_reasons,
                "event_evidence_refs": cycle_evidence_refs.get("event", []),
                "leader_evidence_refs": cycle_evidence_refs.get("leader", []),
                "board_structure_evidence_refs": cycle_evidence_refs.get("board", []),
                "theme_kline_evidence_refs": cycle_evidence_refs.get("kline", []),
            },
            "decision": {
                "signal_level": "X",
                "decision": "candidate_only",
                "data_status": "missing",
                "data_latency_ms": 0,
            },
        }

        return {
            "trade_date": trade_date,
            "next_trade_date": next_trade_date,
            "stock_id": stock_id,
            "stock_name": str(row.get("stock_name") or stock_id),
            "subject_key": str(row.get("subject_key") or ""),
            "theme_name": str(row.get("theme_name") or row.get("subject_key") or ""),
            "candidate_score": round(score, 2),
            "candidate_type": candidate_type,
            "rule_version": self.RULE_VERSION,
            "pool_entry_type": pool_entry_type,
            "cycle_state": cycle_state,
            "is_main_theme": is_main_theme,
            "identity_status": identity_status,
            "mainline_strength_score": round(mainline_strength_score, 2),
            "fade_watch": fade_watch,
            "fade_confirmed": fade_confirmed,
            "weak_type": weak_type,
            "weak_intensity": round(weak_intensity, 2),
            "is_dragon_head": bool(is_leader and recent_limit_up_count >= 3),
            "dragon_head_level": "absolute" if (is_leader and recent_limit_up_count >= 3) else ("relative" if is_leader else "sector"),
            "prev_limit_up_count": recent_limit_up_count,
            "prior7_limitup_days": prior7_limitup_days,
            "prior7_strong_days": prior7_strong_days,
            "max_consecutive_limit_up_days": 0,
            "support_type": support_type,
            "support_level": support_level,
            "support_strength": round(support_strength, 2),
            "expected_open_low": expected_open_low,
            "expected_open_high": expected_open_high,
            "expected_auction_pattern": expected_pattern,
            "need_last_minute_grab": True,
            "need_plate_follow": True,
            "evidence_json": json.dumps(evidence, ensure_ascii=False),
        }

    async def _async_to_candidate(self, row: asyncpg.Record, trade_date: date, next_trade_date: date) -> Optional[Dict[str, Any]]:
        """异步版本：统一使用独立支撑评分器。"""
        stock_id = self._normalize_stock_id(str(row.get("stock_id") or ""), str(row.get("stock_code") or ""))
        if not stock_id:
            return None

        support = await self.support_scorer.score(
            stock_id=stock_id,
            trade_date=trade_date,
            current_bar={
                "pct_chg": float(row.get("pct_chg") or 0.0),
                "low_price": float(row.get("low_price") or 0.0),
                "close_price": float(row.get("close_price") or 0.0),
            },
            prev_bar={
                "pct_chg": float(row.get("prev_day_pct_chg") or 0.0),
                "low_price": float(row.get("prev_day_low_price") or 0.0),
                "close_price": float(row.get("prev_day_close_price") or 0.0),
            },
        )

        return self._to_candidate(
            row,
            trade_date,
            next_trade_date,
            support_type_override=support.support_type,
            support_level_override=support.support_level,
            support_strength_override=support.support_strength,
            support_breakdown=support.support_breakdown,
            support_refs=support.evidence_refs,
        )

    def _apply_watch_context(self, candidate: Dict[str, Any], row: asyncpg.Record) -> Dict[str, Any]:
        watch_pool_entry_type = str(row.get("watch_pool_entry_type") or "observe_only")
        watch_score = float(row.get("watch_score") or 0.0)
        watch_labels = self._coerce_json_dict(row.get("watch_labels_json"))
        strong_grade = str(watch_labels.get("strong_grade") or "").upper()
        strong_whitelist = strong_grade in {"S", "A"}

        if watch_pool_entry_type == "formal" and candidate.get("pool_entry_type") == "observe_only":
            candidate["pool_entry_type"] = "formal"
            candidate["candidate_score"] = min(100.0, max(float(candidate.get("candidate_score") or 0.0), 70.0))
        if strong_grade == "B":
            candidate["pool_entry_type"] = "observe_only"
            candidate["candidate_score"] = min(69.0, float(candidate.get("candidate_score") or 0.0))
        elif strong_whitelist and candidate.get("pool_entry_type") == "observe_only":
            # S/A 白名单允许优先进入 formal（仍需后续盘前确认）
            candidate["pool_entry_type"] = "formal"
            candidate["candidate_score"] = min(100.0, max(float(candidate.get("candidate_score") or 0.0), 72.0))

        # 观察池来源候选加一个轻量优先权，避免在限额下被静态噪声挤掉。
        score_boost = min(max(watch_score * 0.08, 0.0), 8.0)
        if strong_whitelist:
            score_boost = min(12.0, score_boost + 3.0)
        candidate["candidate_score"] = round(min(100.0, float(candidate.get("candidate_score") or 0.0) + score_boost), 2)
        return candidate

    def _coerce_json_dict(self, value: Any) -> Dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str) and value:
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    def _candidate_has_sa_watch_whitelist(self, candidate: Dict[str, Any]) -> bool:
        evidence_raw = str(candidate.get("evidence_json") or "{}")
        try:
            evidence = json.loads(evidence_raw)
        except Exception:
            return False
        refs = evidence.get("source_refs") or []
        if not isinstance(refs, list):
            return False
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            if str(ref.get("source_tag") or "") != self.WATCH_SOURCE_TAG:
                continue
            grade = str(ref.get("strong_grade") or "").upper()
            if grade in {"S", "A"}:
                return True
        return False

    def _enforce_formal_sa_whitelist(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # 强约束：候选来源必须是强势股观察池，屏蔽任何外部来源回流。
        pool_only: List[Dict[str, Any]] = []
        for candidate in candidates:
            evidence_raw = str(candidate.get("evidence_json") or "{}")
            try:
                evidence = json.loads(evidence_raw)
            except Exception:
                continue
            refs = evidence.get("source_refs") or []
            if not isinstance(refs, list):
                continue
            has_watch_source = any(
                isinstance(ref, dict) and str(ref.get("source_tag") or "") == self.WATCH_SOURCE_TAG
                for ref in refs
            )
            if has_watch_source:
                pool_only.append(candidate)

        if self.formal_sa_gate_mode == "off":
            return pool_only

        out: List[Dict[str, Any]] = []
        for candidate in pool_only:
            entry = str(candidate.get("pool_entry_type") or "").lower()
            if entry != "formal":
                out.append(candidate)
                continue

            has_sa_whitelist = self._candidate_has_sa_watch_whitelist(candidate)
            if has_sa_whitelist:
                out.append(candidate)
                continue

            if self.formal_sa_gate_mode == "hard":
                continue

            # soft: 降级 observe_only，保留观察
            candidate["pool_entry_type"] = "observe_only"
            candidate["candidate_score"] = round(min(69.0, float(candidate.get("candidate_score") or 0.0)), 2)
            out.append(candidate)
        return out

    def _merge_candidate(self, merged: Dict[str, Dict[str, Any]], candidate: Dict[str, Any]) -> None:
        stock_id = str(candidate.get("stock_id") or "")
        if not stock_id:
            return
        current = merged.get(stock_id)
        if current is None:
            merged[stock_id] = candidate
            return
        if self._is_better_candidate(candidate, current):
            merged[stock_id] = candidate
        else:
            self._merge_source_tags(current, candidate)

    def _pool_entry_rank(self, value: str) -> int:
        if value == "formal":
            return 2
        if value == "observe_only":
            return 1
        return 0

    def _is_better_candidate(self, incoming: Dict[str, Any], current: Dict[str, Any]) -> bool:
        incoming_rank = self._pool_entry_rank(str(incoming.get("pool_entry_type") or ""))
        current_rank = self._pool_entry_rank(str(current.get("pool_entry_type") or ""))
        if incoming_rank != current_rank:
            return incoming_rank > current_rank
        return float(incoming.get("candidate_score") or 0.0) > float(current.get("candidate_score") or 0.0)

    def _attach_source_metadata(
        self,
        candidate: Dict[str, Any],
        *,
        source_tag: str,
        source_meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        evidence_json = str(candidate.get("evidence_json") or "{}")
        try:
            evidence = json.loads(evidence_json)
        except Exception:
            evidence = {}
        source_meta = source_meta or {}
        source_refs = list(evidence.get("source_refs") or [])
        source_refs.append({"source_tag": source_tag, **source_meta})
        evidence["source_refs"] = source_refs
        evidence["source_summary"] = sorted({str(x.get("source_tag") or "") for x in source_refs if x.get("source_tag")})
        candidate["evidence_json"] = json.dumps(evidence, ensure_ascii=False)

    def _merge_source_tags(self, target: Dict[str, Any], source: Dict[str, Any]) -> None:
        try:
            target_evidence = json.loads(str(target.get("evidence_json") or "{}"))
        except Exception:
            target_evidence = {}
        try:
            source_evidence = json.loads(str(source.get("evidence_json") or "{}"))
        except Exception:
            source_evidence = {}
        merged_refs = list(target_evidence.get("source_refs") or [])
        merged_refs.extend(list(source_evidence.get("source_refs") or []))
        dedup: Dict[str, Dict[str, Any]] = {}
        for ref in merged_refs:
            if not isinstance(ref, dict):
                continue
            key = json.dumps(ref, sort_keys=True, ensure_ascii=False)
            dedup[key] = ref
        refs = list(dedup.values())
        target_evidence["source_refs"] = refs
        target_evidence["source_summary"] = sorted({str(x.get("source_tag") or "") for x in refs if x.get("source_tag")})
        target["evidence_json"] = json.dumps(target_evidence, ensure_ascii=False)

    def _classify_weak_type(self, pct_chg: float, prev_day_pct: float, prev_day_limit_up: bool) -> Tuple[str, float]:
        if prev_day_limit_up and pct_chg < 0:
            return "bad_limit_up", min(100.0, abs(pct_chg) * 12.0 + 20.0)
        if pct_chg <= -5.0:
            return "big_negative_line", min(100.0, abs(pct_chg) * 10.0)
        if -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
            return "upper_shadow", 55.0
        if pct_chg <= -1.0:
            return "high_open_low_close", min(100.0, abs(pct_chg) * 8.0 + 10.0)
        return "fake_break", 40.0

    def _day_weak_score(self, pct_chg: float) -> float:
        if pct_chg < -4.0:
            return 20.0
        if pct_chg < -2.0:
            return 16.0
        if pct_chg < -1.0:
            return 10.0
        if pct_chg < 0:
            return 6.0
        return 0.0

    def _prev_day_weak_score(self, prev_day_pct: float) -> float:
        if prev_day_pct < -3.0:
            return 10.0
        if prev_day_pct < -1.5:
            return 8.0
        if prev_day_pct < 0:
            return 5.0
        return 0.0

    def _weekly_midterm_gate(self, support_breakdown: Optional[Dict[str, Any]]) -> Tuple[bool, Dict[str, Any]]:
        """周线门禁（当前为消融模式）：暂不拦截，仅输出诊断。"""
        weekly = {}
        if isinstance(support_breakdown, dict):
            weekly = support_breakdown.get("weekly_context") or {}
        if not isinstance(weekly, dict):
            weekly = {}

        data_ok = bool(weekly.get("weekly_data_sufficient") or False)
        trend_up = bool(weekly.get("weekly_trend_up") or False)
        filter_pass = bool(weekly.get("weekly_filter_pass") or False)
        high_fall = bool(weekly.get("weekly_high_fall_flag") or False)
        position_pct = float(weekly.get("weekly_position_pct") or 1.0)
        pullback_pct = float(weekly.get("weekly_pullback_pct") or 0.0)

        passed = True
        reason = "weekly_gate_disabled_ablation"

        return passed, {
            "passed": passed,
            "reason": reason,
            "weekly_data_sufficient": data_ok,
            "weekly_trend_up": trend_up,
            "weekly_filter_pass": filter_pass,
            "weekly_high_fall_flag": high_fall,
            "weekly_position_pct": round(position_pct, 4),
            "weekly_pullback_pct": round(pullback_pct, 4),
        }

    def classify_pool_entry(
        self,
        *,
        is_main_theme: bool,
        final_mainline_alive: bool,
        fade_confirmed: bool,
        fade_watch: bool,
        mainline_strength_score: float,
        leader_alive_score: float,
        event_continuity_score: float,
        strong_background: bool,
        repair_window: bool,
        support_strength: float,
        support_available: bool,
        recent_limit_up_count: int,
        day_pct_chg: float,
        prev_day_pct_chg: float,
        day_weak_score: float,
        prev_day_weak_score: float,
    ) -> Tuple[str, float, Dict[str, float]]:
        if not support_available:
            return "reject", 0.0, {"support_available": 0.0}
        # 候选层只做弱转强本体判定：弱势+支撑+强势背景
        formal_allow = (
            support_strength >= 45.0
            and strong_background
            and day_weak_score >= 4.0
            and prev_day_weak_score >= 2.0
        )
        observe_only_allow = (
            support_strength >= 60.0
            and day_weak_score >= 3.0
            and prev_day_weak_score >= 2.0
        )

        support_norm = max(0.0, min(1.0, support_strength / 100.0))
        weak_norm = max(0.0, min(1.0, (day_weak_score + prev_day_weak_score) / 30.0))
        background_norm = 1.0 if strong_background else 0.5
        trend_norm = max(0.0, min(1.0, recent_limit_up_count / 4.0))
        confidence = max(
            0.0,
            min(1.0, support_norm * 0.52 + weak_norm * 0.26 + background_norm * 0.14 + trend_norm * 0.08),
        )
        components = {
            "support_norm": round(support_norm, 4),
            "weak_norm": round(weak_norm, 4),
            "background_norm": round(background_norm, 4),
            "trend_norm": round(trend_norm, 4),
            "formal_allow": 1.0 if formal_allow else 0.0,
            "observe_only_allow": 1.0 if observe_only_allow else 0.0,
            "recent_limit_up_count": float(recent_limit_up_count),
            "day_pct_chg": round(day_pct_chg, 4),
            "prev_day_pct_chg": round(prev_day_pct_chg, 4),
            "confidence": round(confidence, 4),
        }
        if formal_allow:
            return "formal", round(confidence, 4), components
        if observe_only_allow:
            return "observe_only", round(confidence, 4), components
        return "reject", round(confidence, 4), components

    def _classify_candidate_type(
        self,
        *,
        is_leader: bool,
        recent_limit_up_count: int,
        weak_type: str,
        rank_order: int,
    ) -> str:
        # 冲突优先级（高 -> 低）：
        # dragon_repair > subdragon_repair > bad_limit_repair > upper_shadow_repair > strong_trend_repair > generic_repair
        if is_leader and recent_limit_up_count >= 3:
            return "dragon_repair"
        if is_leader or rank_order <= 3:
            return "subdragon_repair"
        if weak_type == "bad_limit_up":
            return "bad_limit_repair"
        if weak_type == "upper_shadow":
            return "upper_shadow_repair"
        if recent_limit_up_count >= 1:
            return "strong_trend_repair"
        return "generic_repair"

    def _expected_open_range(self, candidate_type: str) -> Tuple[float, float]:
        if candidate_type == "dragon_repair":
            return (0.0, 4.0)
        if candidate_type == "subdragon_repair":
            return (0.5, 4.5)
        if candidate_type == "bad_limit_repair":
            return (1.0, 5.0)
        if candidate_type == "upper_shadow_repair":
            return (0.0, 3.0)
        if candidate_type == "strong_trend_repair":
            return (0.5, 4.0)
        return (0.0, 3.0)

    def _expected_pattern(self, candidate_type: str) -> str:
        if candidate_type in {"dragon_repair", "subdragon_repair"}:
            return "tail_lift_or_stair_up"
        if candidate_type == "bad_limit_repair":
            return "u_recover_then_lift"
        if candidate_type == "upper_shadow_repair":
            return "stable_red_with_tail_lift"
        return "stable_red"

    async def analyze_strict_support(self, stock_id: str, pct_chg: float, trade_date: date) -> Dict[str, Any]:
        """
        增强支撑位分析 - 使用KlineDataService进行完整的支撑位检测，支持多种支撑类型组合

        返回: {
            'has_support': bool,
            'support_type': str,  # 主要支撑类型: gap, previous_low, previous_close, integer_level
            'support_strength': float,  # 0.0-1.0 (组合支撑强度)
            'support_level': float,
            'is_gap_support': bool,
            'support_types': List[Dict],  # 所有检测到的支撑类型
            'support_count': int,  # 支撑类型数量
            'combined_strength': float,  # 组合支撑强度(0.0-1.0)
            'primary_type': str  # 主要支撑类型
        }
        """
        try:
            # 使用KlineDataService分析支撑位
            # 清理股票ID：KlineDataService期望不带后缀的6位代码
            raw_stock_id = stock_id.split('.')[0] if '.' in stock_id else stock_id
            gap_analysis = await self.kline_service.analyze_gap_support(raw_stock_id, trade_date)

            # 收集所有可能的支撑类型
            support_types = []

            # 1. 检查缺口支撑
            if gap_analysis.get('has_support', False):
                support_type = gap_analysis.get('support_type', '')
                support_strength = gap_analysis.get('support_strength', 0.0)
                support_level = gap_analysis.get('support_level', 0.0)
                is_gap_support = gap_analysis.get('is_gap_support', False)

                # 添加主要支撑类型
                support_types.append({
                    'type': support_type,
                    'strength': support_strength,
                    'level': support_level,
                    'is_gap_support': is_gap_support,
                    'description': self._get_support_description(support_type, support_level)
                })

                # 如果缺口支撑存在，检查是否还有其他隐含支撑
                # 例如：缺口支撑通常也意味着前一日低点支撑
                if support_type == 'gap_support' and support_level > 0:
                    # 添加前一日低点支撑（强度较低）
                    support_types.append({
                        'type': 'previous_low',
                        'strength': min(0.6, support_strength * 0.75),  # 前一日低点强度约为缺口支撑的75%
                        'level': support_level,  # 缺口下沿通常也是前一日高点
                        'is_gap_support': False,
                        'description': '前一日高点/低点支撑'
                    })

            # 2. 检查前一日低点支撑（简单方法）
            # 获取K线数据以检测前一日低点（增加天数以确保获取前一日数据）
            kline_data = await self.kline_service.get_kline_data(raw_stock_id, trade_date, days_before=5, days_after=0)
            if len(kline_data) >= 2:
                # 找到目标日期和前一日
                target_kline = None
                prev_kline = None

                for kline in kline_data:
                    if kline['trade_date'] == trade_date:
                        target_kline = kline
                    elif target_kline is None and kline['trade_date'] < trade_date:
                        prev_kline = kline

                if target_kline and prev_kline:
                    current_low = target_kline.get('low_price', 0)
                    prev_low = prev_kline.get('low_price', 0)

                    # 检查是否在前一日低点附近获得支撑
                    if prev_low > 0 and current_low > 0:
                        distance_pct = abs(current_low - prev_low) / prev_low * 100
                        if distance_pct < 7.0:  # 放宽到7%以内认为是支撑（A股波动较大）
                            # 检查是否已存在相同类型的支撑
                            existing_prev_low = any(st['type'] == 'previous_low' for st in support_types)
                            if not existing_prev_low:
                                support_types.append({
                                    'type': 'previous_low',
                                    'strength': 0.6,
                                    'level': prev_low,
                                    'is_gap_support': False,
                                    'description': f'前一日低点支撑 {prev_low:.2f}（距离{distance_pct:.1f}%）'
                                })

                    # 3. 检查整数关口支撑
                    if current_low > 0:
                        # 检查关键整数位
                        integer_levels = [1.00, 2.00, 5.00, 10.00, 20.00, 50.00]
                        for base in integer_levels:
                            for multiplier in [0.5, 1.0, 1.5, 2.0]:
                                level = base * multiplier
                                if abs(current_low - level) / level < 0.02:  # 2%以内
                                    # 检查是否已存在相同类型的支撑
                                    existing_integer = any(st['type'] == 'integer_level' for st in support_types)
                                    if not existing_integer:
                                        support_types.append({
                                            'type': 'integer_level',
                                            'strength': 0.4,
                                            'level': level,
                                            'is_gap_support': False,
                                            'description': f'整数关口支撑 {level:.2f}'
                                        })
                                    break  # 只取第一个匹配的整数位

            # 计算组合支撑强度
            has_support = len(support_types) > 0
            combined_strength = 0.0
            primary_type = ''
            support_level = 0.0
            is_gap_support = False

            if has_support:
                # 按支撑强度排序
                support_types.sort(key=lambda x: x['strength'], reverse=True)

                # 主要支撑类型是强度最高的
                primary_support = support_types[0]
                primary_type = primary_support['type']
                support_level = primary_support['level']
                is_gap_support = primary_support.get('is_gap_support', False)

                # 计算组合支撑强度
                max_strength = primary_support['strength']
                support_count = len(support_types)

                # 多种支撑存在时增加强度加成
                # 每多一种支撑类型增加5%强度，最多增加20%
                strength_bonus = min(0.2, (support_count - 1) * 0.05)
                combined_strength = min(1.0, max_strength + strength_bonus)

            # 构建返回结果（保持向后兼容）
            result = {
                'has_support': has_support,
                'support_type': primary_type,  # 主要支撑类型
                'support_strength': combined_strength,  # 组合支撑强度
                'support_level': support_level,
                'is_gap_support': is_gap_support,
                # 新增字段
                'support_types': support_types,
                'support_count': len(support_types),
                'combined_strength': combined_strength,
                'primary_type': primary_type
            }

            return result

        except Exception as e:
            # 如果分析失败，回退到简单支撑检测
            print(f"支撑位分析失败 {stock_id} {trade_date}: {e}")
            # 返回空结果
            return {
                'has_support': False,
                'support_type': '',
                'support_strength': 0.0,
                'support_level': 0.0,
                'is_gap_support': False,
                'support_types': [],
                'support_count': 0,
                'combined_strength': 0.0,
                'primary_type': ''
            }

    def _get_support_description(self, support_type: str, level: float) -> str:
        """获取支撑类型的描述"""
        descriptions = {
            'gap_support': f'缺口支撑 {level:.2f}',
            'previous_low': f'前一日低点支撑 {level:.2f}',
            'previous_close': f'前一日收盘价支撑 {level:.2f}',
            'integer_level': f'整数关口支撑 {level:.2f}',
            'ma5': '5日均线支撑',
            'break_recover': '突破回踩支撑',
            'none': '无明确支撑'
        }
        return descriptions.get(support_type, f'{support_type}支撑 {level:.2f}')

    def _support_type_from_row(self, pct_chg: float, prev_day_pct: float) -> str:
        if prev_day_pct <= -4.0 and pct_chg > -2.0:
            return "previous_low"
        if -1.5 <= pct_chg <= 1.5:
            return "ma5"
        if pct_chg > 1.5:
            return "break_recover"
        return "none"

    def _support_strength(self, pct_chg: float, prev_day_pct: float, support_type: str) -> float:
        base = 20.0 if support_type == "none" else 45.0
        if prev_day_pct <= -4.0:
            base += 15.0
        if -1.5 <= pct_chg <= 2.5:
            base += 10.0
        return min(base, 95.0)

    def _candidate_score(
        self,
        *,
        is_leader: bool,
        limit_up: bool,
        recent_limit_up_count: int,
        rank_order: int,
        stage: str,
        weak_intensity: float,
        support_strength: float,
        day_weak_score: float = 0.0,
        prev_day_weak_score: float = 0.0,
        mainline_strength_score: float = 0.0,
        fade_watch: bool = False,
    ) -> float:
        score = 45.0
        if is_leader:
            score += 18.0
        if limit_up:
            score += 10.0
        score += min(recent_limit_up_count * 4.0, 12.0)
        if rank_order <= 3:
            score += 8.0
        if stage in {"rebound", "fermentation", "回流", "发酵", "启动"}:
            score += 8.0
        score += min(weak_intensity * 0.08, 8.0)
        score += min(support_strength * 0.1, 9.0)
        score += day_weak_score + prev_day_weak_score
        score += min(mainline_strength_score * 0.08, 8.0)
        score -= self._fade_watch_penalty(
            fade_watch=fade_watch,
            mainline_strength_score=mainline_strength_score,
        )
        return max(0.0, min(score, 100.0))

    def _fade_watch_penalty(self, *, fade_watch: bool, mainline_strength_score: float) -> float:
        if not fade_watch:
            return 0.0
        if mainline_strength_score >= 75.0:
            return 4.0
        if mainline_strength_score >= 60.0:
            return 8.0
        return 12.0

    def _normalize_stock_id(self, raw_stock_id: str, stock_code: str) -> str:
        normalized = normalize_stock_id(raw_stock_id)
        if normalized:
            return normalized
        return normalize_stock_id(stock_code)

    async def _replace_candidates(self, next_trade_date: date, candidates: List[Dict[str, Any]]) -> int:
        pool = await self._ensure_pool()
        sql = """
        INSERT INTO weak_to_strong_candidate_pool (
            trade_date, next_trade_date, stock_id, stock_name,
            subject_key, theme_name, candidate_score, candidate_type, rule_version,
            weak_type, weak_intensity, is_dragon_head, dragon_head_level,
            prev_limit_up_count, max_consecutive_limit_up_days,
            support_type, support_level, support_strength,
            expected_open_low, expected_open_high, expected_auction_pattern,
            need_last_minute_grab, need_plate_follow, evidence_json,
            pool_entry_type, cycle_state, mainline_strength_score, fade_watch, fade_confirmed,
            created_at
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21,
            $22, $23, $24::jsonb, $25, $26, $27, $28, $29, NOW()
        )
        ON CONFLICT (next_trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            candidate_score = EXCLUDED.candidate_score,
            candidate_type = EXCLUDED.candidate_type,
            rule_version = EXCLUDED.rule_version,
            weak_type = EXCLUDED.weak_type,
            weak_intensity = EXCLUDED.weak_intensity,
            is_dragon_head = EXCLUDED.is_dragon_head,
            dragon_head_level = EXCLUDED.dragon_head_level,
            prev_limit_up_count = EXCLUDED.prev_limit_up_count,
            max_consecutive_limit_up_days = EXCLUDED.max_consecutive_limit_up_days,
            support_type = EXCLUDED.support_type,
            support_level = EXCLUDED.support_level,
            support_strength = EXCLUDED.support_strength,
            expected_open_low = EXCLUDED.expected_open_low,
            expected_open_high = EXCLUDED.expected_open_high,
            expected_auction_pattern = EXCLUDED.expected_auction_pattern,
            need_last_minute_grab = EXCLUDED.need_last_minute_grab,
            need_plate_follow = EXCLUDED.need_plate_follow,
            evidence_json = EXCLUDED.evidence_json,
            pool_entry_type = EXCLUDED.pool_entry_type,
            cycle_state = EXCLUDED.cycle_state,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_watch = EXCLUDED.fade_watch,
            fade_confirmed = EXCLUDED.fade_confirmed
        """
        inserted = 0
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    DELETE FROM weak_to_strong_candidate_pool
                    WHERE next_trade_date = $1::date
                    """,
                    next_trade_date,
                )
                for c in candidates:
                    await conn.execute(
                        sql,
                        c["trade_date"],
                        c["next_trade_date"],
                        c["stock_id"],
                        c["stock_name"],
                        c["subject_key"],
                        c["theme_name"],
                        c["candidate_score"],
                        c["candidate_type"],
                        c["rule_version"],
                        c["weak_type"],
                        c["weak_intensity"],
                        c["is_dragon_head"],
                        c["dragon_head_level"],
                        c["prev_limit_up_count"],
                        c["max_consecutive_limit_up_days"],
                        c["support_type"],
                        c["support_level"],
                        c["support_strength"],
                        c["expected_open_low"],
                        c["expected_open_high"],
                        c["expected_auction_pattern"],
                        c["need_last_minute_grab"],
                        c["need_plate_follow"],
                        c["evidence_json"],
                        c.get("pool_entry_type", "formal"),
                        c.get("cycle_state", ""),
                        c.get("mainline_strength_score", 0.0),
                        c.get("fade_watch", False),
                        c.get("fade_confirmed", False),
                    )
                    inserted += 1
        return inserted

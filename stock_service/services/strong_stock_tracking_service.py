from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import asyncpg

from stock_service.config import StockServiceConfig
from stock_service.domain.cycle_states import (
    CYCLE_STATES,
    CYCLE_STATE_DIVERGENCE,
    CYCLE_STATE_FADE_CONFIRMED,
    CYCLE_STATE_FADE_WATCH,
    CYCLE_STATE_REPAIR,
)
from stock_service.services.weak_to_strong_support_scorer import WeakToStrongSupportScorer
from stock_service.utils.security_id import normalize_stock_id


@dataclass
class WatchSeedRow:
    stock_id: str
    stock_name: str
    subject_key: str
    theme_name: str
    source_tag: str
    relay_role: str
    labels: Dict[str, Any]
    evidence: Dict[str, Any]


@dataclass
class WatchScoreResult:
    watch_score: float
    watch_priority: float
    watch_status: str
    pool_entry_type: str
    cycle_state: str
    mainline_strength_score: float
    fade_watch: bool
    fade_confirmed: bool
    support_type: Optional[str]
    support_level: Optional[float]
    support_score: float
    labels: Dict[str, Any]
    evidence: Dict[str, Any]


class StrongStockTrackingService:
    """强势股持续跟踪观察池（Phase 1: seed/refresh/history）。"""

    RULE_VERSION = "strong_stock_watch.v2"
    ACTIVE_MIN_SCORE = 72.0
    WEAKENING_MIN_SCORE = 62.0
    OBSERVE_MIN_SCORE = 62.0
    FORMAL_MIN_SCORE = 78.0
    FORMAL_MIN_MAINLINE = 65.0
    STRONG_GRADE_S_MIN = 80.0
    STRONG_GRADE_A_MIN = 65.0
    STRONG_GRADE_B_MIN = 50.0

    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
        self.pool: Optional[asyncpg.Pool] = None
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
                max_size=4,
            )
        return self.pool

    async def close(self) -> None:
        await self.support_scorer.close()
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def seed_watch_pool(self, trade_date: date) -> int:
        pool = await self._ensure_pool()
        rows = await self._fetch_seed_rows(trade_date)
        inserted_or_updated = 0

        async with pool.acquire() as conn:
            async with conn.transaction():
                for row in rows:
                    inserted_or_updated += await self._upsert_watch_pool_seed(conn, trade_date, row)
                    await self._recompute_watch_window_days(conn, row.stock_id)
                    await self._append_watch_history(conn, trade_date, row.stock_id)
        return inserted_or_updated

    async def refresh_watch_pool(self, trade_date: date) -> int:
        pool = await self._ensure_pool()
        current_rows = await self._fetch_refresh_watch_pool(trade_date)
        updated = 0

        async with pool.acquire() as conn:
            async with conn.transaction():
                for row in current_rows:
                    result = await self._score_watch_row(conn, trade_date, row)
                    await self._update_watch_pool_row(conn, trade_date, row, result)
                    await self._recompute_watch_window_days(conn, str(row["stock_id"]))
                    await self._append_watch_history(conn, trade_date, row["stock_id"])
                    updated += 1
        return updated

    async def promote_watch_candidates(self, trade_date: date) -> int:
        """
        将观察池中可继续参与弱转强的对象标记为已升级。
        与候选池的实际合流由 CandidateBuilder 在同日读取 watch_pool 完成。
        """
        pool = await self._ensure_pool()
        sql = """
        UPDATE strong_stock_watch_pool
        SET candidate_promoted = TRUE,
            updated_at = now()
        WHERE watch_status IN ('active', 'weakening')
          AND pool_entry_type IN ('formal', 'observe_only')
          AND COALESCE(fade_confirmed, FALSE) = FALSE
          AND candidate_promoted = FALSE
          AND last_trade_date <= $1::date
        """
        async with pool.acquire() as conn:
            result = await conn.execute(sql, trade_date)
        return int(str(result).split()[-1])

    async def prune_watch_pool(self, trade_date: date) -> int:
        """
        清理已失效观察对象：
        1) 已确认退潮；2) 弱化且评分持续偏低；3) 7日窗口到期未获续命。
        """
        pool = await self._ensure_pool()
        async with pool.acquire() as conn:
            cutoff_trade_date = await self._resolve_cutoff_trade_date(conn, trade_date, lookback_trade_days=3)
        sql = """
        UPDATE strong_stock_watch_pool
        SET watch_status = 'removed',
            pool_entry_type = 'reject',
            updated_at = now()
        WHERE (
                COALESCE(fade_confirmed, FALSE) = TRUE
             OR (
                    watch_status = 'weakening'
                AND watch_score < $2
                AND last_trade_date <= $1::date
             )
             OR (
                    watch_window_days >= 7
                AND watch_status <> 'removed'
             )
        )
          AND watch_status <> 'removed'
        """
        async with pool.acquire() as conn:
            result = await conn.execute(sql, cutoff_trade_date, self.WEAKENING_MIN_SCORE)
            # 将本次被清理对象写入历史快照，便于回放复盘。
            rows = await conn.fetch(
                """
                SELECT stock_id FROM strong_stock_watch_pool
                WHERE watch_status = 'removed'
                  AND updated_at::date = $1::date
                """,
                trade_date,
            )
            async with conn.transaction():
                for row in rows:
                    await self._append_watch_history(conn, trade_date, row["stock_id"])
        return int(str(result).split()[-1])

    async def snapshot_watch_pool(self, trade_date: date) -> int:
        """将当前活动池按交易日写入 history 快照（幂等）。"""
        pool = await self._ensure_pool()
        sql = """
        SELECT stock_id
        FROM strong_stock_watch_pool
        WHERE watch_status IN ('pending_seed', 'pending_refresh', 'active', 'weakening', 'removed')
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
            async with conn.transaction():
                for row in rows:
                    await self._append_watch_history(conn, trade_date, row["stock_id"])
        return len(rows)

    async def list_screening_candidates(self, trade_date: date) -> List[Dict[str, str]]:
        """为选股器提供观察池候选（formal/observe_only，按优先级降序）。"""
        rows = await self._fetch_active_watch_pool(trade_date)
        out: List[Dict[str, str]] = []
        seen: set[str] = set()
        for row in rows:
            pool_entry_type = str(row.get("pool_entry_type") or "").lower()
            if pool_entry_type not in {"formal", "observe_only"}:
                continue
            stock_id = normalize_stock_id(str(row.get("stock_id") or ""))
            if not stock_id:
                continue
            stock_code = stock_id.split(".", 1)[0]
            if stock_code in seen:
                continue
            seen.add(stock_code)
            out.append(
                {
                    "stock_id": stock_code,
                    "stock_name": str(row.get("stock_name") or stock_code),
                }
            )
        return out

    async def _fetch_seed_rows(self, trade_date: date) -> List[WatchSeedRow]:
        pool = await self._ensure_pool()
        sql = """
        WITH recent_trade_days AS (
            SELECT t.trade_date
            FROM (
                SELECT DISTINCT s.trade_date
                FROM subject_stock_daily_snapshot s
                WHERE s.trade_date <= $1::date
                ORDER BY s.trade_date DESC
                LIMIT 7
            ) t
        ),
        recent AS (
            SELECT
                stock_id,
                MAX(stock_name) AS stock_name,
                subject_key,
                COUNT(DISTINCT trade_date) FILTER (WHERE COALESCE(limit_up, FALSE)) AS recent_limit_up_count,
                MAX(CASE WHEN COALESCE(is_leader, FALSE) THEN 1 ELSE 0 END) AS is_leader_flag,
                MIN(COALESCE(rank_order, 999)) AS best_rank,
                MAX(
                    CASE
                        WHEN trade_date = $1::date
                             AND jsonb_typeof(raw_json) = 'array'
                             AND jsonb_array_length(raw_json) > 20
                        THEN COALESCE(NULLIF(raw_json->>20, ''), '0')::int
                        ELSE 0
                    END
                ) AS current_flag_today
            FROM subject_stock_daily_snapshot
            WHERE trade_date IN (SELECT trade_date FROM recent_trade_days)
            GROUP BY stock_id, subject_key
        ),
        subject_strength AS (
            SELECT
                subject_key,
                COUNT(DISTINCT stock_id) FILTER (WHERE COALESCE(limit_up, FALSE)) AS subject_limit_up_count,
                COUNT(DISTINCT stock_id) FILTER (
                    WHERE COALESCE(limit_up, FALSE)
                       OR COALESCE(pct_chg, 0) >= 7.0
                       OR COALESCE(rank_order, 999) <= 3
                ) AS subject_strong_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date
            GROUP BY subject_key
        ),
        eligible AS (
            SELECT
                r.*,
                COALESCE(v2.theme_name, r.subject_key) AS theme_name,
                COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
                COALESCE(mr.identity_status, 'observed') AS identity_status,
                (
                    COALESCE(mr.is_main_theme, FALSE)
                    AND COALESCE(mr.identity_status, '') = 'confirmed'
                    AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, '')) <> 'fade_confirmed'
                    AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
                ) AS final_mainline_alive,
                COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) AS mainline_strength_score,
                COALESCE(ss.subject_limit_up_count, 0) AS subject_limit_up_count,
                COALESCE(ss.subject_strong_count, 0) AS subject_strong_count
            FROM recent r
            LEFT JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = r.subject_key
            LEFT JOIN mainline_state_daily msd
              ON msd.trade_date = $1::date
             AND msd.subject_key = r.subject_key
            LEFT JOIN theme_cycle_judgement_v2 v2
              ON v2.trade_date = $1::date
             AND v2.subject_key = r.subject_key
            LEFT JOIN subject_strength ss
              ON ss.subject_key = r.subject_key
            WHERE (
                    (
                        COALESCE(mr.is_main_theme, FALSE) = TRUE
                        AND COALESCE(mr.identity_status, '') = 'confirmed'
                        AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, '')) <> 'fade_confirmed'
                        AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
                        AND (
                              COALESCE(ss.subject_limit_up_count, 0) >= 2
                              OR COALESCE(ss.subject_strong_count, 0) >= 3
                        )
                    )
                    OR COALESCE(r.recent_limit_up_count, 0) >= 2
              )
        ),
        ranked AS (
            SELECT
                e.*,
                CASE
                    WHEN e.recent_limit_up_count >= 2
                      OR (e.is_leader_flag = 1 AND e.recent_limit_up_count >= 1)
                    THEN 1 ELSE 0
                END AS cond_gene,
                CASE WHEN e.current_flag_today >= 2 THEN 1 ELSE 0 END AS cond_volume,
                CASE WHEN e.is_leader_flag = 1 OR e.best_rank <= 5 THEN 1 ELSE 0 END AS cond_structure,
                ROW_NUMBER() OVER (
                    PARTITION BY e.stock_id
                    ORDER BY
                        e.mainline_strength_score DESC,
                        e.subject_limit_up_count DESC,
                        e.subject_strong_count DESC,
                        e.recent_limit_up_count DESC,
                        e.is_leader_flag DESC,
                        e.best_rank ASC
                ) AS rn
            FROM eligible e
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
          AND (
                COALESCE(recent_limit_up_count, 0) >= 2
                OR (
                    COALESCE(recent_limit_up_count, 0) >= 1
                    AND (cond_gene + cond_volume + cond_structure) >= 2
                )
              )
        ORDER BY mainline_strength_score DESC, recent_limit_up_count DESC, best_rank ASC
        """
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, trade_date)

        dedup: Dict[str, WatchSeedRow] = {}
        for row in rows:
            stock_id = normalize_stock_id(str(row.get("stock_id") or ""))
            if not stock_id:
                continue
            stock_name = str(row.get("stock_name") or stock_id)
            if self._is_disallowed_watch_stock(stock_id, stock_name):
                continue

            recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
            is_leader = bool(row.get("is_leader_flag") or 0)
            best_rank = int(row.get("best_rank") or 999)

            if recent_limit_up_count >= 4:
                source_tag = "4_limit_up"
            elif recent_limit_up_count >= 3:
                source_tag = "3_limit_up"
            elif recent_limit_up_count >= 2:
                source_tag = "2_limit_up"
            elif is_leader:
                source_tag = "leader_core"
            else:
                source_tag = "front_row_core"

            if is_leader:
                relay_role = "dragon"
            elif best_rank <= 3:
                relay_role = "sub_dragon"
            else:
                relay_role = "unknown"

            labels = {
                "has_recent_limit_up": recent_limit_up_count > 0,
                "recent_limit_up_count": recent_limit_up_count,
                "current_flag_today": int(row.get("current_flag_today") or 0),
                "is_dragon_head": is_leader,
                "is_front_row_core": best_rank <= 3,
                "watch_window_days": 7,
                "mainline_identity_confirmed": True,
                "board_effect_confirmed": (
                    int(row.get("subject_limit_up_count") or 0) >= 2
                    or int(row.get("subject_strong_count") or 0) >= 3
                ),
                "subject_limit_up_count": int(row.get("subject_limit_up_count") or 0),
                "subject_strong_count": int(row.get("subject_strong_count") or 0),
                "hard_gate_cond_gene": bool(int(row.get("cond_gene") or 0)),
                "hard_gate_cond_volume": bool(int(row.get("cond_volume") or 0)),
                "hard_gate_cond_structure": bool(int(row.get("cond_structure") or 0)),
                "hard_gate_pass_count": int(row.get("cond_gene") or 0)
                + int(row.get("cond_volume") or 0)
                + int(row.get("cond_structure") or 0),
            }
            evidence = {
                "schema_version": "watch_evidence.v1",
                "rule_version": self.RULE_VERSION,
                "seed_reason": {
                    "recent_limit_up_count": recent_limit_up_count,
                    "is_leader": is_leader,
                    "best_rank": best_rank,
                    "subject_limit_up_count": int(row.get("subject_limit_up_count") or 0),
                    "subject_strong_count": int(row.get("subject_strong_count") or 0),
                },
                "source": {"table": "subject_stock_daily_snapshot", "lookback_days": 7},
            }

            dedup[stock_id] = WatchSeedRow(
                stock_id=stock_id,
                stock_name=stock_name,
                subject_key=str(row.get("subject_key") or ""),
                theme_name=str(row.get("theme_name") or row.get("subject_key") or ""),
                source_tag=source_tag,
                relay_role=relay_role,
                labels=labels,
                evidence=evidence,
            )

        return list(dedup.values())

    async def _resolve_cutoff_trade_date(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        *,
        lookback_trade_days: int,
    ) -> date:
        """
        返回“向前 N 个交易日”的截止日（含当天计数）。
        例如 lookback_trade_days=3 时，返回最近 4 个交易日中最早那天。
        """
        window = max(int(lookback_trade_days), 0) + 1
        row = await conn.fetchrow(
            """
            SELECT x.trade_date
            FROM (
                SELECT DISTINCT s.trade_date
                FROM subject_stock_daily_snapshot s
                WHERE s.trade_date <= $1::date
                ORDER BY s.trade_date DESC
                LIMIT $2
            ) x
            ORDER BY x.trade_date ASC
            LIMIT 1
            """,
            trade_date,
            window,
        )
        return date.fromisoformat(str(row["trade_date"])) if row and row.get("trade_date") else trade_date

    async def _recompute_watch_window_days(self, conn: asyncpg.Connection, stock_id: str) -> None:
        """
        统一以交易日计数回填 watch_window_days，避免自然日偏差。
        """
        sql = """
        UPDATE strong_stock_watch_pool p
        SET watch_window_days = GREATEST(
            1,
            COALESCE(
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT DISTINCT s.trade_date
                        FROM subject_stock_daily_snapshot s
                        WHERE split_part(s.stock_id, '.', 1) = split_part(p.stock_id, '.', 1)
                          AND s.trade_date BETWEEN p.watch_start_date AND p.last_trade_date
                    ) d
                ),
                1
            )
        )
        WHERE p.stock_id = $1
        """
        await conn.execute(sql, normalize_stock_id(stock_id))

    async def _fetch_active_watch_pool(self, trade_date: date) -> List[asyncpg.Record]:
        pool = await self._ensure_pool()
        sql = """
        SELECT
          p.*,
          COALESCE(sf.current_flag_today, 0) AS current_flag_today
        FROM strong_stock_watch_pool
        p
        LEFT JOIN (
          SELECT
            split_part(stock_id, '.', 1) AS stock_code,
            MAX(
              CASE
                WHEN jsonb_typeof(raw_json) = 'array' AND jsonb_array_length(raw_json) > 20
                THEN COALESCE(NULLIF(raw_json->>20, ''), '0')::int
                ELSE 0
              END
            ) AS current_flag_today
          FROM subject_stock_daily_snapshot
          WHERE trade_date = $1::date
          GROUP BY split_part(stock_id, '.', 1)
        ) sf
          ON sf.stock_code = split_part(p.stock_id, '.', 1)
        WHERE p.watch_status IN ('active', 'weakening')
          AND p.last_trade_date <= $1::date
        ORDER BY watch_score DESC, watch_priority DESC
        """
        async with pool.acquire() as conn:
            return await conn.fetch(sql, trade_date)

    async def _fetch_refresh_watch_pool(self, trade_date: date) -> List[asyncpg.Record]:
        """
        refresh 阶段消费集合：
        - pending_seed / pending_refresh：待正式评分的新入池或滚动样本
        - active / weakening：在池样本的日更评分
        """
        pool = await self._ensure_pool()
        sql = """
        SELECT
          p.*,
          COALESCE(sf.current_flag_today, 0) AS current_flag_today
        FROM strong_stock_watch_pool p
        LEFT JOIN (
          SELECT
            split_part(stock_id, '.', 1) AS stock_code,
            MAX(
              CASE
                WHEN jsonb_typeof(raw_json) = 'array' AND jsonb_array_length(raw_json) > 20
                THEN COALESCE(NULLIF(raw_json->>20, ''), '0')::int
                ELSE 0
              END
            ) AS current_flag_today
          FROM subject_stock_daily_snapshot
          WHERE trade_date = $1::date
          GROUP BY split_part(stock_id, '.', 1)
        ) sf
          ON sf.stock_code = split_part(p.stock_id, '.', 1)
        WHERE p.watch_status IN ('pending_seed', 'pending_refresh', 'active', 'weakening')
          AND p.last_trade_date <= $1::date
        ORDER BY
          CASE
            WHEN p.watch_status = 'pending_seed' THEN 0
            WHEN p.watch_status = 'pending_refresh' THEN 1
            WHEN p.watch_status = 'active' THEN 2
            ELSE 3
          END ASC,
          p.watch_score DESC,
          p.watch_priority DESC
        """
        async with pool.acquire() as conn:
            return await conn.fetch(sql, trade_date)

    async def _score_watch_row(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        row: asyncpg.Record,
    ) -> WatchScoreResult:
        stock_id = normalize_stock_id(str(row.get("stock_id") or ""))
        stock_name = str(row.get("stock_name") or "")
        if self._is_disallowed_watch_stock(stock_id, stock_name):
            labels = self._coerce_json_object(row.get("labels_json"))
            labels.update(
                {
                    "removed_by_filter": True,
                    "removed_reason": "exclude_st_or_688",
                }
            )
            return WatchScoreResult(
                watch_score=0.0,
                watch_priority=0.0,
                watch_status="removed",
                pool_entry_type="reject",
                cycle_state=str(row.get("cycle_state") or ""),
                mainline_strength_score=float(row.get("mainline_strength_score") or 0.0),
                fade_watch=bool(row.get("fade_watch") or False),
                fade_confirmed=True,
                support_type=None,
                support_level=None,
                support_score=0.0,
                labels=labels,
                evidence={
                    "schema_version": "watch_evidence.v1",
                    "rule_version": self.RULE_VERSION,
                    "phase": "phase1_seed_refresh_history",
                    "removed_reason": "exclude_st_or_688",
                },
            )

        current_flag_today = int(row.get("current_flag_today") or 0)
        broken_board = current_flag_today < 2

        cycle = await conn.fetchrow(
            """
            SELECT
                COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
                (
                    COALESCE(mr.is_main_theme, FALSE)
                    AND COALESCE(mr.identity_status, '') = 'confirmed'
                    AND COALESCE(msd.state, COALESCE(v2.final_cycle_state, '')) <> 'fade_confirmed'
                    AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
                ) AS effective_mainline_alive,
                COALESCE(v2.fade_watch, COALESCE(msd.state, '') = 'fade_watch') AS fade_watch,
                COALESCE(v2.fade_confirmed, COALESCE(msd.state, '') = 'fade_confirmed') AS fade_confirmed,
                COALESCE(msd.mainline_strength_score, v2.mainline_strength_score, 0) AS mainline_strength_score,
                COALESCE(e.event_continuity_score, 0) AS event_continuity_score
            FROM theme_cycle_judgement_v2 v2
            LEFT JOIN theme_mainline_identity_registry mr
              ON mr.subject_key = v2.subject_key
            LEFT JOIN mainline_state_daily msd
              ON msd.trade_date = v2.trade_date
             AND msd.subject_key = v2.subject_key
            LEFT JOIN theme_cycle_evidence_daily e
              ON e.trade_date = v2.trade_date
             AND e.subject_key = v2.subject_key
            WHERE v2.trade_date = $1::date
              AND v2.subject_key = $2
            """,
            trade_date,
            row.get("subject_key"),
        )
        board = await conn.fetchrow(
            """
            SELECT
                COUNT(DISTINCT stock_id) FILTER (WHERE COALESCE(limit_up, FALSE)) AS subject_limit_up_count,
                COUNT(DISTINCT stock_id) FILTER (
                    WHERE COALESCE(limit_up, FALSE)
                       OR COALESCE(pct_chg, 0) >= 7.0
                       OR COALESCE(rank_order, 999) <= 3
                ) AS subject_strong_count
            FROM subject_stock_daily_snapshot
            WHERE trade_date = $1::date
              AND subject_key = $2
            """,
            trade_date,
            row.get("subject_key"),
        )
        current_bar, prev_bar = await self._fetch_support_bars(conn, trade_date, stock_id)
        support_result = await self.support_scorer.score(
            stock_id=stock_id,
            trade_date=trade_date,
            current_bar=current_bar,
            prev_bar=prev_bar,
        )
        pos = await conn.fetchrow(
            """
            SELECT
                COALESCE(position_label, '') AS position_label,
                COALESCE(ma_alignment_status, '') AS ma_alignment_status,
                COALESCE(trend_strength_score, 0) AS trend_strength_score
            FROM stock_position_judgement
            WHERE trade_date = $1::date
              AND split_part(stock_id, '.', 1) = split_part($2, '.', 1)
            LIMIT 1
            """,
            trade_date,
            stock_id,
        )
        pattern = await conn.fetchrow(
            """
            SELECT
                COALESCE(pattern_labels, '[]'::jsonb) AS pattern_labels,
                COALESCE(volume_pattern_status, '') AS volume_pattern_status,
                COALESCE(breakout_status, '') AS breakout_status,
                COALESCE(pullback_status, '') AS pullback_status,
                COALESCE(risk_pattern_status, '') AS risk_pattern_status
            FROM stock_pattern_judgement
            WHERE trade_date = $1::date
              AND split_part(stock_id, '.', 1) = split_part($2, '.', 1)
            LIMIT 1
            """,
            trade_date,
            stock_id,
        )

        labels = self._coerce_json_object(row.get("labels_json"))
        recent_limit_up_count = int(labels.get("recent_limit_up_count", 0) or 0)
        is_dragon_head = bool(labels.get("is_dragon_head") or False)
        is_front_row_core = bool(labels.get("is_front_row_core") or False)
        board_effect_confirmed = bool(labels.get("board_effect_confirmed") or False)

        # 1) 涨停/强势基因（20）
        gene_score = 0.0
        if recent_limit_up_count >= 4:
            gene_score = 20.0
        elif recent_limit_up_count >= 3:
            gene_score = 16.0
        elif recent_limit_up_count >= 2:
            gene_score = 12.0
        elif recent_limit_up_count >= 1:
            gene_score = 8.0
        if current_flag_today >= 2:
            gene_score = min(20.0, gene_score + 2.0)

        mainline_strength_score = float(cycle.get("mainline_strength_score") or 0.0) if cycle else 0.0
        event_continuity_score = float(cycle.get("event_continuity_score") or 0.0) if cycle else 0.0
        final_mainline_alive = bool(cycle.get("effective_mainline_alive") or False) if cycle else False
        subject_limit_up_count = int(board.get("subject_limit_up_count") or 0) if board else 0
        subject_strong_count = int(board.get("subject_strong_count") or 0) if board else 0
        board_effect_confirmed = board_effect_confirmed or subject_limit_up_count >= 2 or subject_strong_count >= 3

        # 2) 题材主线分（20）
        theme_score = 0.0
        if final_mainline_alive:
            theme_score += 8.0
        if event_continuity_score >= 40.0:
            theme_score += 6.0
        elif event_continuity_score >= 25.0:
            theme_score += 3.0
        if board_effect_confirmed:
            theme_score += 6.0
        theme_score = min(20.0, theme_score)

        # 3) 龙头地位分（20）
        relay_role = str(row.get("relay_role") or "unknown")
        if relay_role == "dragon":
            dragon_score = 20.0
        elif relay_role == "sub_dragon":
            dragon_score = 15.0
        elif relay_role == "card_position_candidate":
            dragon_score = 12.0
        elif is_front_row_core:
            dragon_score = 10.0
        else:
            dragon_score = 4.0

        pattern_labels = []
        if pattern:
            raw_labels = pattern.get("pattern_labels")
            if isinstance(raw_labels, list):
                pattern_labels = [str(x) for x in raw_labels]
        volume_pattern_status = str(pattern.get("volume_pattern_status") or "") if pattern else ""
        breakout_status = str(pattern.get("breakout_status") or "") if pattern else ""
        pullback_status = str(pattern.get("pullback_status") or "") if pattern else ""

        # 4) 量价结构分（20）
        volume_price_score = 0.0
        if current_flag_today >= 2:
            volume_price_score += 6.0
        if volume_pattern_status in {"放量上涨", "缩量整理"}:
            volume_price_score += 6.0
        if pullback_status == "缩量回踩":
            volume_price_score += 4.0
        if not broken_board:
            volume_price_score += 4.0
        volume_price_score = min(20.0, volume_price_score)

        # 5) K线结构分（20）
        structure_score = 0.0
        position_label = str(pos.get("position_label") or "") if pos else ""
        ma_status = str(pos.get("ma_alignment_status") or "") if pos else ""
        trend_strength_score = float(pos.get("trend_strength_score") or 0.0) if pos else 0.0
        if ma_status == "均线多头":
            structure_score += 4.0
        if "高量不破" in pattern_labels:
            structure_score += 4.0
        if breakout_status == "放量突破":
            structure_score += 4.0
        if position_label in {"突破前高", "接近前高"}:
            structure_score += 4.0
        if trend_strength_score >= 70.0:
            structure_score += 4.0
        structure_score = min(20.0, structure_score)

        hard_gate = self._evaluate_strong_pool_hard_gate(
            recent_limit_up_count=recent_limit_up_count,
            final_mainline_alive=final_mainline_alive,
            board_effect_confirmed=board_effect_confirmed,
            current_flag_today=current_flag_today,
            broken_board=broken_board,
            volume_pattern_status=volume_pattern_status,
            pullback_status=pullback_status,
            ma_status=ma_status,
            pattern_labels=pattern_labels,
            breakout_status=breakout_status,
            position_label=position_label,
            trend_strength_score=trend_strength_score,
        )
        if not bool(hard_gate.get("passed")):
            labels.update(
                {
                    "hard_gate_rule_a_gene": bool(hard_gate.get("rule_a_gene")),
                    "hard_gate_rule_b_theme": bool(hard_gate.get("rule_b_theme")),
                    "hard_gate_rule_c_volume": bool(hard_gate.get("rule_c_volume")),
                    "hard_gate_rule_d_structure": bool(hard_gate.get("rule_d_structure")),
                    "hard_gate_pass_count": int(hard_gate.get("pass_count") or 0),
                    "removed_by_hard_gate": True,
                    "removed_reason": "strong_pool_hard_gate_failed",
                }
            )
            evidence = {
                "schema_version": "watch_evidence.v1",
                "rule_version": self.RULE_VERSION,
                "phase": "phase1_seed_refresh_history",
                "hard_gate": hard_gate,
                "removed_reason": "strong_pool_hard_gate_failed",
            }
            return WatchScoreResult(
                watch_score=0.0,
                watch_priority=0.0,
                watch_status="removed",
                pool_entry_type="reject",
                cycle_state=str(cycle.get("final_cycle_state") or "") if cycle else "",
                mainline_strength_score=mainline_strength_score,
                fade_watch=bool(cycle.get("fade_watch") or False) if cycle else False,
                fade_confirmed=True,
                support_type=None,
                support_level=None,
                support_score=0.0,
                labels=labels,
                evidence=evidence,
            )

        watch_score = round(
            gene_score + theme_score + dragon_score + volume_price_score + structure_score,
            2,
        )
        if broken_board and not final_mainline_alive:
            watch_score = max(0.0, round(watch_score - 8.0, 2))
        watch_priority = round(
            watch_score
            + (5.0 if relay_role == "dragon" else 0.0)
            + (2.0 if board_effect_confirmed else 0.0),
            2,
        )

        fade_watch = bool(cycle.get("fade_watch") or False) if cycle else False
        fade_confirmed = bool(cycle.get("fade_confirmed") or False) if cycle else False
        cycle_state = str(cycle.get("final_cycle_state") or "") if cycle else ""
        if cycle_state not in CYCLE_STATES:
            cycle_state = ""

        if fade_confirmed or cycle_state == CYCLE_STATE_FADE_CONFIRMED:
            watch_status = "removed"
        elif broken_board:
            # 断板后只要主线未死，继续保留为弱转强观察标的
            watch_status = "weakening" if final_mainline_alive else "removed"
        elif watch_score >= self.ACTIVE_MIN_SCORE:
            watch_status = "active"
        elif watch_score >= self.WEAKENING_MIN_SCORE:
            watch_status = "weakening"
        else:
            watch_status = "removed"

        strong_grade = "REJECT"
        if watch_score >= self.STRONG_GRADE_S_MIN:
            strong_grade = "S"
        elif watch_score >= self.STRONG_GRADE_A_MIN:
            strong_grade = "A"
        elif watch_score >= self.STRONG_GRADE_B_MIN:
            strong_grade = "B"

        if fade_confirmed or cycle_state == CYCLE_STATE_FADE_CONFIRMED:
            pool_entry_type = "reject"
        elif broken_board and final_mainline_alive:
            pool_entry_type = "observe_only"
        elif (
            strong_grade in {"S", "A"}
            and watch_score >= self.FORMAL_MIN_SCORE
            and mainline_strength_score >= self.FORMAL_MIN_MAINLINE
        ):
            pool_entry_type = "formal"
        elif watch_status in {"active", "weakening"} and strong_grade in {"S", "A", "B"} and watch_score >= self.OBSERVE_MIN_SCORE:
            pool_entry_type = "observe_only"
        else:
            pool_entry_type = "reject"

        removed_reason: Optional[str] = None
        if watch_status == "removed":
            if fade_confirmed or cycle_state == CYCLE_STATE_FADE_CONFIRMED:
                removed_reason = "fade_confirmed"
            elif broken_board and not final_mainline_alive:
                removed_reason = "broken_board_non_mainline"
            elif watch_score < self.WEAKENING_MIN_SCORE:
                removed_reason = "watch_score_below_threshold"
            else:
                removed_reason = "removed_unclassified"

        if cycle_state in {CYCLE_STATE_DIVERGENCE, CYCLE_STATE_REPAIR, CYCLE_STATE_FADE_WATCH}:
            watch_priority = round(watch_priority + 2.0, 2)

        labels.update(
            {
                "cycle_state": cycle_state,
                "fade_watch": fade_watch,
                "fade_confirmed": fade_confirmed,
                "mainline_strength_score": mainline_strength_score,
                "current_flag_today": current_flag_today,
                "broken_board": broken_board,
                "final_mainline_alive": final_mainline_alive,
                "board_effect_confirmed": board_effect_confirmed,
                "subject_limit_up_count": subject_limit_up_count,
                "subject_strong_count": subject_strong_count,
                "hard_gate_rule_a_gene": bool(hard_gate.get("rule_a_gene")),
                "hard_gate_rule_b_theme": bool(hard_gate.get("rule_b_theme")),
                "hard_gate_rule_c_volume": bool(hard_gate.get("rule_c_volume")),
                "hard_gate_rule_d_structure": bool(hard_gate.get("rule_d_structure")),
                "hard_gate_pass_count": int(hard_gate.get("pass_count") or 0),
                "strong_grade": strong_grade,
                "mainline_identity_confirmed": True,
                "hot_theme": board_effect_confirmed,
                "theme_has_event_catalyst": event_continuity_score >= 25.0,
                "ma_bullish": ma_status == "均线多头",
                "high_volume_unbroken": "高量不破" in pattern_labels,
                "new_high_structure": position_label in {"突破前高", "接近前高"},
                "stable_seal_order": not broken_board,
                "volume_up_price_up": str(pattern.get("volume_pattern_status") or "") == "放量上涨" if pattern else False,
                "shrink_on_pullback": str(pattern.get("pullback_status") or "") == "缩量回踩" if pattern else False,
                "support_type": support_result.support_type,
                "support_level": support_result.support_level,
                "support_score": support_result.support_score,
                "support_strength": support_result.support_strength,
            }
        )
        if removed_reason:
            labels["removed_reason"] = removed_reason

        evidence = {
            "schema_version": "watch_evidence.v1",
            "rule_version": self.RULE_VERSION,
            "watch_score_breakdown": {
                "gene_score": gene_score,
                "theme_score": theme_score,
                "dragon_score": dragon_score,
                "volume_price_score": volume_price_score,
                "structure_score": structure_score,
            },
            "hard_gate": hard_gate,
            "cycle_state": cycle_state,
            "mainline_strength_score": mainline_strength_score,
            "broken_board": broken_board,
            "current_flag_today": current_flag_today,
            "final_mainline_alive": final_mainline_alive,
            "event_continuity_score": event_continuity_score,
            "subject_limit_up_count": subject_limit_up_count,
            "subject_strong_count": subject_strong_count,
            "position_label": position_label,
            "ma_alignment_status": ma_status,
            "pattern_labels": pattern_labels,
            "strong_grade": strong_grade,
            "support": {
                "support_type": support_result.support_type,
                "support_level": support_result.support_level,
                "support_score": support_result.support_score,
                "support_strength": support_result.support_strength,
                "support_breakdown": support_result.support_breakdown,
                "evidence_refs": support_result.evidence_refs,
            },
            "phase": "phase1_seed_refresh_history",
        }
        if removed_reason:
            evidence["removed_reason"] = removed_reason

        return WatchScoreResult(
            watch_score=watch_score,
            watch_priority=watch_priority,
            watch_status=watch_status,
            pool_entry_type=pool_entry_type,
            cycle_state=cycle_state,
            mainline_strength_score=mainline_strength_score,
            fade_watch=fade_watch,
            fade_confirmed=fade_confirmed,
            support_type=support_result.support_type,
            support_level=support_result.support_level,
            support_score=support_result.support_score,
            labels=labels,
            evidence=evidence,
        )

    async def _fetch_support_bars(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        stock_id: str,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        """
        为支撑评分器准备当前/前一交易日K线，避免强势池支撑字段长期为默认值。
        """
        rows = await conn.fetch(
            """
            SELECT
              trade_date,
              COALESCE(low_price, 0) AS low_price,
              COALESCE(close_price, 0) AS close_price,
              COALESCE(pct_chg, 0) AS pct_chg
            FROM subject_stock_daily_snapshot
            WHERE split_part(stock_id, '.', 1) = split_part($1, '.', 1)
              AND trade_date <= $2::date
            ORDER BY trade_date DESC
            LIMIT 2
            """,
            stock_id,
            trade_date,
        )
        current = {"low_price": 0.0, "close_price": 0.0, "pct_chg": 0.0}
        prev = {"low_price": 0.0, "close_price": 0.0, "pct_chg": 0.0}
        if rows:
            current = {
                "low_price": float(rows[0].get("low_price") or 0.0),
                "close_price": float(rows[0].get("close_price") or 0.0),
                "pct_chg": float(rows[0].get("pct_chg") or 0.0),
            }
        if len(rows) > 1:
            prev = {
                "low_price": float(rows[1].get("low_price") or 0.0),
                "close_price": float(rows[1].get("close_price") or 0.0),
                "pct_chg": float(rows[1].get("pct_chg") or 0.0),
            }
        return current, prev

    def _is_disallowed_watch_stock(self, stock_id: str, stock_name: str) -> bool:
        canonical = normalize_stock_id(stock_id)
        code = canonical.split(".", 1)[0] if "." in canonical else canonical
        if code.startswith("688"):
            return True
        name = str(stock_name or "").strip().upper()
        if not name:
            return False
        if name.startswith("ST") or name.startswith("*ST"):
            return True
        return False

    def _coerce_json_object(self, raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return dict(raw)
        if raw is None:
            return {}
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}

    def _evaluate_strong_pool_hard_gate(
        self,
        *,
        recent_limit_up_count: int,
        final_mainline_alive: bool,
        board_effect_confirmed: bool,
        current_flag_today: int,
        broken_board: bool,
        volume_pattern_status: str,
        pullback_status: str,
        ma_status: str,
        pattern_labels: List[str],
        breakout_status: str,
        position_label: str,
        trend_strength_score: float,
    ) -> Dict[str, Any]:
        # Rule A：涨停基因（必须成立）
        rule_a_gene = recent_limit_up_count >= 1
        # Rule B：题材承接（主线+板块合力）
        rule_b_theme = final_mainline_alive and board_effect_confirmed
        # Rule C：量价结构健康
        rule_c_volume = (
            current_flag_today >= 2
            or volume_pattern_status in {"放量上涨", "缩量整理"}
            or pullback_status == "缩量回踩"
            or (not broken_board)
        )
        # Rule D：K线结构健康
        rule_d_structure = (
            ma_status == "均线多头"
            or "高量不破" in pattern_labels
            or breakout_status == "放量突破"
            or position_label in {"突破前高", "接近前高"}
            or trend_strength_score >= 70.0
        )
        pass_count = int(rule_a_gene) + int(rule_b_theme) + int(rule_c_volume) + int(rule_d_structure)
        # 文档口径：强势池应优先保留“有涨停基因 + 主线承接”的历史强势样本，
        # 即使当日结构信号偏弱，也不应直接剔除。
        passed = bool(
            rule_a_gene
            and (
                pass_count >= 3
                or (rule_b_theme and recent_limit_up_count >= 2)
            )
        )
        return {
            "rule_a_gene": rule_a_gene,
            "rule_b_theme": rule_b_theme,
            "rule_c_volume": rule_c_volume,
            "rule_d_structure": rule_d_structure,
            "pass_count": pass_count,
            "passed": passed,
        }

    async def _upsert_watch_pool_seed(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        row: WatchSeedRow,
    ) -> int:
        sql = """
        INSERT INTO strong_stock_watch_pool (
            stock_id, stock_name, subject_key, theme_name,
            watch_start_date, last_trade_date, watch_window_days,
            source_tag, relay_role, watch_status,
            watch_priority, watch_score,
            pool_entry_type, candidate_promoted,
            labels_json, evidence_json,
            created_at, updated_at
        ) VALUES (
            $1, $2, $3, $4,
            $5, $6, 1,
            $7, $8, 'pending_seed',
            0, 0,
            'observe_only', FALSE,
            $9::jsonb, $10::jsonb,
            now(), now()
        )
        ON CONFLICT (stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            watch_start_date = CASE
                -- 若当前处于已移除状态，重新入池时重置起始日为本次触发日。
                WHEN strong_stock_watch_pool.watch_status = 'removed' THEN EXCLUDED.watch_start_date
                -- 若出现“二连板及以上”的新一轮强势信号，重置最近强势起始日。
                WHEN COALESCE(NULLIF(EXCLUDED.labels_json->>'recent_limit_up_count', ''), '0')::int >= 2
                     AND COALESCE(NULLIF(strong_stock_watch_pool.labels_json->>'recent_limit_up_count', ''), '0')::int < 2
                     THEN EXCLUDED.watch_start_date
                -- 其余场景保留最早起始日，维持连续观察窗口。
                ELSE LEAST(strong_stock_watch_pool.watch_start_date, EXCLUDED.watch_start_date)
            END,
            last_trade_date = GREATEST(strong_stock_watch_pool.last_trade_date, EXCLUDED.last_trade_date),
            -- 交易日口径统一由 _recompute_watch_window_days 回填，避免自然日偏差。
            watch_window_days = GREATEST(strong_stock_watch_pool.watch_window_days, 1),
            source_tag = EXCLUDED.source_tag,
            relay_role = EXCLUDED.relay_role,
            watch_status = CASE
                WHEN strong_stock_watch_pool.watch_status IN ('active', 'weakening') THEN 'pending_refresh'
                ELSE 'pending_seed'
            END,
            pool_entry_type = 'observe_only',
            candidate_promoted = FALSE,
            labels_json = EXCLUDED.labels_json,
            evidence_json = EXCLUDED.evidence_json,
            updated_at = now()
        """
        await conn.execute(
            sql,
            row.stock_id,
            row.stock_name,
            row.subject_key,
            row.theme_name,
            trade_date,
            trade_date,
            row.source_tag,
            row.relay_role,
            json.dumps(row.labels, ensure_ascii=False),
            json.dumps(row.evidence, ensure_ascii=False),
        )
        return 1

    async def _update_watch_pool_row(
        self,
        conn: asyncpg.Connection,
        trade_date: date,
        row: asyncpg.Record,
        result: WatchScoreResult,
    ) -> None:
        sql = """
        UPDATE strong_stock_watch_pool
        SET last_trade_date = $2::date,
            -- 交易日口径统一由 _recompute_watch_window_days 回填，避免自然日偏差。
            watch_window_days = GREATEST(watch_window_days, 1),
            watch_status = $3,
            watch_priority = $4,
            watch_score = $5,
            pool_entry_type = $6,
            cycle_state = $7,
            mainline_strength_score = $8,
            fade_watch = $9,
            fade_confirmed = $10,
            support_type = $11,
            support_level = $12,
            support_score = $13,
            labels_json = $14::jsonb,
            evidence_json = $15::jsonb,
            updated_at = now()
        WHERE stock_id = $1
        """
        await conn.execute(
            sql,
            row["stock_id"],
            trade_date,
            result.watch_status,
            result.watch_priority,
            result.watch_score,
            result.pool_entry_type,
            result.cycle_state,
            result.mainline_strength_score,
            result.fade_watch,
            result.fade_confirmed,
            result.support_type,
            result.support_level,
            result.support_score,
            json.dumps(result.labels, ensure_ascii=False),
            json.dumps(result.evidence, ensure_ascii=False),
        )

    async def _append_watch_history(self, conn: asyncpg.Connection, trade_date: date, stock_id: str) -> None:
        sql = """
        INSERT INTO strong_stock_watch_history (
            trade_date, stock_id, stock_name, subject_key, theme_name,
            watch_status, watch_score, watch_priority,
            relay_role, pool_entry_type, cycle_state, mainline_strength_score,
            fade_watch, fade_confirmed,
            promoted_to_candidate, removed_reason,
            support_type, support_level, support_score,
            labels_json, evidence_json,
            created_at
        )
        SELECT
            $1::date,
            p.stock_id, p.stock_name, p.subject_key, p.theme_name,
            p.watch_status, p.watch_score, p.watch_priority,
            p.relay_role, p.pool_entry_type, p.cycle_state, p.mainline_strength_score,
            p.fade_watch, p.fade_confirmed,
            p.candidate_promoted,
            CASE
              WHEN COALESCE(NULLIF(BTRIM(p.labels_json->>'removed_reason'), ''), '') <> ''
                THEN p.labels_json->>'removed_reason'
              WHEN COALESCE(p.fade_confirmed, FALSE) THEN 'fade_confirmed'
              WHEN p.watch_status = 'removed' AND p.pool_entry_type = 'reject'
                THEN 'removed_unclassified'
              ELSE NULL
            END,
            p.support_type, p.support_level, p.support_score,
            p.labels_json, p.evidence_json,
            now()
        FROM strong_stock_watch_pool p
        WHERE p.stock_id = $2
        ON CONFLICT (trade_date, stock_id) DO UPDATE SET
            stock_name = EXCLUDED.stock_name,
            subject_key = EXCLUDED.subject_key,
            theme_name = EXCLUDED.theme_name,
            watch_status = EXCLUDED.watch_status,
            watch_score = EXCLUDED.watch_score,
            watch_priority = EXCLUDED.watch_priority,
            relay_role = EXCLUDED.relay_role,
            pool_entry_type = EXCLUDED.pool_entry_type,
            cycle_state = EXCLUDED.cycle_state,
            mainline_strength_score = EXCLUDED.mainline_strength_score,
            fade_watch = EXCLUDED.fade_watch,
            fade_confirmed = EXCLUDED.fade_confirmed,
            promoted_to_candidate = EXCLUDED.promoted_to_candidate,
            removed_reason = EXCLUDED.removed_reason,
            support_type = EXCLUDED.support_type,
            support_level = EXCLUDED.support_level,
            support_score = EXCLUDED.support_score,
            labels_json = EXCLUDED.labels_json,
            evidence_json = EXCLUDED.evidence_json
        """
        await conn.execute(sql, trade_date, normalize_stock_id(stock_id))


__all__ = ["StrongStockTrackingService", "WatchSeedRow", "WatchScoreResult"]

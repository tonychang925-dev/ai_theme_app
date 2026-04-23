#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from pathlib import Path
import sys
from typing import List

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="主线口径一致性审计（identity_registry vs v2）")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--stock-code", help="可选：指定股票代码（如 605060）")
    parser.add_argument("--topn", type=int, default=20, help="冲突题材输出上限")
    parser.add_argument("--streak-lookback-days", type=int, default=15, help="连续冲突统计回看交易日数量")
    parser.add_argument("--max-hidden-conflicts", type=int, help="hidden_mainline_conflicts 最大允许值")
    parser.add_argument(
        "--max-hidden-ratio",
        type=float,
        help="hidden_mainline_conflicts / total_themes 最大允许比例（0~1）",
    )
    parser.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="触发阈值门禁时返回非0退出码",
    )
    return parser.parse_args()


async def _connect() -> asyncpg.Connection:
    c = StockServiceConfig()
    return await asyncpg.connect(
        host=c.postgres_host,
        port=c.postgres_port,
        database=c.postgres_database,
        user=c.postgres_user,
        password=c.postgres_password,
    )


async def _fetch_conflict_summary(conn: asyncpg.Connection, trade_date: date) -> asyncpg.Record:
    sql = """
    WITH joined AS (
      SELECT
        v2.subject_key AS subject_key,
        COALESCE(NULLIF(v2.theme_name, ''), NULLIF(mr.theme_name, ''), v2.subject_key) AS theme_name,
        COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
        COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') AS identity_status,
        COALESCE(v2.final_mainline_alive, FALSE) AS final_mainline_alive,
        COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
        COALESCE(v2.fade_watch, FALSE) AS fade_watch,
        COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed
      FROM theme_cycle_judgement_v2 v2
      LEFT JOIN theme_mainline_identity_registry mr
        ON mr.subject_key = v2.subject_key
      WHERE v2.trade_date = $1::date
    )
    SELECT
      COUNT(*) AS total_themes,
      COUNT(*) FILTER (
        WHERE (is_main_theme = FALSE OR identity_status <> 'confirmed')
          AND final_mainline_alive = TRUE
      ) AS hidden_mainline_conflicts,
      COUNT(*) FILTER (
        WHERE is_main_theme = TRUE
          AND identity_status = 'confirmed'
          AND final_mainline_alive = FALSE
      ) AS dropped_mainline_conflicts,
      COUNT(*) FILTER (
        WHERE is_main_theme = TRUE
          AND identity_status = 'confirmed'
          AND final_cycle_state = 'fade_confirmed'
      ) AS mainline_but_fade_confirmed,
      COUNT(*) FILTER (
        WHERE is_main_theme = TRUE
          AND identity_status = 'confirmed'
          AND final_cycle_state = 'fade_watch'
      ) AS mainline_but_fade_watch
    FROM joined
    """
    return await conn.fetchrow(sql, trade_date)


async def _fetch_conflict_topics(
    conn: asyncpg.Connection,
    trade_date: date,
    topn: int,
    streak_lookback_days: int,
) -> List[asyncpg.Record]:
    sql = """
    WITH trading_days AS (
      SELECT trade_date
      FROM (
        SELECT DISTINCT trade_date
        FROM theme_cycle_judgement_v2
        WHERE trade_date <= $1::date
        ORDER BY trade_date DESC
        LIMIT $3::int
      ) t
    ),
    day_seq AS (
      SELECT
        trade_date,
        ROW_NUMBER() OVER (ORDER BY trade_date DESC) AS rn
      FROM trading_days
    ),
    joined AS (
      SELECT
        v2.subject_key AS subject_key,
        COALESCE(NULLIF(v2.theme_name, ''), NULLIF(mr.theme_name, ''), v2.subject_key) AS theme_name,
        COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
        COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') AS identity_status,
        COALESCE(v2.final_mainline_alive, FALSE) AS final_mainline_alive,
        COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
        COALESCE(v2.mainline_strength_score, 0) AS mainline_strength_score,
        COALESCE(v2.fade_watch, FALSE) AS fade_watch,
        COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed
      FROM theme_cycle_judgement_v2 v2
      LEFT JOIN theme_mainline_identity_registry mr
        ON mr.subject_key = v2.subject_key
      WHERE v2.trade_date = $1::date
    ),
    current_hidden AS (
      SELECT j.subject_key
      FROM joined j
      WHERE (j.is_main_theme = FALSE OR j.identity_status <> 'confirmed')
        AND j.final_mainline_alive = TRUE
    ),
    hidden_matrix AS (
      SELECT
        ch.subject_key,
        ds.rn,
        ds.trade_date,
        CASE
          WHEN (
            COALESCE(mr.is_main_theme, FALSE) = FALSE
            OR COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') <> 'confirmed'
          )
          AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
          THEN TRUE
          ELSE FALSE
        END AS hidden_flag
      FROM current_hidden ch
      CROSS JOIN day_seq ds
      LEFT JOIN theme_cycle_judgement_v2 v2
        ON v2.trade_date = ds.trade_date
       AND v2.subject_key = ch.subject_key
      LEFT JOIN theme_mainline_identity_registry mr
        ON mr.subject_key = ch.subject_key
    ),
    hidden_break AS (
      SELECT
        subject_key,
        MIN(rn) FILTER (WHERE hidden_flag = FALSE) AS first_break_rn
      FROM hidden_matrix
      GROUP BY subject_key
    ),
    hidden_streak AS (
      SELECT
        m.subject_key,
        COUNT(*) FILTER (
          WHERE m.hidden_flag = TRUE
            AND m.rn < COALESCE(b.first_break_rn, 999999)
        ) AS hidden_streak_days
      FROM hidden_matrix m
      LEFT JOIN hidden_break b
        ON b.subject_key = m.subject_key
      GROUP BY m.subject_key
    ),
    impacted AS (
      SELECT
        subject_key,
        COUNT(DISTINCT split_part(stock_id, '.', 1)) AS stock_count,
        COALESCE(SUM(amount), 0) AS amount_sum
      FROM subject_stock_daily_snapshot
      WHERE trade_date = $1::date
      GROUP BY subject_key
    )
    SELECT
      j.subject_key,
      j.theme_name,
      j.is_main_theme,
      j.identity_status,
      j.final_mainline_alive,
      j.final_cycle_state,
      ROUND(j.mainline_strength_score::numeric, 3) AS mainline_strength_score,
      j.fade_watch,
      j.fade_confirmed,
      COALESCE(i.stock_count, 0) AS stock_count,
      COALESCE(i.amount_sum, 0) AS amount_sum,
      COALESCE(hs.hidden_streak_days, 1) AS hidden_streak_days
    FROM joined j
    LEFT JOIN impacted i ON i.subject_key = j.subject_key
    LEFT JOIN hidden_streak hs ON hs.subject_key = j.subject_key
    WHERE (
        (j.is_main_theme = FALSE OR j.identity_status <> 'confirmed')
        AND j.final_mainline_alive = TRUE
    )
       OR (
        j.is_main_theme = TRUE
        AND j.identity_status = 'confirmed'
        AND j.final_mainline_alive = FALSE
    )
       OR (
        j.is_main_theme = TRUE
        AND j.identity_status = 'confirmed'
        AND j.final_cycle_state IN ('fade_watch', 'fade_confirmed')
    )
    ORDER BY COALESCE(hs.hidden_streak_days, 1) DESC, i.stock_count DESC, i.amount_sum DESC, j.subject_key
    LIMIT $2
    """
    return await conn.fetch(sql, trade_date, topn, max(int(streak_lookback_days), 2))


async def _fetch_stock_topics(conn: asyncpg.Connection, trade_date: date, stock_code: str) -> List[asyncpg.Record]:
    sql = """
    WITH stock_themes AS (
      SELECT DISTINCT
        s.subject_key,
        split_part(s.stock_id, '.', 1) AS stock_code,
        s.stock_id,
        s.stock_name
      FROM subject_stock_daily_snapshot s
      WHERE s.trade_date = $1::date
        AND split_part(s.stock_id, '.', 1) = $2
    )
    SELECT
      st.stock_id,
      st.stock_name,
      st.subject_key,
      COALESCE(NULLIF(v2.theme_name, ''), NULLIF(mr.theme_name, ''), st.subject_key) AS theme_name,
      COALESCE(mr.is_main_theme, FALSE) AS is_main_theme,
      COALESCE(NULLIF(LOWER(mr.identity_status), ''), 'observed') AS identity_status,
      COALESCE(v2.final_mainline_alive, FALSE) AS final_mainline_alive,
      COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
      COALESCE(v2.fade_watch, FALSE) AS fade_watch,
      COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed,
      ROUND(COALESCE(v2.mainline_strength_score, 0)::numeric, 3) AS mainline_strength_score
    FROM stock_themes st
    LEFT JOIN theme_mainline_identity_registry mr
      ON mr.subject_key = st.subject_key
    LEFT JOIN theme_cycle_judgement_v2 v2
      ON v2.trade_date = $1::date AND v2.subject_key = st.subject_key
    ORDER BY st.subject_key
    """
    return await conn.fetch(sql, trade_date, stock_code)


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)
    conn = await _connect()
    try:
        summary = await _fetch_conflict_summary(conn, trade_date)
        topics = await _fetch_conflict_topics(conn, trade_date, args.topn, args.streak_lookback_days)

        print(f"[DATE] {trade_date.isoformat()}")
        print(
            "[SUMMARY] "
            f"total_themes={summary['total_themes']} "
            f"hidden_mainline_conflicts={summary['hidden_mainline_conflicts']} "
            f"dropped_mainline_conflicts={summary['dropped_mainline_conflicts']} "
            f"mainline_but_fade_watch={summary['mainline_but_fade_watch']} "
            f"mainline_but_fade_confirmed={summary['mainline_but_fade_confirmed']}"
        )
        total_themes = int(summary["total_themes"] or 0)
        hidden_conflicts = int(summary["hidden_mainline_conflicts"] or 0)
        hidden_ratio = (hidden_conflicts / total_themes) if total_themes > 0 else 0.0
        print(f"[RATIO] hidden_mainline_conflict_ratio={hidden_ratio:.4f}")
        if topics:
            max_streak = max(int(row.get("hidden_streak_days") or 0) for row in topics)
            ge2 = sum(1 for row in topics if int(row.get("hidden_streak_days") or 0) >= 2)
            print(
                f"[STREAK] lookback_trade_days={int(args.streak_lookback_days)} "
                f"max_hidden_streak_days={max_streak} hidden_streak_ge2={ge2}"
            )

        gate_failed = False
        if args.max_hidden_conflicts is not None and hidden_conflicts > int(args.max_hidden_conflicts):
            gate_failed = True
            print(
                f"[GATE_FAIL] hidden_mainline_conflicts={hidden_conflicts} > max_hidden_conflicts={int(args.max_hidden_conflicts)}"
            )
        if args.max_hidden_ratio is not None and hidden_ratio > float(args.max_hidden_ratio):
            gate_failed = True
            print(
                f"[GATE_FAIL] hidden_mainline_conflict_ratio={hidden_ratio:.4f} > max_hidden_ratio={float(args.max_hidden_ratio):.4f}"
            )

        print("[CONFLICT_TOPICS]")
        for row in topics:
            print(
                "  - subject_key={subject_key} theme={theme_name} "
                "mainline={is_main_theme} status={identity_status} v2_alive={final_mainline_alive} "
                "cycle={final_cycle_state} fade_watch={fade_watch} fade_confirmed={fade_confirmed} "
                "mainline_strength={mainline_strength_score} stocks={stock_count} "
                "hidden_streak_days={hidden_streak_days}".format(**dict(row))
            )

        if args.stock_code:
            stock_code = str(args.stock_code).strip()
            rows = await _fetch_stock_topics(conn, trade_date, stock_code)
            print(f"[STOCK] stock_code={stock_code} linked_themes={len(rows)}")
            for row in rows:
                print(
                    "  - stock={stock_id} name={stock_name} subject_key={subject_key} theme={theme_name} "
                    "mainline={is_main_theme} status={identity_status} v2_alive={final_mainline_alive} "
                    "cycle={final_cycle_state} fade_watch={fade_watch} fade_confirmed={fade_confirmed} "
                    "mainline_strength={mainline_strength_score}".format(**dict(row))
                )
        if args.fail_on_gate and gate_failed:
            return 2
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

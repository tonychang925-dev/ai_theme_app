#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime, timedelta
from pathlib import Path
import sys

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="自动生成 CYCLE_CRITICAL_SUBJECT_KEYS（confirmed+强事件+曾入池）"
    )
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=7, help="回看窗口（天）")
    parser.add_argument("--top-k", type=int, default=50, help="最多输出题材数")
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


async def build_critical_keys(
    conn: asyncpg.Connection, trade_date: date, lookback_days: int, top_k: int
) -> list[dict]:
    start_date = trade_date - timedelta(days=max(lookback_days - 1, 0))
    sql = """
    WITH idt AS (
      SELECT subject_key
      FROM theme_mainline_identity_registry
      WHERE COALESCE(is_main_theme, FALSE) = TRUE
        AND COALESCE(NULLIF(LOWER(identity_status), ''), 'observed') = 'confirmed'
    ),
    evt AS (
      SELECT
        subject_key,
        COUNT(*) FILTER (WHERE rank_date >= $2::date) AS event_count_lookback,
        COUNT(*) FILTER (
          WHERE rank_date >= $2::date
            AND (
              COALESCE(heat, 0) >= 70
              OR ABS(COALESCE(pct_chg, 0)) >= 3
              OR COALESCE(heat_name, '') IN ('高', '很高', '极高')
            )
        ) AS strong_event_count_lookback
      FROM theme_history_event
      WHERE rank_date <= $1::date
      GROUP BY subject_key
    ),
    watch AS (
      SELECT
        subject_key,
        MAX(CASE WHEN trade_date >= $2::date THEN 1 ELSE 0 END) AS in_watch_recent
      FROM strong_stock_watch_history
      GROUP BY subject_key
    ),
    cand AS (
      SELECT
        subject_key,
        MAX(CASE WHEN trade_date >= $2::date THEN 1 ELSE 0 END) AS in_candidate_recent
      FROM weak_to_strong_candidate_pool
      GROUP BY subject_key
    )
    SELECT
      i.subject_key,
      COALESCE(e.strong_event_count_lookback, 0) AS strong_event_count_lookback,
      COALESCE(e.event_count_lookback, 0) AS event_count_lookback,
      COALESCE(w.in_watch_recent, 0) AS in_watch_recent,
      COALESCE(c.in_candidate_recent, 0) AS in_candidate_recent
    FROM idt i
    LEFT JOIN evt e ON e.subject_key = i.subject_key
    LEFT JOIN watch w ON w.subject_key = i.subject_key
    LEFT JOIN cand c ON c.subject_key = i.subject_key
    WHERE
      COALESCE(e.strong_event_count_lookback, 0) > 0
      OR COALESCE(w.in_watch_recent, 0) = 1
      OR COALESCE(c.in_candidate_recent, 0) = 1
    ORDER BY
      COALESCE(e.strong_event_count_lookback, 0) DESC,
      COALESCE(e.event_count_lookback, 0) DESC,
      COALESCE(w.in_watch_recent, 0) DESC,
      COALESCE(c.in_candidate_recent, 0) DESC,
      i.subject_key
    LIMIT $3
    """
    rows = await conn.fetch(sql, trade_date, start_date, max(1, top_k))
    return [dict(r) for r in rows]


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)
    conn = await _connect()
    try:
        rows = await build_critical_keys(
            conn=conn,
            trade_date=trade_date,
            lookback_days=args.lookback_days,
            top_k=args.top_k,
        )
    finally:
        await conn.close()

    keys = [str(r["subject_key"]) for r in rows if str(r.get("subject_key") or "")]
    print(f"[OK] trade_date={trade_date.isoformat()} lookback_days={args.lookback_days} top_k={args.top_k}")
    print(f"[OK] critical_count={len(keys)}")
    print("CYCLE_CRITICAL_SUBJECT_KEYS=" + ",".join(keys))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))


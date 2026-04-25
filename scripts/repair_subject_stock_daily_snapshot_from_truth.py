#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date, datetime
from typing import Any

import asyncpg


def _dsn_from_env() -> str:
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db = os.getenv("PG_DATABASE", os.getenv("REPLAY_DB_NAME", "stock_data_test"))
    user = os.getenv("PG_USERNAME", "postgres")
    pw = os.getenv("PG_PASSWORD", "")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


def _filters_sql(since_date: date | None, stock_id: str | None, trade_date: date | None) -> tuple[str, list[Any]]:
    where = ["1=1"]
    args: list[Any] = []
    idx = 1
    if since_date is not None:
        where.append(f"s.trade_date >= ${idx}::date")
        args.append(since_date)
        idx += 1
    if stock_id is not None:
        where.append(f"s.stock_id = ${idx}")
        args.append(stock_id)
        idx += 1
    if trade_date is not None:
        where.append(f"s.trade_date = ${idx}::date")
        args.append(trade_date)
    return " AND ".join(where), args


async def _scan(
    conn: asyncpg.Connection,
    *,
    since_date: date | None,
    stock_id: str | None,
    trade_date: date | None,
) -> dict[str, Any]:
    where_sql, args = _filters_sql(since_date, stock_id, trade_date)
    sql = f"""
    WITH market_rows AS (
        SELECT DISTINCT ON (m.trade_date, m.stock_id)
            m.trade_date, m.stock_id, m.stock_name,
            m.open_price, m.high_price, m.low_price, m.close_price, m.pre_close, m.pct_chg, m.volume, m.amount
        FROM stock_daily_snapshot m
        WHERE m.source_name LIKE 'tushare%'
        ORDER BY m.trade_date, m.stock_id,
                 CASE WHEN m.source_name = 'tushare' THEN 0 ELSE 1 END,
                 m.updated_at DESC NULLS LAST
    ),
    base AS (
        SELECT s.*, m.stock_id AS m_hit
        FROM subject_stock_daily_snapshot s
        LEFT JOIN market_rows m
          ON m.trade_date = s.trade_date
         AND m.stock_id = s.stock_id
        WHERE {where_sql}
    )
    SELECT
      COUNT(*)::bigint AS total_rows,
      SUM((stock_name IS NULL)::int)::bigint AS stock_name_null,
      SUM((rank_order IS NULL)::int)::bigint AS rank_null,
      SUM((close_price IS NULL)::int)::bigint AS close_null,
      SUM((low_price IS NULL)::int)::bigint AS low_null,
      SUM((pct_chg IS NULL)::int)::bigint AS pct_null,
      SUM(((close_price IS NULL OR open_price IS NULL OR high_price IS NULL OR low_price IS NULL OR pre_close IS NULL) AND m_hit IS NOT NULL)::int)::bigint AS recoverable_ohlc_rows
    FROM base
    """
    row = await conn.fetchrow(sql, *args)
    return dict(row) if row else {}


async def _backup(conn: asyncpg.Connection, backup_table: str, *, since_date: date | None, stock_id: str | None, trade_date: date | None) -> int:
    where_sql, args = _filters_sql(since_date, stock_id, trade_date)
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {backup_table} (
            LIKE subject_stock_daily_snapshot INCLUDING ALL
        )
        """
    )
    cmd = await conn.execute(
        f"""
        INSERT INTO {backup_table}
        SELECT *
        FROM subject_stock_daily_snapshot s
        WHERE {where_sql}
        """,
        *args,
    )
    # e.g. "INSERT 0 123"
    return int(cmd.split()[-1]) if cmd else 0


async def _repair(conn: asyncpg.Connection, *, since_date: date | None, stock_id: str | None, trade_date: date | None) -> int:
    where_sql, args = _filters_sql(since_date, stock_id, trade_date)
    sql = f"""
    WITH market_rows AS (
        SELECT DISTINCT ON (m.trade_date, m.stock_id)
            m.trade_date, m.stock_id, m.stock_name,
            m.open_price, m.high_price, m.low_price, m.close_price, m.pre_close, m.pct_chg, m.volume, m.amount
        FROM stock_daily_snapshot m
        WHERE m.source_name LIKE 'tushare%'
        ORDER BY m.trade_date, m.stock_id,
                 CASE WHEN m.source_name = 'tushare' THEN 0 ELSE 1 END,
                 m.updated_at DESC NULLS LAST
    )
    UPDATE subject_stock_daily_snapshot s
    SET
      stock_name = COALESCE(s.stock_name, m.stock_name),
      open_price = COALESCE(s.open_price, m.open_price),
      high_price = COALESCE(s.high_price, m.high_price),
      low_price = COALESCE(s.low_price, m.low_price),
      close_price = COALESCE(s.close_price, m.close_price),
      pre_close = COALESCE(s.pre_close, m.pre_close),
      pct_chg = COALESCE(s.pct_chg, m.pct_chg),
      volume = COALESCE(s.volume, m.volume),
      amount = COALESCE(s.amount, m.amount),
      updated_at = NOW()
    FROM market_rows m
    WHERE s.trade_date = m.trade_date
      AND s.stock_id = m.stock_id
      AND ({where_sql})
      AND (
        s.stock_name IS NULL OR
        s.open_price IS NULL OR s.high_price IS NULL OR s.low_price IS NULL OR s.close_price IS NULL OR s.pre_close IS NULL OR
        s.pct_chg IS NULL OR s.volume IS NULL OR s.amount IS NULL
      )
    """
    cmd = await conn.execute(sql, *args)
    return int(cmd.split()[-1]) if cmd else 0


async def main() -> None:
    parser = argparse.ArgumentParser(description="Repair subject_stock_daily_snapshot from stock_daily_snapshot truth rows.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fix-all", action="store_true")
    parser.add_argument("--stock-id", type=str, default=None)
    parser.add_argument("--trade-date", type=str, default=None)
    parser.add_argument("--since-date", type=str, default="2026-01-01")
    args = parser.parse_args()

    if not args.dry_run and not args.fix_all and not (args.stock_id and args.trade_date):
        raise SystemExit("Use --dry-run or --fix-all, or provide both --stock-id and --trade-date.")

    since_date = date.fromisoformat(args.since_date) if args.since_date else None
    trade_date = date.fromisoformat(args.trade_date) if args.trade_date else None

    conn = await asyncpg.connect(dsn=_dsn_from_env())
    try:
        before = await _scan(conn, since_date=since_date, stock_id=args.stock_id, trade_date=trade_date)
        print(f"[before] {before}")
        if args.dry_run and not args.fix_all:
            return

        backup_table = f"subject_stock_daily_snapshot_repair_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        backup_rows = await _backup(
            conn,
            backup_table,
            since_date=since_date,
            stock_id=args.stock_id,
            trade_date=trade_date,
        )
        print(f"[backup] table={backup_table} rows={backup_rows}")

        async with conn.transaction():
            updated = await _repair(conn, since_date=since_date, stock_id=args.stock_id, trade_date=trade_date)
        print(f"[repair] updated_rows={updated}")

        after = await _scan(conn, since_date=since_date, stock_id=args.stock_id, trade_date=trade_date)
        print(f"[after] {after}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())


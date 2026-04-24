#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

from database_service.config import DatabaseConfig
from database_service.gateway import DatabaseGateway


@dataclass
class PollutedRow:
    trade_date: date
    stock_id: str
    source_name: str
    open_price: Any
    high_price: Any
    low_price: Any
    close_price: Any
    pre_close: Any


async def fetch_polluted_rows(gateway: DatabaseGateway, stock_id: str | None, trade_date: date | None) -> list[PollutedRow]:
    where = [
        "source_name = 'stock_processing_service'",
        "(open_price IS NULL OR high_price IS NULL OR low_price IS NULL OR pre_close IS NULL)",
    ]
    params: list[Any] = []
    idx = 1
    if stock_id:
        where.append(f"stock_id = ${idx}")
        params.append(stock_id)
        idx += 1
    if trade_date:
        where.append(f"trade_date = ${idx}::date")
        params.append(trade_date)
        idx += 1
    sql = f"""
    SELECT trade_date, stock_id, source_name, open_price, high_price, low_price, close_price, pre_close
    FROM stock_daily_snapshot
    WHERE {' AND '.join(where)}
    ORDER BY trade_date, stock_id
    """
    rows = await gateway._client.execute_query(sql, tuple(params))
    return [PollutedRow(**row) for row in rows]


async def has_tushare_truth(gateway: DatabaseGateway, trade_date: date, stock_id: str) -> bool:
    sql = """
    SELECT 1
    FROM stock_daily_snapshot
    WHERE trade_date = $1::date
      AND stock_id = $2
      AND source_name = 'tushare'
    LIMIT 1
    """
    rows = await gateway._client.execute_query(sql, (trade_date, stock_id))
    return bool(rows)


async def delete_polluted_row(gateway: DatabaseGateway, trade_date: date, stock_id: str) -> None:
    sql = """
    DELETE FROM stock_daily_snapshot
    WHERE trade_date = $1::date
      AND stock_id = $2
      AND source_name = 'stock_processing_service'
      AND (open_price IS NULL OR high_price IS NULL OR low_price IS NULL OR pre_close IS NULL)
    """
    await gateway._client.execute_query(sql, (trade_date, stock_id))


async def mark_invalid_row(gateway: DatabaseGateway, trade_date: date, stock_id: str) -> None:
    sql = """
    UPDATE stock_daily_snapshot
    SET source_name = 'stock_processing_service_invalid',
        updated_at = NOW()
    WHERE trade_date = $1::date
      AND stock_id = $2
      AND source_name = 'stock_processing_service'
    """
    await gateway._client.execute_query(sql, (trade_date, stock_id))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Fix polluted stock_daily_snapshot rows written by stock_processing_service.")
    parser.add_argument("--postgres-database", default="stock_data_test")
    parser.add_argument("--stock-id", default="")
    parser.add_argument("--trade-date", default="")
    parser.add_argument("--fix-targeted", action="store_true", help="Apply fixes for matched rows.")
    parser.add_argument("--mark-invalid", action="store_true", help="Mark unrecoverable rows invalid instead of leave as-is.")
    args = parser.parse_args()

    cfg = DatabaseConfig()
    cfg.postgres_database = args.postgres_database
    gateway = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    try:
        trade_date_obj = date.fromisoformat(args.trade_date) if args.trade_date else None
        rows = await fetch_polluted_rows(gateway, args.stock_id or None, trade_date_obj)
        print(f"[scan] polluted_rows={len(rows)}")
        deleted = 0
        marked = 0

        for row in rows:
            truth_exists = await has_tushare_truth(gateway, row.trade_date, row.stock_id)
            action = "none"
            if args.fix_targeted and truth_exists:
                await delete_polluted_row(gateway, row.trade_date, row.stock_id)
                deleted += 1
                action = "deleted_polluted_row"
            elif args.fix_targeted and args.mark_invalid:
                await mark_invalid_row(gateway, row.trade_date, row.stock_id)
                marked += 1
                action = "marked_invalid"

            print(
                f"[row] trade_date={row.trade_date} stock_id={row.stock_id} "
                f"truth_exists={truth_exists} action={action}"
            )

        print(f"[summary] scanned={len(rows)} deleted={deleted} marked_invalid={marked}")
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())

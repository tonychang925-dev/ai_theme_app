#!/usr/bin/env python3
"""M2.5 — Collect Eastmoney Board Pool data (a-stock-data 打板层).

Fetches ZT(涨停池), ZB(炸板池), DT(跌停池), YZT(昨涨停池) from
Eastmoney push2ex API and persists to eastmoney_board_pool_daily.

Usage:
  # Today only
  python -m scripts.collect_eastmoney_board_pool

  # Specific date
  python -m scripts.collect_eastmoney_board_pool --date 2026-07-08

  # Backfill range
  python -m scripts.collect_eastmoney_board_pool --from 2026-07-01 --to 2026-07-08
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import asyncpg

DB_DSN = "postgresql://localhost:5432/stock_data_test"


async def ensure_table(conn):
    """Create table if not exists."""
    migration = ROOT / "database" / "migrations" / "create_eastmoney_board_pool.sql"
    if migration.exists():
        await conn.execute(migration.read_text())


async def collect_date(conn, td: date) -> dict:
    """Fetch and persist board pool data for one trading date."""
    from integrations.a_stock_data.clients.eastmoney_board_client import EastmoneyBoardClient

    client = EastmoneyBoardClient()
    result = {"date": td.isoformat(), "zt": 0, "zb": 0, "dt": 0, "yzt": 0, "errors": []}

    pools = [
        ("ZT", client.fetch_zt_pool),
        ("ZB", client.fetch_zb_pool),
        ("DT", client.fetch_dt_pool),
        ("YZT", client.fetch_yzt_pool),
    ]

    for pool_type, fetch_fn in pools:
        try:
            stocks = await fetch_fn(td)
            count = 0
            for s in stocks:
                await conn.execute(
                    """INSERT INTO eastmoney_board_pool_daily
                       (trade_date, pool_type, stock_code, stock_name,
                        limit_days, pct, break_times, seal_fund, turnover,
                        amount, industry, zt_stat, first_seal, last_seal, raw_json)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15::jsonb)
                       ON CONFLICT (trade_date, pool_type, stock_code) DO UPDATE SET
                        limit_days=EXCLUDED.limit_days, pct=EXCLUDED.pct,
                        break_times=EXCLUDED.break_times, seal_fund=EXCLUDED.seal_fund,
                        turnover=EXCLUDED.turnover, amount=EXCLUDED.amount,
                        industry=EXCLUDED.industry, zt_stat=EXCLUDED.zt_stat,
                        first_seal=EXCLUDED.first_seal, last_seal=EXCLUDED.last_seal,
                        raw_json=EXCLUDED.raw_json""",
                    td, pool_type, s.code, s.name,
                    getattr(s, "limit_days", getattr(s, "dt_days", 0)),
                    getattr(s, "pct", 0),
                    getattr(s, "break_times", getattr(s, "open_times", 0)),
                    getattr(s, "seal_fund", 0),
                    getattr(s, "turnover", 0),
                    getattr(s, "amount", 0),
                    getattr(s, "industry", ""),
                    getattr(s, "zt_stat", ""),
                    getattr(s, "first_seal", ""),
                    getattr(s, "last_seal", ""),
                    json.dumps(_stock_to_dict(s), default=str),
                )
                count += 1
            result[pool_type.lower()] = count
        except Exception as e:
            result["errors"].append(f"{pool_type}: {e}")

    await client.close()
    return result


def _stock_to_dict(s) -> dict:
    """Convert stock DTO to dict for raw_json."""
    d = {}
    for field in ["code", "name", "limit_days", "pct", "break_times", "turnover",
                   "amount", "industry", "zt_stat", "first_seal", "last_seal"]:
        val = getattr(s, field, None)
        if val is not None and val != "" and val != 0:
            d[field] = val
    return d


async def main():
    parser = argparse.ArgumentParser(description="Collect Eastmoney Board Pool")
    parser.add_argument("--date", type=str, help="Specific date YYYY-MM-DD")
    parser.add_argument("--from", dest="from_date", type=str, help="Start date for backfill")
    parser.add_argument("--to", type=str, help="End date for backfill")
    args = parser.parse_args()

    conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
    try:
        await ensure_table(conn)

        if args.date:
            dates = [date.fromisoformat(args.date)]
        elif args.from_date:
            start = date.fromisoformat(args.from_date)
            end = date.fromisoformat(args.to) if args.to else date.today()
            dates = []
            cursor = start
            while cursor <= end:
                dates.append(cursor)
                from datetime import timedelta
                cursor += timedelta(days=1)
        else:
            dates = [date.today()]

        for td in dates:
            result = await collect_date(conn, td)
            status = "OK" if not result["errors"] else f"PARTIAL ({len(result['errors'])} errors)"
            print(f"{td}: ZT={result['zt']} ZB={result['zb']} DT={result['dt']} YZT={result['yzt']} [{status}]")
            if result["errors"]:
                for e in result["errors"]:
                    print(f"  ERROR: {e}")

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())

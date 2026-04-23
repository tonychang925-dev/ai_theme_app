#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _to_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _resolve_stock_id(path: Path, row: dict) -> str:
    value = str(row.get("stock_id") or "").strip().upper()
    if value:
        return value
    return path.stem.strip().upper()


def _iter_rows(path: Path, start_date: date, end_date: date) -> Iterable[Tuple]:
    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            trade_date_raw = str(row.get("trade_date") or "").strip()
            if not trade_date_raw:
                continue
            try:
                trade_date = date.fromisoformat(trade_date_raw)
            except Exception:
                continue
            if trade_date < start_date or trade_date > end_date:
                continue

            stock_id = _resolve_stock_id(path, row)
            if not stock_id:
                continue

            yield (
                trade_date,
                stock_id,
                str(row.get("stock_name") or "").strip() or None,
                _to_float(row.get("open_price")),
                _to_float(row.get("high_price")),
                _to_float(row.get("low_price")),
                _to_float(row.get("close_price")),
                _to_float(row.get("pre_close")),
                _to_float(row.get("pct_chg")),
                _to_float(row.get("volume")),
                _to_float(row.get("amount")),
                str(row.get("source_name") or "tushare").strip() or "tushare",
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="将本地 Tushare daily_bar JSONL 导入 stock_daily_snapshot")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录")
    parser.add_argument(
        "--data-root",
        default=str(PROJECT_ROOT / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar"),
        help="本地 daily_bar 目录",
    )
    parser.add_argument("--trade-date", default="", help="仅导入某个交易日 YYYY-MM-DD")
    parser.add_argument("--start-date", default="", help="导入起始日期 YYYY-MM-DD")
    parser.add_argument("--end-date", default="", help="导入结束日期 YYYY-MM-DD")
    parser.add_argument("--batch-size", type=int, default=2000, help="数据库批量写入行数")
    return parser


async def ensure_table(conn: asyncpg.Connection) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS stock_daily_snapshot (
        trade_date DATE NOT NULL,
        stock_id VARCHAR(16) NOT NULL,
        stock_name VARCHAR(64),
        open_price NUMERIC(12,4),
        high_price NUMERIC(12,4),
        low_price NUMERIC(12,4),
        close_price NUMERIC(12,4),
        pre_close NUMERIC(12,4),
        pct_chg NUMERIC(10,4),
        volume NUMERIC(20,4),
        amount NUMERIC(20,4),
        source_name VARCHAR(32) NOT NULL DEFAULT 'tushare',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT pk_stock_daily_snapshot PRIMARY KEY (trade_date, stock_id)
    );
    CREATE INDEX IF NOT EXISTS idx_stock_daily_snapshot_stock_date
      ON stock_daily_snapshot (stock_id, trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_stock_daily_snapshot_trade_date
      ON stock_daily_snapshot (trade_date DESC);
    """
    await conn.execute(ddl)


async def run_import(args) -> int:
    data_root = Path(args.data_root).resolve()
    if not data_root.exists():
        raise SystemExit(f"daily_bar目录不存在: {data_root}")

    if args.trade_date:
        start_date = end_date = _parse_date(args.trade_date)
    else:
        if args.start_date:
            start_date = _parse_date(args.start_date)
        else:
            start_date = date(1900, 1, 1)
        if args.end_date:
            end_date = _parse_date(args.end_date)
        else:
            end_date = date.today()

    if end_date < start_date:
        raise SystemExit(f"日期范围非法: start={start_date} end={end_date}")

    cfg = StockServiceConfig(project_root=Path(args.project_root).resolve())
    pool = await asyncpg.create_pool(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
        min_size=1,
        max_size=4,
    )

    upsert_sql = """
    INSERT INTO stock_daily_snapshot (
        trade_date, stock_id, stock_name,
        open_price, high_price, low_price, close_price, pre_close, pct_chg,
        volume, amount, source_name
    ) VALUES (
        $1, $2, $3,
        $4, $5, $6, $7, $8, $9,
        $10, $11, $12
    )
    ON CONFLICT (trade_date, stock_id) DO UPDATE SET
      stock_name = EXCLUDED.stock_name,
      open_price = EXCLUDED.open_price,
      high_price = EXCLUDED.high_price,
      low_price = EXCLUDED.low_price,
      close_price = EXCLUDED.close_price,
      pre_close = EXCLUDED.pre_close,
      pct_chg = EXCLUDED.pct_chg,
      volume = EXCLUDED.volume,
      amount = EXCLUDED.amount,
      source_name = EXCLUDED.source_name,
      updated_at = NOW()
    """

    files = sorted(data_root.glob("*.jsonl"))
    processed_files = 0
    total_rows = 0
    batch: List[Tuple] = []

    try:
        async with pool.acquire() as conn:
            await ensure_table(conn)

        async with pool.acquire() as conn:
            for path in files:
                processed_files += 1
                for row in _iter_rows(path, start_date, end_date):
                    batch.append(row)
                    if len(batch) >= args.batch_size:
                        await conn.executemany(upsert_sql, batch)
                        total_rows += len(batch)
                        batch.clear()

                if processed_files <= 5 or processed_files % 500 == 0:
                    print(f"[SYNC] files={processed_files}/{len(files)} rows={total_rows}")

            if batch:
                await conn.executemany(upsert_sql, batch)
                total_rows += len(batch)
                batch.clear()

            count_sql = """
            SELECT COUNT(*)::bigint
            FROM stock_daily_snapshot
            WHERE trade_date >= $1::date AND trade_date <= $2::date
            """
            in_range = await conn.fetchval(count_sql, start_date, end_date)
    finally:
        await pool.close()

    print(f"[OK] data_root={data_root}")
    print(f"[OK] start_date={start_date.isoformat()}")
    print(f"[OK] end_date={end_date.isoformat()}")
    print(f"[OK] files_scanned={len(files)}")
    print(f"[OK] upsert_rows={total_rows}")
    print(f"[OK] db_rows_in_range={int(in_range or 0)}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    return asyncio.run(run_import(args))


if __name__ == "__main__":
    raise SystemExit(main())

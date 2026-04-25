#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import asyncpg


@dataclass(frozen=True)
class DamagedKey:
    trade_date: date
    stock_id: str
    source_name: str
    open_price: Optional[Decimal]
    high_price: Optional[Decimal]
    low_price: Optional[Decimal]
    close_price: Optional[Decimal]
    pre_close: Optional[Decimal]
    pct_chg: Optional[Decimal]
    volume: Optional[Decimal]
    amount: Optional[Decimal]


@dataclass(frozen=True)
class LocalBar:
    trade_date: date
    stock_id: str
    stock_name: str
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    pre_close: Decimal
    pct_chg: Decimal
    volume: Decimal
    amount: Decimal


def _normalize_stock_id(stock_id: str) -> tuple[str, str]:
    raw = (stock_id or "").strip().upper()
    if not raw:
        return "", ""
    if "." in raw:
        code, suffix = raw.split(".", 1)
        if len(code) == 6 and code.isdigit() and suffix in {"SZ", "SH", "BJ"}:
            return code, f"{code}.{suffix}"
        raw = code
    if len(raw) == 6 and raw.isdigit():
        if raw.startswith(("60", "68")):
            suffix = "SH"
        elif raw.startswith(("43", "83", "87")):
            suffix = "BJ"
        else:
            suffix = "SZ"
        return raw, f"{raw}.{suffix}"
    return raw, raw


class LocalKlineStore:
    def __init__(self, root: Path) -> None:
        self._root = root
        self._cache: dict[str, dict[date, LocalBar]] = {}

    def _paths(self, stock_id: str) -> list[Path]:
        raw_code, normalized = _normalize_stock_id(stock_id)
        paths: list[Path] = []
        if normalized:
            paths.append(self._root / f"{normalized}.jsonl")
        if raw_code and raw_code != normalized:
            paths.append(self._root / f"{raw_code}.jsonl")
        return paths

    def _to_decimal(self, value: Any) -> Decimal:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _load(self, stock_id: str) -> dict[date, LocalBar]:
        _, normalized = _normalize_stock_id(stock_id)
        if not normalized:
            return {}
        if normalized in self._cache:
            return self._cache[normalized]

        bars: dict[date, LocalBar] = {}
        for path in self._paths(stock_id):
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                        trade_date = date.fromisoformat(str(row.get("trade_date")))
                    except Exception:
                        continue
                    try:
                        bars[trade_date] = LocalBar(
                            trade_date=trade_date,
                            stock_id=normalized,
                            stock_name=str(row.get("stock_name") or ""),
                            open_price=self._to_decimal(row.get("open_price")),
                            high_price=self._to_decimal(row.get("high_price")),
                            low_price=self._to_decimal(row.get("low_price")),
                            close_price=self._to_decimal(row.get("close_price")),
                            pre_close=self._to_decimal(row.get("pre_close")),
                            pct_chg=self._to_decimal(row.get("pct_chg")),
                            volume=self._to_decimal(row.get("volume")),
                            amount=self._to_decimal(row.get("amount")),
                        )
                    except Exception:
                        continue
            if bars:
                break
        self._cache[normalized] = bars
        return bars

    def get(self, stock_id: str, trade_date: date) -> Optional[LocalBar]:
        bars = self._load(stock_id)
        return bars.get(trade_date)


def _dsn_from_env() -> str:
    host = os.getenv("PG_HOST", "localhost")
    port = os.getenv("PG_PORT", "5432")
    db = os.getenv("PG_DATABASE", os.getenv("REPLAY_DB_NAME", "stock_data_test"))
    user = os.getenv("PG_USERNAME", "postgres")
    pw = os.getenv("PG_PASSWORD", "")
    return f"postgresql://{user}:{pw}@{host}:{port}/{db}"


async def _fetch_damaged_keys(
    conn: asyncpg.Connection,
    *,
    since_date: Optional[date],
    stock_id: Optional[str],
    trade_date: Optional[date],
) -> list[DamagedKey]:
    where = [
        "("
        "source_name = 'stock_processing_service' "
        "OR open_price IS NULL "
        "OR high_price IS NULL "
        "OR low_price IS NULL "
        "OR close_price IS NULL "
        "OR pre_close IS NULL"
        ")"
    ]
    args: list[Any] = []
    idx = 1
    if since_date is not None:
        where.append(f"trade_date >= ${idx}::date")
        args.append(since_date)
        idx += 1
    if stock_id is not None:
        where.append(f"stock_id = ${idx}")
        args.append(stock_id)
        idx += 1
    if trade_date is not None:
        where.append(f"trade_date = ${idx}::date")
        args.append(trade_date)
        idx += 1
    sql = f"""
    SELECT
      trade_date, stock_id, source_name,
      open_price, high_price, low_price, close_price, pre_close,
      pct_chg, volume, amount
    FROM stock_daily_snapshot
    WHERE {' AND '.join(where)}
    ORDER BY trade_date, stock_id
    """
    rows = await conn.fetch(sql, *args)
    return [DamagedKey(**dict(r)) for r in rows]


async def _create_backup(conn: asyncpg.Connection, backup_table: str, keys: list[DamagedKey]) -> int:
    if not keys:
        return 0
    await conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {backup_table} (
            LIKE stock_daily_snapshot INCLUDING ALL
        )
        """
    )
    pairs = {(k.trade_date, k.stock_id) for k in keys}
    rows = await conn.executemany(
        f"""
        INSERT INTO {backup_table}
        SELECT *
        FROM stock_daily_snapshot
        WHERE trade_date = $1::date AND stock_id = $2
        """,
        list(pairs),
    )
    return len(pairs)


async def _upsert_truth(conn: asyncpg.Connection, bar: LocalBar) -> None:
    await conn.execute(
        """
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
          stock_name = COALESCE(EXCLUDED.stock_name, stock_daily_snapshot.stock_name),
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
        """,
        bar.trade_date,
        bar.stock_id,
        bar.stock_name,
        bar.open_price,
        bar.high_price,
        bar.low_price,
        bar.close_price,
        bar.pre_close,
        bar.pct_chg,
        bar.volume,
        bar.amount,
        "tushare_local_repair",
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Repair damaged stock_daily_snapshot rows from local daily_bar jsonl.")
    parser.add_argument("--dry-run", action="store_true", help="Only scan and print summary.")
    parser.add_argument("--fix-all", action="store_true", help="Repair all damaged rows found by filters.")
    parser.add_argument("--stock-id", type=str, default=None, help="Repair one stock_id only.")
    parser.add_argument("--trade-date", type=str, default=None, help="Repair one date (YYYY-MM-DD) only.")
    parser.add_argument("--since-date", type=str, default="2026-01-01", help="Scan lower bound date (YYYY-MM-DD).")
    parser.add_argument(
        "--local-kline-root",
        type=str,
        default=str(Path(__file__).resolve().parents[1] / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar"),
        help="Path to local daily_bar jsonl directory.",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.fix_all and not (args.stock_id and args.trade_date):
        raise SystemExit("Use --dry-run or --fix-all, or provide both --stock-id and --trade-date for targeted fix.")

    trade_date = date.fromisoformat(args.trade_date) if args.trade_date else None
    since_date = date.fromisoformat(args.since_date) if args.since_date else None
    local_store = LocalKlineStore(Path(args.local_kline_root))
    dsn = _dsn_from_env()

    conn = await asyncpg.connect(dsn=dsn)
    try:
        keys = await _fetch_damaged_keys(
            conn,
            since_date=since_date,
            stock_id=args.stock_id,
            trade_date=trade_date,
        )
        print(f"[scan] damaged_rows={len(keys)}")
        if not keys:
            return

        found_local = 0
        missing_local = 0
        for k in keys:
            if local_store.get(k.stock_id, k.trade_date):
                found_local += 1
            else:
                missing_local += 1
        print(f"[scan] local_match={found_local} local_missing={missing_local}")

        if args.dry_run and not args.fix_all:
            for k in keys[:100]:
                hit = local_store.get(k.stock_id, k.trade_date) is not None
                print(
                    f"[dry-run] {k.trade_date} {k.stock_id} src={k.source_name} "
                    f"ohlc_null={any(v is None for v in [k.open_price, k.high_price, k.low_price, k.close_price, k.pre_close])} "
                    f"local={'Y' if hit else 'N'}"
                )
            return

        backup_table = f"stock_daily_snapshot_repair_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        await _create_backup(conn, backup_table, keys)
        print(f"[backup] table={backup_table} rows={len(keys)}")

        repaired = 0
        unresolved = 0
        async with conn.transaction():
            for k in keys:
                bar = local_store.get(k.stock_id, k.trade_date)
                if bar is None:
                    unresolved += 1
                    continue
                await _upsert_truth(conn, bar)
                repaired += 1

        print(f"[done] repaired={repaired} unresolved={unresolved} total={len(keys)}")
        if unresolved > 0:
            print("[hint] unresolved rows have no local daily_bar record; keep for manual recovery list.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())


#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
from pathlib import Path
import sys
from typing import Optional

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.config import StockServiceConfig


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="修复 theme_mainline_judgement 身份字段一致性（已废弃，默认阻断）")
    parser.add_argument("--trade-date", help="单日修复 YYYY-MM-DD")
    parser.add_argument("--start-date", help="区间起始 YYYY-MM-DD")
    parser.add_argument("--end-date", help="区间结束 YYYY-MM-DD")
    parser.add_argument(
        "--allow-legacy",
        action="store_true",
        help="显式允许执行已废弃脚本（仅临时诊断使用）",
    )
    return parser.parse_args()


def _where_clause(trade_date: Optional[date], start_date: Optional[date], end_date: Optional[date]) -> tuple[str, list]:
    if trade_date is not None:
        return "trade_date = $1::date", [trade_date]
    if start_date is not None and end_date is not None:
        return "trade_date BETWEEN $1::date AND $2::date", [start_date, end_date]
    return "TRUE", []


async def main_async() -> int:
    args = parse_args()
    if not args.allow_legacy:
        print(
            "[BLOCKED] fix_mainline_identity_consistency is deprecated. "
            "Identity consistency is enforced via mainline_state_daily and v2 identity-prior gate. "
            "Pass --allow-legacy for temporary diagnostics."
        )
        return 2
    trade_date = _parse_date(args.trade_date) if args.trade_date else None
    start_date = _parse_date(args.start_date) if args.start_date else None
    end_date = _parse_date(args.end_date) if args.end_date else None

    if trade_date is None and ((start_date is None) != (end_date is None)):
        raise ValueError("区间修复必须同时传 --start-date 和 --end-date")
    if start_date and end_date and end_date < start_date:
        raise ValueError("--end-date 不能早于 --start-date")

    cfg = StockServiceConfig()
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        where_sql, params = _where_clause(trade_date, start_date, end_date)
        inconsistent_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM theme_mainline_judgement
        WHERE {where_sql}
          AND (
            (is_main_theme = TRUE AND COALESCE(NULLIF(LOWER(theme_tier), ''), 'failed') <> 'main')
            OR (is_main_theme = FALSE AND COALESCE(NULLIF(LOWER(theme_tier), ''), 'failed') = 'main')
          )
        """
        before = int((await conn.fetchrow(inconsistent_sql, *params))["cnt"] or 0)

        update_sql = f"""
        UPDATE theme_mainline_judgement
        SET
            is_main_theme = (COALESCE(NULLIF(LOWER(theme_tier), ''), 'failed') = 'main'),
            updated_at = NOW()
        WHERE {where_sql}
          AND is_main_theme IS DISTINCT FROM (COALESCE(NULLIF(LOWER(theme_tier), ''), 'failed') = 'main')
        """
        updated = await conn.execute(update_sql, *params)
        updated_rows = int(updated.split()[-1])

        after = int((await conn.fetchrow(inconsistent_sql, *params))["cnt"] or 0)
        print(f"[FIX] updated_rows={updated_rows}")
        print(f"[FIX] inconsistent_before={before} inconsistent_after={after}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

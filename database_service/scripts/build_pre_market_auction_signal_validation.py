#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.models import PreMarketAuctionSignal
from stock_service.services.auction_signal_validation_service import (
    AuctionSignalValidationService,
    AuctionValidationMarketInput,
)


def get_postgres_config() -> DatabaseConfig:
    return DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        postgres_schema="public",
        table_names_config={"theme_master": "theme_master"},
        redis=RedisConfig(enabled=False),
        postgres_pool_size=5,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="构建 pre_market_auction_signal_validation")
    parser.add_argument("--trade-date", required=True, help="目标交易日 YYYY-MM-DD")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _stock_aliases(value: str) -> set[str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return set()
    aliases = {raw}
    if "." in raw:
        aliases.add(raw.split(".", 1)[0])
    else:
        if raw.startswith(("6", "9")):
            aliases.add(f"{raw}.SH")
        elif raw.startswith(("4", "8")):
            aliases.add(f"{raw}.BJ")
        else:
            aliases.add(f"{raw}.SZ")
    return aliases


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS pre_market_auction_signal_validation (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        stock_id TEXT NOT NULL,
        stock_name TEXT NOT NULL DEFAULT '',
        subject_key TEXT NOT NULL DEFAULT '',
        theme_name TEXT NOT NULL DEFAULT '',
        role_label TEXT NOT NULL DEFAULT '',
        auction_signal_level TEXT NOT NULL DEFAULT '',
        auction_signal_score NUMERIC(8,4) NOT NULL DEFAULT 0,
        signal_type TEXT NOT NULL DEFAULT '',
        action_today TEXT NOT NULL DEFAULT '',
        close_pct NUMERIC(8,4) NOT NULL DEFAULT 0,
        close_price NUMERIC(12,4) NOT NULL DEFAULT 0,
        hit_limit_up BOOLEAN NOT NULL DEFAULT FALSE,
        close_rank_order INTEGER NOT NULL DEFAULT 0,
        close_is_leader BOOLEAN NOT NULL DEFAULT FALSE,
        validation_result TEXT NOT NULL DEFAULT '',
        signal_validated BOOLEAN NOT NULL DEFAULT FALSE,
        validation_note TEXT NOT NULL DEFAULT '',
        source_type TEXT NOT NULL DEFAULT 'p3.phase3.auction_signal_validation',
        source_trace_id TEXT NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version TEXT NOT NULL DEFAULT 'auction_signal_validation.v1.daily_only',
        rule_version TEXT NOT NULL DEFAULT 'auction_signal_validation.v1.daily_only',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_pre_market_auction_signal_validation UNIQUE (trade_date, stock_id, subject_key)
    );
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute(
            "ALTER TABLE pre_market_auction_signal_validation ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        )


async def fetch_signals(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT trade_date, stock_id, stock_name, subject_key, theme_name, role_label,
           auction_signal_level, auction_signal_score, signal_type, action_today,
           hard_reject_reason, evidence, source_type, source_trace_id,
           source_trace, source_version, rule_version
    FROM pre_market_auction_signal
    WHERE trade_date = $1
    ORDER BY theme_name, stock_id
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_daily_market(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT trade_date, subject_key, stock_id, stock_name,
           rank_order, pct_chg, close_price, limit_up, is_leader
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    result = {}
    for row in rows:
        payload = dict(row)
        payload["close_pct"] = float(payload.get("pct_chg") or 0.0)
        for alias in _stock_aliases(str(row["stock_id"])):
            result[(str(row["subject_key"]), alias)] = payload
    return result


async def upsert_rows(manager: PostgresDatabaseManager, items):
    sql = """
    INSERT INTO pre_market_auction_signal_validation (
        trade_date, stock_id, stock_name, subject_key, theme_name, role_label,
        auction_signal_level, auction_signal_score, signal_type, action_today,
        close_pct, close_price, hit_limit_up, close_rank_order, close_is_leader,
        validation_result, signal_validated, validation_note,
        source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5, $6,
        $7, $8, $9, $10,
        $11, $12, $13, $14, $15,
        $16, $17, $18,
        $19, $20, $21::jsonb, $22, $23
    )
    ON CONFLICT (trade_date, stock_id, subject_key)
    DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        theme_name = EXCLUDED.theme_name,
        role_label = EXCLUDED.role_label,
        auction_signal_level = EXCLUDED.auction_signal_level,
        auction_signal_score = EXCLUDED.auction_signal_score,
        signal_type = EXCLUDED.signal_type,
        action_today = EXCLUDED.action_today,
        close_pct = EXCLUDED.close_pct,
        close_price = EXCLUDED.close_price,
        hit_limit_up = EXCLUDED.hit_limit_up,
        close_rank_order = EXCLUDED.close_rank_order,
        close_is_leader = EXCLUDED.close_is_leader,
        validation_result = EXCLUDED.validation_result,
        signal_validated = EXCLUDED.signal_validated,
        validation_note = EXCLUDED.validation_note,
        source_type = EXCLUDED.source_type,
        source_trace_id = EXCLUDED.source_trace_id,
        source_trace = EXCLUDED.source_trace,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    payload = [
        (
            _parse_trade_date(item.trade_date),
            item.stock_id,
            item.stock_name,
            item.subject_key,
            item.theme_name,
            item.role_label,
            item.auction_signal_level,
            item.auction_signal_score,
            item.signal_type,
            item.action_today,
            item.close_pct,
            item.close_price,
            item.hit_limit_up,
            item.close_rank_order,
            item.close_is_leader,
            item.validation_result,
            item.signal_validated,
            item.validation_note,
            item.source_type,
            item.source_trace_id,
            json.dumps(item.source_trace, ensure_ascii=False),
            item.source_version,
            item.rule_version,
        )
        for item in items
    ]
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, payload)


async def main_async() -> int:
    args = parse_args()
    trade_date_value = _parse_trade_date(args.trade_date)
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        signals = await fetch_signals(manager, trade_date_value)
        market_map = await fetch_daily_market(manager, trade_date_value)
        service = AuctionSignalValidationService()

        items = []
        for row in signals:
            signal = PreMarketAuctionSignal(
                trade_date=args.trade_date,
                stock_id=str(row["stock_id"]).upper(),
                stock_name=row["stock_name"],
                subject_key=str(row["subject_key"]),
                theme_name=row["theme_name"],
                role_label=row["role_label"],
                auction_signal_score=float(row["auction_signal_score"] or 0.0),
                auction_signal_level=row["auction_signal_level"],
                signal_type=row["signal_type"],
                leader_status="",
                action_today=row["action_today"],
                hard_reject_reason=row["hard_reject_reason"] or "",
                evidence=row["evidence"] or [],
                source_type=row["source_type"],
                source_trace_id=row["source_trace_id"] or "",
                source_trace=row["source_trace"] or {},
                source_version=row["source_version"] or "auction_signal.v1",
                rule_version=row["rule_version"] or "auction_signal.v1",
            )
            market_row = None
            for alias in _stock_aliases(signal.stock_id):
                market_row = market_map.get((signal.subject_key, alias))
                if market_row:
                    break
            market = AuctionValidationMarketInput(
                close_pct=float((market_row or {}).get("close_pct") or 0.0),
                close_price=float((market_row or {}).get("close_price") or 0.0),
                hit_limit_up=bool((market_row or {}).get("limit_up") or False),
                close_rank_order=int((market_row or {}).get("rank_order") or 0),
                close_is_leader=bool((market_row or {}).get("is_leader") or False),
                has_daily_result=market_row is not None,
            )
            items.append(service.build_validation(signal, market))

        await upsert_rows(manager, items)
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] validation_rows={len(items)}")
        print(f"[OK] validated={sum(1 for x in items if x.signal_validated)}")
        print(f"[OK] not_validated={sum(1 for x in items if not x.signal_validated)}")
        for item in items[: args.top_k]:
            print(
                f"[ROW] theme={item.theme_name} stock={item.stock_name} "
                f"level={item.auction_signal_level} close_pct={item.close_pct:.2f} "
                f"limit_up={item.hit_limit_up} result={item.validation_result} validated={item.signal_validated}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

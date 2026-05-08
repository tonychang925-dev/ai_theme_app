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
from stock_service.config import StockServiceConfig
from stock_service.services.dragon_tiger_object_service import DragonTigerObjectService
from stock_service.services.tushare_dragon_tiger_snapshot_service import (
    TushareDragonTigerSnapshotService,
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
    parser = argparse.ArgumentParser(description="构建 dragon_tiger_object")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--token", default="", help="Tushare token，优先于环境变量 TUSHARE_TOKEN")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    parser.add_argument("--force-refresh", action="store_true", help="强制刷新 Tushare 原始快照")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS dragon_tiger_object (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100) NOT NULL,
        reason TEXT NOT NULL,
        close_price NUMERIC(12,2) NOT NULL DEFAULT 0,
        pct_change NUMERIC(8,2) NOT NULL DEFAULT 0,
        turnover_rate NUMERIC(8,2) NOT NULL DEFAULT 0,
        total_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        billboard_buy_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        billboard_sell_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        billboard_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        net_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        net_rate NUMERIC(10,2) NOT NULL DEFAULT 0,
        amount_rate NUMERIC(10,2) NOT NULL DEFAULT 0,
        float_market_value NUMERIC(20,2) NOT NULL DEFAULT 0,
        institution_buy_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        institution_sell_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        institution_net_buy NUMERIC(20,2) NOT NULL DEFAULT 0,
        institution_seat_count INTEGER NOT NULL DEFAULT 0,
        seat_summary JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_trace_id VARCHAR(40) NOT NULL,
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_dragon_tiger_object UNIQUE (trade_date, stock_id, reason)
    );
    CREATE INDEX IF NOT EXISTS idx_dto_trade_date ON dragon_tiger_object(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_dto_stock_date ON dragon_tiger_object(stock_id, trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_dto_trace_id ON dragon_tiger_object(source_trace_id);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def upsert_rows(manager: PostgresDatabaseManager, objects):
    sql = """
    INSERT INTO dragon_tiger_object (
        trade_date, stock_id, stock_name, reason,
        close_price, pct_change, turnover_rate, total_amount,
        billboard_buy_amount, billboard_sell_amount, billboard_amount, net_amount,
        net_rate, amount_rate, float_market_value,
        institution_buy_amount, institution_sell_amount, institution_net_buy, institution_seat_count,
        seat_summary, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4,
        $5, $6, $7, $8,
        $9, $10, $11, $12,
        $13, $14, $15,
        $16, $17, $18, $19,
        $20::jsonb, $21, $22::jsonb, $23, $24
    )
    ON CONFLICT (trade_date, stock_id, reason)
    DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        close_price = EXCLUDED.close_price,
        pct_change = EXCLUDED.pct_change,
        turnover_rate = EXCLUDED.turnover_rate,
        total_amount = EXCLUDED.total_amount,
        billboard_buy_amount = EXCLUDED.billboard_buy_amount,
        billboard_sell_amount = EXCLUDED.billboard_sell_amount,
        billboard_amount = EXCLUDED.billboard_amount,
        net_amount = EXCLUDED.net_amount,
        net_rate = EXCLUDED.net_rate,
        amount_rate = EXCLUDED.amount_rate,
        float_market_value = EXCLUDED.float_market_value,
        institution_buy_amount = EXCLUDED.institution_buy_amount,
        institution_sell_amount = EXCLUDED.institution_sell_amount,
        institution_net_buy = EXCLUDED.institution_net_buy,
        institution_seat_count = EXCLUDED.institution_seat_count,
        seat_summary = EXCLUDED.seat_summary,
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
            item.reason,
            item.close_price,
            item.pct_change,
            item.turnover_rate,
            item.total_amount,
            item.billboard_buy_amount,
            item.billboard_sell_amount,
            item.billboard_amount,
            item.net_amount,
            item.net_rate,
            item.amount_rate,
            item.float_market_value,
            item.institution_buy_amount,
            item.institution_sell_amount,
            item.institution_net_buy,
            item.institution_seat_count,
            json.dumps(item.seat_summary, ensure_ascii=False),
            item.source_trace_id,
            json.dumps(item.source_trace, ensure_ascii=False),
            item.source_version,
            item.rule_version,
        )
        for item in objects
    ]
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, payload)


async def main_async(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        stock_config = StockServiceConfig()
        if args.token:
            stock_config.tushare_token = args.token
        snapshot_service = TushareDragonTigerSnapshotService(stock_config)
        top_list_result = snapshot_service.fetch_or_cache_top_list(
            args.trade_date,
            force_refresh=args.force_refresh,
        )
        top_inst_result = snapshot_service.fetch_or_cache_top_inst(
            args.trade_date,
            force_refresh=args.force_refresh,
        )

        service = DragonTigerObjectService()
        top_list_rows = service.normalize_top_list(top_list_result.records)
        top_inst_rows = service.normalize_top_inst(top_inst_result.records)
        objects = service.build_objects(top_list_rows, top_inst_rows)
        await upsert_rows(manager, objects)

        async with manager.pool.acquire() as conn:
            preview = await conn.fetch(
                """
                SELECT trade_date, stock_id, stock_name, reason, net_amount, institution_seat_count
                FROM dragon_tiger_object
                WHERE trade_date = $1
                ORDER BY ABS(net_amount) DESC, stock_id ASC
                LIMIT $2
                """,
                _parse_trade_date(args.trade_date),
                args.top_k,
            )

        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] top_list_rows={top_list_result.row_count} cache_hit={top_list_result.cache_hit}")
        print(f"[OK] top_inst_rows={top_inst_result.row_count} cache_hit={top_inst_result.cache_hit}")
        print(f"[OK] objects={len(objects)}")
        for row in preview:
            print(
                f"  - {row['stock_id']} {row['stock_name']} | {row['reason']} | "
                f"net={float(row['net_amount'] or 0):.2f} | seats={int(row['institution_seat_count'] or 0)}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

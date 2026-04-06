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
from stock_service.services.hot_money_activity_service import HotMoneyActivityService
from stock_service.services.tushare_dragon_tiger_snapshot_service import TushareDragonTigerSnapshotService


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
    parser = argparse.ArgumentParser(description="构建 hot_money_trading_activity")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--token", default="", help="Tushare token，优先于环境变量")
    parser.add_argument("--force-refresh", action="store_true", help="强制刷新 Tushare 原始快照")
    parser.add_argument("--top-k", type=int, default=20, help="预览条数")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS hot_money_seat_master (
        id BIGSERIAL PRIMARY KEY,
        seat_name VARCHAR(255) NOT NULL UNIQUE,
        seat_alias VARCHAR(120) NOT NULL DEFAULT '',
        hot_money_name VARCHAR(120) NOT NULL DEFAULT '',
        style_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
        confidence NUMERIC(6,2) NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS hot_money_trading_activity (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        hot_money_name VARCHAR(120) NOT NULL,
        seat_name VARCHAR(255) NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(120) NOT NULL DEFAULT '',
        subject_key VARCHAR(80) NOT NULL DEFAULT '',
        theme_name VARCHAR(200) NOT NULL DEFAULT '',
        side VARCHAR(20) NOT NULL DEFAULT '',
        buy_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        sell_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        net_amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        reason TEXT NOT NULL DEFAULT '',
        rank_order INTEGER NOT NULL DEFAULT 0,
        is_theme_leader BOOLEAN NOT NULL DEFAULT FALSE,
        style_tags JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_hot_money_activity UNIQUE (trade_date, hot_money_name, seat_name, stock_id, subject_key, side)
    );
    CREATE INDEX IF NOT EXISTS idx_hot_money_activity_trade_date ON hot_money_trading_activity(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_hot_money_activity_theme ON hot_money_trading_activity(theme_name, trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def fetch_subject_links(manager: PostgresDatabaseManager, trade_date: str, stock_ids: list[str]) -> list[dict]:
    if not stock_ids:
        return []
    sql = """
    SELECT DISTINCT
        s.subject_key,
        COALESCE(tm.name, s.subject_key) AS theme_name,
        s.stock_id,
        s.stock_name,
        s.rank_order,
        s.is_leader
    FROM subject_stock_daily_snapshot s
    LEFT JOIN theme_master tm
      ON COALESCE(NULLIF(tm.source_id, ''), 'theme:' || tm.id::text) = s.subject_key
    WHERE s.trade_date = $1::date
      AND split_part(s.stock_id, '.', 1) = ANY($2::text[])
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, _parse_trade_date(trade_date), [x.split(".")[0] for x in stock_ids])
    return [dict(r) for r in rows]


async def upsert_seat_masters(manager: PostgresDatabaseManager, items) -> None:
    sql = """
    INSERT INTO hot_money_seat_master (
        seat_name, seat_alias, hot_money_name, style_tags, confidence, is_active, source_version, rule_version
    ) VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8)
    ON CONFLICT (seat_name)
    DO UPDATE SET
        seat_alias = EXCLUDED.seat_alias,
        hot_money_name = EXCLUDED.hot_money_name,
        style_tags = EXCLUDED.style_tags,
        confidence = EXCLUDED.confidence,
        is_active = EXCLUDED.is_active,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    payload = [
        (
            item.seat_name,
            item.seat_alias,
            item.hot_money_name,
            json.dumps(item.style_tags, ensure_ascii=False),
            item.confidence,
            item.is_active,
            item.source_version,
            item.rule_version,
        )
        for item in items
    ]
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, payload)


async def upsert_activities(manager: PostgresDatabaseManager, items) -> None:
    sql = """
    INSERT INTO hot_money_trading_activity (
        trade_date, hot_money_name, seat_name, stock_id, stock_name, subject_key, theme_name,
        side, buy_amount, sell_amount, net_amount, reason, rank_order, is_theme_leader,
        style_tags, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7,
        $8, $9, $10, $11, $12, $13, $14,
        $15::jsonb, $16, $17
    )
    ON CONFLICT (trade_date, hot_money_name, seat_name, stock_id, subject_key, side)
    DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        theme_name = EXCLUDED.theme_name,
        buy_amount = EXCLUDED.buy_amount,
        sell_amount = EXCLUDED.sell_amount,
        net_amount = EXCLUDED.net_amount,
        reason = EXCLUDED.reason,
        rank_order = EXCLUDED.rank_order,
        is_theme_leader = EXCLUDED.is_theme_leader,
        style_tags = EXCLUDED.style_tags,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    payload = [
        (
            _parse_trade_date(item.trade_date),
            item.hot_money_name,
            item.seat_name,
            item.stock_id,
            item.stock_name,
            item.subject_key,
            item.theme_name,
            item.side,
            item.buy_amount,
            item.sell_amount,
            item.net_amount,
            item.reason,
            item.rank_order,
            item.is_theme_leader,
            json.dumps(item.style_tags, ensure_ascii=False),
            item.source_version,
            item.rule_version,
        )
        for item in items
    ]
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, payload)


async def main_async() -> int:
    args = parse_args()
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        stock_config = StockServiceConfig()
        if args.token:
            stock_config.tushare_token = args.token
        snapshot_service = TushareDragonTigerSnapshotService(stock_config)
        top_list = snapshot_service.fetch_or_cache_top_list(args.trade_date, force_refresh=args.force_refresh)
        top_inst = snapshot_service.fetch_or_cache_top_inst(args.trade_date, force_refresh=args.force_refresh)
        subject_links = await fetch_subject_links(
            manager,
            args.trade_date,
            [str(x.get("ts_code") or "") for x in top_inst.records],
        )
        service = HotMoneyActivityService()
        seat_masters = service.build_seat_masters(top_inst.records)
        activities = service.build_activities(
            trade_date=args.trade_date,
            top_inst_records=top_inst.records,
            top_list_records=top_list.records,
            subject_links=subject_links,
        )
        await upsert_seat_masters(manager, seat_masters)
        await upsert_activities(manager, activities)
        async with manager.pool.acquire() as conn:
            preview = await conn.fetch(
                """
                SELECT theme_name, stock_name, hot_money_name, side, net_amount
                FROM hot_money_trading_activity
                WHERE trade_date = $1::date
                ORDER BY ABS(net_amount) DESC, hot_money_name
                LIMIT $2
                """,
                _parse_trade_date(args.trade_date),
                args.top_k,
            )
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] seat_masters={len(seat_masters)}")
        print(f"[OK] activities={len(activities)}")
        for row in preview:
            print(
                f"  - {row['theme_name']} | {row['stock_name']} | {row['hot_money_name']} {row['side']} | net={float(row['net_amount'] or 0):.2f}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.services.auction_watch_universe_service import (
    AuctionWatchUniverseService,
    WatchCycleInput,
    WatchLeaderInput,
    WatchMainlineInput,
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
    parser = argparse.ArgumentParser(description="构建 auction_watch_universe")
    parser.add_argument("--trade-date", required=True, help="目标交易日 YYYY-MM-DD")
    parser.add_argument("--source-trade-date", default="", help="源交易日 YYYY-MM-DD，默认取目标交易日前一日")
    parser.add_argument("--top-k", type=int, default=40, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS auction_watch_universe (
        id BIGSERIAL PRIMARY KEY,
        source_trade_date DATE NOT NULL,
        trade_date DATE NOT NULL,
        stock_id TEXT NOT NULL,
        stock_name TEXT NOT NULL DEFAULT '',
        subject_key TEXT NOT NULL DEFAULT '',
        theme_name TEXT NOT NULL DEFAULT '',
        theme_tier TEXT NOT NULL DEFAULT '',
        mainline_alive BOOLEAN NOT NULL DEFAULT FALSE,
        primary_cycle_stage TEXT NOT NULL DEFAULT '',
        action_bias TEXT NOT NULL DEFAULT '',
        role_label TEXT NOT NULL DEFAULT '',
        candidate_rank INTEGER NOT NULL DEFAULT 0,
        candidate_priority TEXT NOT NULL DEFAULT '',
        is_reversal_watch BOOLEAN NOT NULL DEFAULT FALSE,
        source_type TEXT NOT NULL DEFAULT 'p3.phase3.auction_watch_universe',
        source_trace_id TEXT NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version TEXT NOT NULL DEFAULT 'auction_watch_universe.v1',
        rule_version TEXT NOT NULL DEFAULT 'auction_watch_universe.v1',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_auction_watch_universe UNIQUE (trade_date, stock_id, subject_key)
    );
    CREATE INDEX IF NOT EXISTS idx_awu_trade_date ON auction_watch_universe(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_awu_priority_trade_date ON auction_watch_universe(candidate_priority, trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute(
            "ALTER TABLE auction_watch_universe ADD COLUMN IF NOT EXISTS mainline_alive BOOLEAN NOT NULL DEFAULT FALSE"
        )


async def fetch_mainlines(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        v2.subject_key,
        COALESCE(NULLIF(v2.theme_name, ''), v2.subject_key) AS theme_name,
        COALESCE(v2.final_mainline_alive, FALSE) AS mainline_alive,
        COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
        COALESCE(v2.mainline_strength_score, 0) AS mainline_strength_score,
        COALESCE(v2.fade_watch, FALSE) AS fade_watch,
        COALESCE(v2.fade_confirmed, FALSE) AS fade_confirmed
    FROM theme_cycle_judgement_v2 v2
    WHERE v2.trade_date = $1
      AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_cycles(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
      v2.subject_key,
      COALESCE(NULLIF(v2.final_cycle_state, ''), 'fade') AS primary_cycle_stage,
      CASE
        WHEN COALESCE(v2.fade_confirmed, FALSE) THEN '观望'
        WHEN COALESCE(v2.final_cycle_state, '') IN ('climax', '高潮') THEN '警惕高潮'
        WHEN COALESCE(v2.final_cycle_state, '') IN ('fermentation', '发酵', 'start', '启动') THEN '可主做'
        WHEN COALESCE(v2.final_cycle_state, '') IN ('repair', '修复', 'divergence', '分歧', 'rebound', '回流') THEN '可做弱转强'
        ELSE '可观察'
      END AS action_bias
    FROM theme_cycle_judgement_v2 v2
    WHERE v2.trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_leaders(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT subject_key, stock_id, stock_name, role_label, candidate_rank
    FROM theme_leader_candidate
    WHERE trade_date = $1
      AND role_label IN ('龙头', '龙二', '卡位', '强趋势')
    ORDER BY subject_key, candidate_rank ASC, composite_score DESC
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def upsert_rows(manager: PostgresDatabaseManager, items):
    sql = """
    INSERT INTO auction_watch_universe (
        source_trade_date, trade_date, stock_id, stock_name, subject_key, theme_name,
        theme_tier, mainline_alive, primary_cycle_stage, action_bias, role_label, candidate_rank,
        candidate_priority, is_reversal_watch, source_type, source_trace_id, source_trace,
        source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5, $6,
        $7, $8, $9, $10, $11, $12,
        $13, $14, $15, $16, $17::jsonb,
        $18, $19
    )
    ON CONFLICT (trade_date, stock_id, subject_key)
    DO UPDATE SET
        source_trade_date = EXCLUDED.source_trade_date,
        stock_name = EXCLUDED.stock_name,
        theme_name = EXCLUDED.theme_name,
        theme_tier = EXCLUDED.theme_tier,
        mainline_alive = EXCLUDED.mainline_alive,
        primary_cycle_stage = EXCLUDED.primary_cycle_stage,
        action_bias = EXCLUDED.action_bias,
        role_label = EXCLUDED.role_label,
        candidate_rank = EXCLUDED.candidate_rank,
        candidate_priority = EXCLUDED.candidate_priority,
        is_reversal_watch = EXCLUDED.is_reversal_watch,
        source_type = EXCLUDED.source_type,
        source_trace_id = EXCLUDED.source_trace_id,
        source_trace = EXCLUDED.source_trace,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    payload = [
        (
            _parse_trade_date(item.source_trade_date),
            _parse_trade_date(item.trade_date),
            item.stock_id,
            item.stock_name,
            item.subject_key,
            item.theme_name,
            item.theme_tier,
            item.mainline_alive,
            item.primary_cycle_stage,
            item.action_bias,
            item.role_label,
            item.candidate_rank,
            item.candidate_priority,
            item.is_reversal_watch,
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
    target_trade_date = _parse_trade_date(args.trade_date)
    source_trade_date = _parse_trade_date(args.source_trade_date) if args.source_trade_date else (target_trade_date - timedelta(days=1))
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        mainlines = {str(r["subject_key"]): r for r in await fetch_mainlines(manager, source_trade_date)}
        cycles = {str(r["subject_key"]): r for r in await fetch_cycles(manager, source_trade_date)}
        leaders = await fetch_leaders(manager, source_trade_date)
        service = AuctionWatchUniverseService()
        items = []
        for row in leaders:
            subject_key = str(row["subject_key"])
            mainline_row = mainlines.get(subject_key)
            cycle_row = cycles.get(subject_key)
            if not mainline_row or not cycle_row:
                continue
            mainline = WatchMainlineInput(
                subject_key=subject_key,
                theme_name=mainline_row["theme_name"],
                mainline_alive=bool(mainline_row["mainline_alive"]),
                final_cycle_state=str(mainline_row.get("final_cycle_state") or ""),
                mainline_strength_score=float(mainline_row.get("mainline_strength_score") or 0.0),
                fade_watch=bool(mainline_row.get("fade_watch") or False),
                fade_confirmed=bool(mainline_row.get("fade_confirmed") or False),
            )
            cycle = WatchCycleInput(
                subject_key=subject_key,
                primary_cycle_stage=cycle_row["primary_cycle_stage"],
                action_bias=cycle_row["action_bias"],
            )
            leader = WatchLeaderInput(
                subject_key=subject_key,
                stock_id=str(row["stock_id"]),
                stock_name=row["stock_name"],
                role_label=row["role_label"],
                candidate_rank=int(row["candidate_rank"]),
            )
            if not service.is_eligible(mainline, cycle, leader):
                continue
            item = service.build_item(
                source_trade_date.isoformat(),
                target_trade_date.isoformat(),
                mainline,
                cycle,
                leader,
            )
            if item.candidate_priority == "P3":
                continue
            items.append(item)

        await upsert_rows(manager, items)

        ranked = sorted(items, key=lambda x: (x.candidate_priority, x.theme_name, x.candidate_rank, x.stock_id))
        print(f"[OK] source_trade_date={source_trade_date.isoformat()}")
        print(f"[OK] target_trade_date={target_trade_date.isoformat()}")
        print(f"[OK] rows={len(items)}")
        print(f"[OK] P1={sum(1 for x in items if x.candidate_priority == 'P1')}")
        print(f"[OK] P2={sum(1 for x in items if x.candidate_priority == 'P2')}")
        for item in ranked[: args.top_k]:
            print(
                f"[ROW] priority={item.candidate_priority} theme={item.theme_name} "
                f"stock={item.stock_name} role={item.role_label} "
                f"stage={item.primary_cycle_stage} bias={item.action_bias}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

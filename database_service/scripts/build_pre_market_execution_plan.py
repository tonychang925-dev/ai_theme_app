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
from stock_service.services.pre_market_execution_service import (
    ExecutionAuctionSignalInput,
    ExecutionCycleInput,
    ExecutionLeaderInput,
    ExecutionMainlineInput,
    PreMarketExecutionService,
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
    parser = argparse.ArgumentParser(description="构建 pre_market_execution_plan")
    parser.add_argument("--trade-date", required=True, help="目标交易日 YYYY-MM-DD")
    parser.add_argument("--source-trade-date", default="", help="源交易日 YYYY-MM-DD，默认取目标交易日前一日")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS pre_market_execution_plan (
        id BIGSERIAL PRIMARY KEY,
        source_trade_date DATE NOT NULL,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        theme_name VARCHAR(200) NOT NULL,
        theme_status VARCHAR(40) NOT NULL DEFAULT '',
        leader_stock_id VARCHAR(20) NOT NULL DEFAULT '',
        leader_stock_name VARCHAR(100) NOT NULL DEFAULT '',
        leader_status VARCHAR(40) NOT NULL DEFAULT '',
        action_today VARCHAR(20) NOT NULL DEFAULT '',
        action_bias VARCHAR(40) NOT NULL DEFAULT '',
        watch_reason TEXT NOT NULL DEFAULT '',
        auction_focus_stock_id VARCHAR(20) NOT NULL DEFAULT '',
        auction_focus_stock_name VARCHAR(100) NOT NULL DEFAULT '',
        auction_signal_level VARCHAR(20) NOT NULL DEFAULT '',
        auction_signal_type VARCHAR(60) NOT NULL DEFAULT '',
        auction_action_today VARCHAR(20) NOT NULL DEFAULT '',
        auction_signal_score NUMERIC(8,4) NOT NULL DEFAULT 0,
        auction_hard_reject_reason TEXT NOT NULL DEFAULT '',
        invalid_conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_pre_market_execution_plan UNIQUE (trade_date, subject_key)
    );
    ALTER TABLE pre_market_execution_plan ADD COLUMN IF NOT EXISTS source_trade_date DATE;
    UPDATE pre_market_execution_plan SET source_trade_date = trade_date WHERE source_trade_date IS NULL;
    ALTER TABLE pre_market_execution_plan ALTER COLUMN source_trade_date SET NOT NULL;
    ALTER TABLE pre_market_execution_plan ADD COLUMN IF NOT EXISTS auction_focus_stock_id VARCHAR(20) NOT NULL DEFAULT '';
    ALTER TABLE pre_market_execution_plan ADD COLUMN IF NOT EXISTS auction_focus_stock_name VARCHAR(100) NOT NULL DEFAULT '';
    ALTER TABLE pre_market_execution_plan ADD COLUMN IF NOT EXISTS auction_signal_level VARCHAR(20) NOT NULL DEFAULT '';
    ALTER TABLE pre_market_execution_plan ADD COLUMN IF NOT EXISTS auction_signal_type VARCHAR(60) NOT NULL DEFAULT '';
    ALTER TABLE pre_market_execution_plan ADD COLUMN IF NOT EXISTS auction_action_today VARCHAR(20) NOT NULL DEFAULT '';
    ALTER TABLE pre_market_execution_plan ADD COLUMN IF NOT EXISTS auction_signal_score NUMERIC(8,4) NOT NULL DEFAULT 0;
    ALTER TABLE pre_market_execution_plan ADD COLUMN IF NOT EXISTS auction_hard_reject_reason TEXT NOT NULL DEFAULT '';
    CREATE INDEX IF NOT EXISTS idx_pmep_trade_date ON pre_market_execution_plan(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_pmep_action_trade_date ON pre_market_execution_plan(action_today, trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def fetch_mainlines(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT subject_key, theme_name, is_main_theme, theme_tier, conclusion
    FROM theme_mainline_judgement
    WHERE trade_date = $1
      AND theme_tier IN ('main', 'strong_branch')
    ORDER BY
      CASE theme_tier WHEN 'main' THEN 0 ELSE 1 END,
      subject_key
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_cycles(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT subject_key, primary_cycle_stage, action_bias, leader_status, board_effect_status, conclusion
    FROM theme_cycle_judgement
    WHERE trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_leaders(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        c.subject_key,
        c.stock_id,
        c.stock_name,
        c.role_label,
        c.candidate_rank,
        c.composite_score,
        COALESCE(p.position_label, '') AS position_label,
        COALESCE(x.pattern_labels, '[]'::jsonb) AS pattern_labels
    FROM theme_leader_candidate c
    LEFT JOIN stock_position_judgement p
      ON p.trade_date = c.trade_date
     AND split_part(p.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
    LEFT JOIN stock_pattern_judgement x
      ON x.trade_date = c.trade_date
     AND split_part(x.stock_id, '.', 1) = split_part(c.stock_id, '.', 1)
    WHERE c.trade_date = $1
      AND candidate_rank = 1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    items = []
    for row in rows:
        item = dict(row)
        if isinstance(item.get("pattern_labels"), str):
            try:
                item["pattern_labels"] = json.loads(item["pattern_labels"])
            except Exception:
                item["pattern_labels"] = []
        items.append(item)
    return items


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


async def fetch_auction_signals(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT stock_id, stock_name, subject_key, theme_name,
           auction_signal_level, signal_type, action_today,
           hard_reject_reason, auction_signal_score
    FROM pre_market_auction_signal
    WHERE trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    result = {}
    priority = {"act": 0, "watch": 1, "avoid": 2}
    for row in rows:
        item = dict(row)
        subject_key = str(row["subject_key"])
        current = result.get(subject_key)
        rank = (priority.get(item["action_today"], 9), -float(item.get("auction_signal_score") or 0.0))
        current_rank = (
            priority.get(current["action_today"], 9),
            -float(current.get("auction_signal_score") or 0.0),
        ) if current else None
        if current is None or rank < current_rank:
            result[subject_key] = item
    return result


async def upsert_rows(manager: PostgresDatabaseManager, plans):
    sql = """
    INSERT INTO pre_market_execution_plan (
        source_trade_date, trade_date, subject_key, theme_name, theme_status,
        leader_stock_id, leader_stock_name, leader_status,
        action_today, action_bias, watch_reason,
        auction_focus_stock_id, auction_focus_stock_name,
        auction_signal_level, auction_signal_type, auction_action_today,
        auction_signal_score, auction_hard_reject_reason,
        invalid_conditions
    ) VALUES (
        $1, $2, $3, $4, $5,
        $6, $7, $8,
        $9, $10, $11,
        $12, $13,
        $14, $15, $16,
        $17, $18,
        $19::jsonb
    )
    ON CONFLICT (trade_date, subject_key)
    DO UPDATE SET
        source_trade_date = EXCLUDED.source_trade_date,
        theme_name = EXCLUDED.theme_name,
        theme_status = EXCLUDED.theme_status,
        leader_stock_id = EXCLUDED.leader_stock_id,
        leader_stock_name = EXCLUDED.leader_stock_name,
        leader_status = EXCLUDED.leader_status,
        action_today = EXCLUDED.action_today,
        action_bias = EXCLUDED.action_bias,
        watch_reason = EXCLUDED.watch_reason,
        auction_focus_stock_id = EXCLUDED.auction_focus_stock_id,
        auction_focus_stock_name = EXCLUDED.auction_focus_stock_name,
        auction_signal_level = EXCLUDED.auction_signal_level,
        auction_signal_type = EXCLUDED.auction_signal_type,
        auction_action_today = EXCLUDED.auction_action_today,
        auction_signal_score = EXCLUDED.auction_signal_score,
        auction_hard_reject_reason = EXCLUDED.auction_hard_reject_reason,
        invalid_conditions = EXCLUDED.invalid_conditions,
        updated_at = NOW()
    """
    payload = [
        (
            _parse_trade_date(item.source_trade_date),
            _parse_trade_date(item.trade_date),
            item.subject_key,
            item.theme_name,
            item.theme_status,
            item.leader_stock_id,
            item.leader_stock_name,
            item.leader_status,
            item.action_today,
            item.action_bias,
            item.watch_reason,
            item.auction_focus_stock_id,
            item.auction_focus_stock_name,
            item.auction_signal_level,
            item.auction_signal_type,
            item.auction_action_today,
            item.auction_signal_score,
            item.auction_hard_reject_reason,
            json.dumps(item.invalid_conditions, ensure_ascii=False),
        )
        for item in plans
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
        mainlines = await fetch_mainlines(manager, source_trade_date)
        cycles = {str(row["subject_key"]): row for row in await fetch_cycles(manager, source_trade_date)}
        leaders = {str(row["subject_key"]): row for row in await fetch_leaders(manager, source_trade_date)}
        auction_signals = await fetch_auction_signals(manager, target_trade_date)

        service = PreMarketExecutionService()
        plans = []
        for row in mainlines:
            subject_key = str(row["subject_key"])
            cycle_row = cycles.get(subject_key)
            if not cycle_row:
                continue
            leader_row = leaders.get(subject_key)
            auction_signal = None
            signal_row = auction_signals.get(subject_key)
            if signal_row:
                auction_signal = ExecutionAuctionSignalInput(
                    stock_id=str(signal_row["stock_id"]),
                    stock_name=signal_row["stock_name"],
                    auction_signal_level=signal_row["auction_signal_level"],
                    signal_type=signal_row["signal_type"],
                    action_today=signal_row["action_today"],
                    hard_reject_reason=signal_row["hard_reject_reason"],
                    auction_signal_score=float(signal_row["auction_signal_score"] or 0.0),
                )
            plans.append(
                service.build_plan(
                    source_trade_date.isoformat(),
                    target_trade_date.isoformat(),
                    ExecutionMainlineInput(
                        subject_key=subject_key,
                        theme_name=row["theme_name"],
                        is_main_theme=bool(row["is_main_theme"]),
                        theme_tier=row["theme_tier"],
                        conclusion=row["conclusion"],
                    ),
                    ExecutionCycleInput(
                        subject_key=subject_key,
                        primary_cycle_stage=cycle_row["primary_cycle_stage"],
                        action_bias=cycle_row["action_bias"],
                        leader_status=cycle_row["leader_status"],
                        board_effect_status=cycle_row["board_effect_status"],
                        conclusion=cycle_row["conclusion"],
                    ),
                    ExecutionLeaderInput(
                        subject_key=subject_key,
                        stock_id=str(leader_row["stock_id"]) if leader_row else "",
                        stock_name=leader_row["stock_name"] if leader_row else "",
                        role_label=leader_row["role_label"] if leader_row else "",
                        candidate_rank=int(leader_row["candidate_rank"]) if leader_row else 0,
                        composite_score=float(leader_row["composite_score"]) if leader_row else 0.0,
                        position_label=str(leader_row.get("position_label") or "") if leader_row else "",
                        pattern_labels=tuple(str(x) for x in (leader_row.get("pattern_labels") or [])) if leader_row else (),
                    ) if leader_row else None,
                    auction_signal,
                )
            )

        await upsert_rows(manager, plans)

        ranked = sorted(plans, key=lambda item: (0 if item.action_today == "act" else 1 if item.action_today == "watch" else 2, item.theme_name))
        print(f"[OK] source_trade_date={source_trade_date.isoformat()}")
        print(f"[OK] target_trade_date={target_trade_date.isoformat()}")
        print(f"[OK] rows={len(plans)}")
        print(f"[OK] act={sum(1 for x in plans if x.action_today == 'act')}")
        print(f"[OK] watch={sum(1 for x in plans if x.action_today == 'watch')}")
        print(f"[OK] avoid={sum(1 for x in plans if x.action_today == 'avoid')}")
        for item in ranked[: args.top_k]:
            print(
                f"[ROW] action={item.action_today} theme={item.theme_name} "
                f"theme_status={item.theme_status} leader={item.leader_stock_name or '--'} "
                f"leader_status={item.leader_status} bias={item.action_bias}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

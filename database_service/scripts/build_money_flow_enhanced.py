#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from stock_service.services.money_flow_enhanced_service import (
    MoneyFlowEnhancedService,
    MoneyFlowInput,
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
    parser = argparse.ArgumentParser(description="构建 money_flow_enhanced")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS money_flow_enhanced (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        theme_name VARCHAR(200) NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100) NOT NULL,
        role_label VARCHAR(40) NOT NULL DEFAULT '',
        role_enhanced VARCHAR(40) NOT NULL DEFAULT '',
        candidate_rank INTEGER NOT NULL DEFAULT 0,
        composite_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        activity_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        capital_flow_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        money_flow_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        money_flow_tier VARCHAR(20) NOT NULL DEFAULT '',
        turnover_rate NUMERIC(8,2) NOT NULL DEFAULT 0,
        volume_ratio NUMERIC(8,2) NOT NULL DEFAULT 0,
        main_net_inflow NUMERIC(18,2) NOT NULL DEFAULT 0,
        dragon_tiger_net_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
        institution_seat_count INTEGER NOT NULL DEFAULT 0,
        explanation JSONB NOT NULL DEFAULT '[]'::jsonb,
        sources JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.money_flow',
        source_trace_id VARCHAR(40) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_money_flow_enhanced UNIQUE (trade_date, subject_key, stock_id)
    );
    CREATE INDEX IF NOT EXISTS idx_mfe_trade_date ON money_flow_enhanced(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_mfe_subject_date ON money_flow_enhanced(subject_key, trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_mfe_tier_date ON money_flow_enhanced(money_flow_tier, trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_mfe_trade_subject_stockcode
        ON money_flow_enhanced (trade_date, subject_key, (split_part(stock_id, '.', 1)));
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute("ALTER TABLE money_flow_enhanced ADD COLUMN IF NOT EXISTS source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.money_flow'")
        await conn.execute("ALTER TABLE money_flow_enhanced ADD COLUMN IF NOT EXISTS source_trace_id VARCHAR(40) NOT NULL DEFAULT ''")
        await conn.execute("ALTER TABLE money_flow_enhanced ADD COLUMN IF NOT EXISTS source_trace JSONB NOT NULL DEFAULT '{}'::jsonb")


async def fetch_candidate_rows(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        c.subject_key,
        c.theme_name,
        c.stock_id,
        c.stock_name,
        c.role_label,
        c.candidate_rank,
        c.composite_score,
        c.turnover_rate,
        c.volume_ratio,
        c.main_net_inflow,
        c.is_limit_up,
        c.source_trace_id,
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
    ORDER BY subject_key, candidate_rank ASC
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


async def fetch_dragon_rows(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        stock_id,
        net_amount,
        institution_seat_count,
        source_trace_id
    FROM dragon_tiger_object
    WHERE trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def upsert_rows(manager: PostgresDatabaseManager, items):
    sql = """
    INSERT INTO money_flow_enhanced (
        trade_date, subject_key, theme_name, stock_id, stock_name,
        role_label, role_enhanced, candidate_rank, composite_score,
        activity_score, capital_flow_score, money_flow_score, money_flow_tier,
        turnover_rate, volume_ratio, main_net_inflow, dragon_tiger_net_amount,
        institution_seat_count, explanation, sources, source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5,
        $6, $7, $8, $9,
        $10, $11, $12, $13,
        $14, $15, $16, $17,
        $18, $19::jsonb, $20::jsonb, $21, $22, $23::jsonb, $24, $25
    )
    ON CONFLICT (trade_date, subject_key, stock_id)
    DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        stock_name = EXCLUDED.stock_name,
        role_label = EXCLUDED.role_label,
        role_enhanced = EXCLUDED.role_enhanced,
        candidate_rank = EXCLUDED.candidate_rank,
        composite_score = EXCLUDED.composite_score,
        activity_score = EXCLUDED.activity_score,
        capital_flow_score = EXCLUDED.capital_flow_score,
        money_flow_score = EXCLUDED.money_flow_score,
        money_flow_tier = EXCLUDED.money_flow_tier,
        turnover_rate = EXCLUDED.turnover_rate,
        volume_ratio = EXCLUDED.volume_ratio,
        main_net_inflow = EXCLUDED.main_net_inflow,
        dragon_tiger_net_amount = EXCLUDED.dragon_tiger_net_amount,
        institution_seat_count = EXCLUDED.institution_seat_count,
        explanation = EXCLUDED.explanation,
        sources = EXCLUDED.sources,
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
            item.subject_key,
            item.theme_name,
            item.stock_id,
            item.stock_name,
            item.role_label,
            item.role_enhanced,
            item.candidate_rank,
            item.composite_score,
            item.activity_score,
            item.capital_flow_score,
            item.money_flow_score,
            item.money_flow_tier,
            item.turnover_rate,
            item.volume_ratio,
            item.main_net_inflow,
            item.dragon_tiger_net_amount,
            item.institution_seat_count,
            json.dumps(item.explanation, ensure_ascii=False),
            json.dumps(item.sources, ensure_ascii=False),
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
        candidate_rows = await fetch_candidate_rows(manager, trade_date_value)
        dragon_rows = await fetch_dragon_rows(manager, trade_date_value)
        dragon_map = {str(row["stock_id"]): dict(row) for row in dragon_rows}

        service = MoneyFlowEnhancedService()
        items = []
        for row in candidate_rows:
            dragon = dragon_map.get(str(row["stock_id"]), {})
            item = service.build_item(
                MoneyFlowInput(
                    trade_date=args.trade_date,
                    subject_key=str(row["subject_key"]),
                    theme_name=str(row["theme_name"]),
                    stock_id=str(row["stock_id"]),
                    stock_name=str(row["stock_name"]),
                    role_label=str(row["role_label"]),
                    candidate_rank=int(row["candidate_rank"] or 0),
                    composite_score=float(row["composite_score"] or 0),
                    turnover_rate=float(row["turnover_rate"] or 0),
                    volume_ratio=float(row["volume_ratio"] or 0),
                    main_net_inflow=float(row["main_net_inflow"] or 0),
                    is_limit_up=bool(row["is_limit_up"]),
                    dragon_tiger_net_amount=float(dragon.get("net_amount") or 0),
                    institution_seat_count=int(dragon.get("institution_seat_count") or 0),
                    position_label=str(row.get("position_label") or ""),
                    pattern_labels=tuple(str(x) for x in (row.get("pattern_labels") or [])),
                )
            )
            source_trace = {
                "datasets": [
                    "theme_leader_candidate",
                    "dragon_tiger_object",
                    "stock_position_judgement",
                    "stock_pattern_judgement",
                ],
                "trade_date": args.trade_date,
                "subject_key": str(row["subject_key"]),
                "stock_id": str(row["stock_id"]),
                "leader_trace_id": str(row.get("source_trace_id") or ""),
                "dragon_tiger_trace_id": str(dragon.get("source_trace_id") or ""),
            }
            source_trace_id = hashlib.md5(
                f"money|{args.trade_date}|{row['subject_key']}|{row['stock_id']}|{row['candidate_rank']}".encode("utf-8")
            ).hexdigest()[:16]
            items.append(
                type(item)(
                    **{
                        **item.__dict__,
                        "source_trace_id": source_trace_id,
                        "source_trace": source_trace,
                    }
                )
            )
        await upsert_rows(manager, items)

        async with manager.pool.acquire() as conn:
            preview = await conn.fetch(
                """
                SELECT theme_name, stock_name, role_enhanced, money_flow_tier, money_flow_score
                FROM money_flow_enhanced
                WHERE trade_date = $1
                ORDER BY money_flow_score DESC, stock_id ASC
                LIMIT $2
                """,
                trade_date_value,
                args.top_k,
            )
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] rows={len(items)}")
        for row in preview:
            print(
                f"  - {row['theme_name']} / {row['stock_name']} | "
                f"{row['role_enhanced']} | {row['money_flow_tier']} | {float(row['money_flow_score'] or 0):.2f}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

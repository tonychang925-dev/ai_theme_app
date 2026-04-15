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
from stock_service.services.theme_leader_llm_queue_service import (
    ThemeLeaderLlmQueueInput,
    ThemeLeaderLlmQueueService,
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
    parser = argparse.ArgumentParser(description="构建 leader_llm_queue")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--top-k", type=int, default=10, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_table(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS theme_leader_llm_queue (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        theme_name VARCHAR(200) NOT NULL,
        theme_tier VARCHAR(40) NOT NULL DEFAULT '',
        primary_cycle_stage VARCHAR(40) NOT NULL DEFAULT '',
        need_llm_judgement BOOLEAN NOT NULL DEFAULT FALSE,
        is_trade_focus BOOLEAN NOT NULL DEFAULT FALSE,
        queue_priority INTEGER NOT NULL DEFAULT 0,
        queue_reason TEXT NOT NULL DEFAULT '',
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.leader_llm_queue',
        source_trace_id VARCHAR(40) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_leader_llm_queue UNIQUE (trade_date, subject_key)
    );
    CREATE INDEX IF NOT EXISTS idx_tllq_trade_date ON theme_leader_llm_queue(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_tllq_priority ON theme_leader_llm_queue(trade_date DESC, queue_priority DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def fetch_rows(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        m.trade_date::text AS trade_date,
        m.subject_key,
        m.theme_name,
        COALESCE(m.theme_tier, '') AS theme_tier,
        COALESCE(MAX(COALESCE(m.event_chain_score, 0) + COALESCE(m.market_recognition_score, 0) + COALESCE(m.mainline_stability_score, 0)), 0) AS ranking_score,
        COALESCE(c.primary_cycle_stage, '') AS primary_cycle_stage,
        COALESCE(c.leader_status, '') AS leader_status,
        COALESCE(c.action_bias, '') AS action_bias,
        COUNT(l.stock_id) AS candidate_count,
        COUNT(*) FILTER (WHERE COALESCE(l.is_limit_up, FALSE)) AS limit_up_count,
        COALESCE(MAX(CASE WHEN l.candidate_rank = 1 THEN l.composite_score END), 0) AS top_candidate_score,
        COALESCE(MAX(CASE WHEN l.candidate_rank = 2 THEN l.composite_score END), 0) AS second_candidate_score,
        COALESCE(MAX(CASE WHEN l.candidate_rank = 1 AND COALESCE(l.is_limit_up, FALSE) THEN 1 ELSE 0 END), 0) = 1 AS top_is_limit_up,
        COALESCE(MAX(CASE WHEN l.candidate_rank = 2 AND COALESCE(l.is_limit_up, FALSE) THEN 1 ELSE 0 END), 0) = 1 AS second_is_limit_up,
        COALESCE(MAX(CASE WHEN l.candidate_rank = 1 THEN l.role_label END), '') AS top_role_label,
        COALESCE(MAX(CASE WHEN l.candidate_rank = 2 THEN l.role_label END), '') AS second_role_label
    FROM theme_mainline_judgement m
    LEFT JOIN theme_cycle_judgement c
      ON c.trade_date = m.trade_date
     AND c.subject_key = m.subject_key
    LEFT JOIN theme_leader_candidate l
      ON l.trade_date = m.trade_date
     AND l.subject_key = m.subject_key
    WHERE m.trade_date = $1::date
      AND COALESCE(m.theme_tier, '') IN ('main', 'strong_branch')
    GROUP BY
        m.trade_date, m.subject_key, m.theme_name, m.theme_tier,
        c.primary_cycle_stage, c.leader_status, c.action_bias
    ORDER BY
        CASE COALESCE(m.theme_tier, '')
            WHEN 'main' THEN 0
            WHEN 'strong_branch' THEN 1
            ELSE 2
        END,
        ranking_score DESC,
        m.subject_key
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def upsert_rows(manager: PostgresDatabaseManager, items: list[dict]) -> None:
    if not items:
        return
    sql = """
    INSERT INTO theme_leader_llm_queue (
        trade_date, subject_key, theme_name, theme_tier, primary_cycle_stage,
        need_llm_judgement, is_trade_focus, queue_priority, queue_reason,
        source_type, source_trace_id, source_trace, source_version, rule_version, updated_at
    ) VALUES (
        $1::date, $2, $3, $4, $5,
        $6, $7, $8, $9,
        $10, $11, $12::jsonb, $13, $14, NOW()
    )
    ON CONFLICT (trade_date, subject_key)
    DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        theme_tier = EXCLUDED.theme_tier,
        primary_cycle_stage = EXCLUDED.primary_cycle_stage,
        need_llm_judgement = EXCLUDED.need_llm_judgement,
        is_trade_focus = EXCLUDED.is_trade_focus,
        queue_priority = EXCLUDED.queue_priority,
        queue_reason = EXCLUDED.queue_reason,
        source_type = EXCLUDED.source_type,
        source_trace_id = EXCLUDED.source_trace_id,
        source_trace = EXCLUDED.source_trace,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    payload = [
        (
            _parse_trade_date(item["trade_date"]),
            item["subject_key"],
            item["theme_name"],
            item["theme_tier"],
            item["primary_cycle_stage"],
            item["need_llm_judgement"],
            item["is_trade_focus"],
            item["queue_priority"],
            item["queue_reason"],
            item["source_type"],
            item["source_trace_id"],
            json.dumps(item["source_trace"], ensure_ascii=False),
            item["source_version"],
            item["rule_version"],
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
        await ensure_table(manager)
        rows = await fetch_rows(manager, _parse_trade_date(args.trade_date))
        service = ThemeLeaderLlmQueueService()
        items: list[dict] = []
        for row in rows:
            decision = service.evaluate(
                ThemeLeaderLlmQueueInput(
                    trade_date=row["trade_date"],
                    subject_key=str(row["subject_key"] or ""),
                    theme_name=str(row["theme_name"] or ""),
                    theme_tier=str(row["theme_tier"] or ""),
                    primary_cycle_stage=str(row["primary_cycle_stage"] or ""),
                    leader_status=str(row["leader_status"] or ""),
                    action_bias=str(row["action_bias"] or ""),
                    candidate_count=int(row["candidate_count"] or 0),
                    limit_up_count=int(row["limit_up_count"] or 0),
                    top_candidate_score=float(row["top_candidate_score"] or 0),
                    second_candidate_score=float(row["second_candidate_score"] or 0),
                    top_is_limit_up=bool(row["top_is_limit_up"]),
                    second_is_limit_up=bool(row["second_is_limit_up"]),
                    top_role_label=str(row["top_role_label"] or ""),
                    second_role_label=str(row["second_role_label"] or ""),
                )
            )
            source_trace = {
                "candidate_count": int(row["candidate_count"] or 0),
                "limit_up_count": int(row["limit_up_count"] or 0),
                "leader_status": str(row["leader_status"] or ""),
                "action_bias": str(row["action_bias"] or ""),
                "top_candidate_score": float(row["top_candidate_score"] or 0),
                "second_candidate_score": float(row["second_candidate_score"] or 0),
            }
            source_trace_id = hashlib.sha1(
                f"{decision.trade_date}|{decision.subject_key}|{decision.queue_priority}|{decision.queue_reason}".encode("utf-8")
            ).hexdigest()[:16]
            items.append({**decision.__dict__, "source_trace_id": source_trace_id, "source_trace": source_trace})
        await upsert_rows(manager, items)
        queued = [item for item in items if item["need_llm_judgement"]]
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] theme_count={len(items)}")
        print(f"[OK] queued_count={len(queued)}")
        for item in sorted(queued, key=lambda x: (-int(x['queue_priority']), x['subject_key']))[: max(args.top_k, 0)]:
            print(
                f"[QUEUE] priority={item['queue_priority']} subject_key={item['subject_key']} "
                f"theme={item['theme_name']} stage={item['primary_cycle_stage']} reason={item['queue_reason']}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

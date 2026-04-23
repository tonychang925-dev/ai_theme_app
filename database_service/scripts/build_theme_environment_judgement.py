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
from stock_service.services.theme_environment_judgement_service import (
    ThemeEnvironmentInput,
    ThemeEnvironmentJudgementService,
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
    parser = argparse.ArgumentParser(description="构建 theme_environment_judgement")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--top-k", type=int, default=12, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS theme_environment_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        theme_name VARCHAR(200) NOT NULL,
        board_health_status VARCHAR(80) NOT NULL DEFAULT '',
        board_effect_status VARCHAR(80) NOT NULL DEFAULT '',
        leader_support_status VARCHAR(80) NOT NULL DEFAULT '',
        follow_strength_status VARCHAR(80) NOT NULL DEFAULT '',
        action_bias VARCHAR(40) NOT NULL DEFAULT '',
        conclusion TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase3.theme_environment_judgement',
        source_trace_id VARCHAR(40) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_environment_judgement UNIQUE (trade_date, subject_key)
    );
    CREATE INDEX IF NOT EXISTS idx_theme_environment_judgement_trade_date
      ON theme_environment_judgement(trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def fetch_rows(manager: PostgresDatabaseManager, trade_date_value: date) -> list[dict]:
    sql = """
    WITH market AS (
        SELECT
            s.subject_key,
            COALESCE(b.theme_name, s.subject_key) AS theme_name,
            COUNT(*) FILTER (WHERE s.limit_up) AS limit_up_count,
            COUNT(*) FILTER (WHERE COALESCE(s.pct_chg, 0) >= 5) AS strong_stock_count,
            COALESCE(MAX(CASE WHEN s.is_leader THEN s.pct_chg END), 0) AS leader_pct_chg,
            COUNT(*) AS member_count,
            COALESCE(MAX(CASE WHEN s.is_leader AND s.limit_up THEN 1 ELSE 0 END), 0) = 1 AS leader_limit_up
        FROM subject_stock_daily_snapshot s
        LEFT JOIN vw_subject_theme_binding b
          ON b.subject_key = s.subject_key
        WHERE s.trade_date = $1
        GROUP BY s.subject_key, COALESCE(b.theme_name, s.subject_key)
    )
    SELECT
        v2.subject_key,
        COALESCE(NULLIF(v2.theme_name, ''), market.theme_name, v2.subject_key) AS theme_name,
        COALESCE(v2.final_mainline_alive, FALSE) AS mainline_alive,
        COALESCE(v2.mainline_strength_score, 0) AS mainline_strength_score,
        COALESCE(v2.final_cycle_state, '') AS final_cycle_state,
        COALESCE(NULLIF(v2.final_cycle_state, ''), 'fade') AS primary_cycle_stage,
        CASE
            WHEN COALESCE(v2.fade_confirmed, FALSE) THEN '观望'
            WHEN COALESCE(v2.final_cycle_state, '') IN ('climax', '高潮') THEN '警惕高潮'
            WHEN COALESCE(v2.final_cycle_state, '') IN ('fermentation', '发酵', 'start', '启动') THEN '可主做'
            WHEN COALESCE(v2.final_cycle_state, '') IN ('repair', '修复', 'divergence', '分歧', 'rebound', '回流') THEN '可做弱转强'
            ELSE '可观察'
        END AS cycle_action_bias,
        market.limit_up_count,
        market.strong_stock_count,
        market.member_count,
        market.leader_limit_up,
        market.leader_pct_chg
    FROM theme_cycle_judgement_v2 v2
    LEFT JOIN market
      ON market.subject_key = v2.subject_key
    WHERE v2.trade_date = $1
      AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
      AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
    ORDER BY
      COALESCE(v2.mainline_strength_score, 0) DESC,
      COALESCE(NULLIF(v2.theme_name, ''), market.theme_name, v2.subject_key)
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def upsert_rows(manager: PostgresDatabaseManager, items) -> None:
    sql = """
    INSERT INTO theme_environment_judgement (
        trade_date, subject_key, theme_name,
        board_health_status, board_effect_status, leader_support_status, follow_strength_status,
        action_bias, conclusion, evidence,
        source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3,
        $4, $5, $6, $7,
        $8, $9, $10::jsonb,
        $11, $12, $13::jsonb, $14, $15
    )
    ON CONFLICT (trade_date, subject_key)
    DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        board_health_status = EXCLUDED.board_health_status,
        board_effect_status = EXCLUDED.board_effect_status,
        leader_support_status = EXCLUDED.leader_support_status,
        follow_strength_status = EXCLUDED.follow_strength_status,
        action_bias = EXCLUDED.action_bias,
        conclusion = EXCLUDED.conclusion,
        evidence = EXCLUDED.evidence,
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
            item.board_health_status,
            item.board_effect_status,
            item.leader_support_status,
            item.follow_strength_status,
            item.action_bias,
            item.conclusion,
            json.dumps(item.evidence, ensure_ascii=False),
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
        rows = await fetch_rows(manager, trade_date_value)
        service = ThemeEnvironmentJudgementService()
        judgements = []
        for row in rows:
            judgement = service.build_judgement(
                trade_date_value.isoformat(),
                ThemeEnvironmentInput(
                    subject_key=str(row["subject_key"]),
                    theme_name=str(row["theme_name"] or row["subject_key"]),
                    mainline_alive=bool(row.get("mainline_alive")),
                    mainline_strength_score=float(row.get("mainline_strength_score") or 0.0),
                    primary_cycle_stage=str(row.get("primary_cycle_stage") or "fade"),
                    action_bias=str(row.get("cycle_action_bias") or ""),
                    limit_up_count=int(row.get("limit_up_count") or 0),
                    strong_stock_count=int(row.get("strong_stock_count") or 0),
                    member_count=int(row.get("member_count") or 0),
                    leader_limit_up=bool(row.get("leader_limit_up")),
                    leader_pct_chg=float(row.get("leader_pct_chg") or 0.0),
                ),
            )
            trace_payload = {
                "mainline_alive": bool(row.get("mainline_alive")),
                "mainline_strength_score": float(row.get("mainline_strength_score") or 0.0),
                "final_cycle_state": row.get("final_cycle_state"),
                "primary_cycle_stage": row.get("primary_cycle_stage"),
                "limit_up_count": int(row.get("limit_up_count") or 0),
                "strong_stock_count": int(row.get("strong_stock_count") or 0),
            }
            trace_seed = json.dumps(trace_payload, ensure_ascii=False, sort_keys=True)
            judgement = judgement.__class__(
                **{
                    **judgement.__dict__,
                    "source_trace_id": hashlib.sha1(trace_seed.encode("utf-8")).hexdigest()[:16],
                    "source_trace": trace_payload,
                }
            )
            judgements.append(judgement)

        await upsert_rows(manager, judgements)
        print(f"[OK] trade_date={trade_date_value.isoformat()}")
        print(f"[OK] rows={len(judgements)}")
        for item in judgements[: args.top_k]:
            print(
                f"[ROW] theme={item.theme_name} board={item.board_health_status} "
                f"effect={item.board_effect_status} leader={item.leader_support_status} "
                f"follow={item.follow_strength_status} action={item.action_bias}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

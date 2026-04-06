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
from stock_service.models import MarketEnvironmentMetrics
from stock_service.services.market_environment_judgement_service import MarketEnvironmentJudgementService


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
    parser = argparse.ArgumentParser(description="构建 market_environment_judgement")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS market_environment_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL UNIQUE,
        market_health_score NUMERIC(10,4) NOT NULL DEFAULT 0,
        market_bias VARCHAR(40) NOT NULL DEFAULT '',
        breadth_status VARCHAR(80) NOT NULL DEFAULT '',
        short_term_sentiment_status VARCHAR(80) NOT NULL DEFAULT '',
        relay_sentiment_status VARCHAR(80) NOT NULL DEFAULT '',
        intraday_fade_status VARCHAR(80) NOT NULL DEFAULT '',
        action_bias VARCHAR(40) NOT NULL DEFAULT '',
        conclusion TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase3.market_environment_judgement',
        source_trace_id VARCHAR(40) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_market_environment_judgement_trade_date
      ON market_environment_judgement(trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)


async def fetch_metrics(manager: PostgresDatabaseManager, trade_date_value: date) -> MarketEnvironmentMetrics | None:
    sql = """
    SELECT
        trade_date,
        up_count,
        down_count,
        flat_count,
        advance_decline_ratio,
        limit_up_count,
        limit_down_count,
        limit_up_down_ratio,
        yesterday_limit_up_open_strength,
        yesterday_limit_up_open_red_ratio,
        yesterday_limit_up_premium_ratio,
        yesterday_limit_up_fade_ratio,
        yesterday_limit_up_fail_ratio,
        morning_high_then_fall_count,
        morning_high_then_fall_ratio,
        intraday_fade_count,
        intraday_fade_ratio,
        high_mark_strong_count,
        high_mark_weak_count,
        market_volume_change_pct,
        market_avg_open_pct,
        market_avg_close_pct,
        source_type,
        source_trace_id,
        source_trace,
        source_version,
        rule_version
    FROM market_environment_metrics
    WHERE trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        row = await conn.fetchrow(sql, trade_date_value)
    if not row:
        return None
    item = dict(row)
    item["trade_date"] = item["trade_date"].isoformat()
    return MarketEnvironmentMetrics(**item)


async def upsert_row(manager: PostgresDatabaseManager, item) -> None:
    sql = """
    INSERT INTO market_environment_judgement (
        trade_date, market_health_score, market_bias, breadth_status,
        short_term_sentiment_status, relay_sentiment_status, intraday_fade_status,
        action_bias, conclusion, evidence,
        source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4,
        $5, $6, $7,
        $8, $9, $10::jsonb,
        $11, $12, $13::jsonb, $14, $15
    )
    ON CONFLICT (trade_date)
    DO UPDATE SET
        market_health_score = EXCLUDED.market_health_score,
        market_bias = EXCLUDED.market_bias,
        breadth_status = EXCLUDED.breadth_status,
        short_term_sentiment_status = EXCLUDED.short_term_sentiment_status,
        relay_sentiment_status = EXCLUDED.relay_sentiment_status,
        intraday_fade_status = EXCLUDED.intraday_fade_status,
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
    async with manager.pool.acquire() as conn:
        await conn.execute(
            sql,
            _parse_trade_date(item.trade_date),
            item.market_health_score,
            item.market_bias,
            item.breadth_status,
            item.short_term_sentiment_status,
            item.relay_sentiment_status,
            item.intraday_fade_status,
            item.action_bias,
            item.conclusion,
            json.dumps(item.evidence, ensure_ascii=False),
            item.source_type,
            item.source_trace_id,
            json.dumps(item.source_trace, ensure_ascii=False),
            item.source_version,
            item.rule_version,
        )


async def main_async() -> int:
    args = parse_args()
    trade_date_value = _parse_trade_date(args.trade_date)
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        metrics = await fetch_metrics(manager, trade_date_value)
        if metrics is None:
            print(f"[WARN] missing market_environment_metrics trade_date={trade_date_value.isoformat()}")
            return 1

        service = MarketEnvironmentJudgementService()
        judgement = service.build_judgement(metrics)
        trace_payload = {
            "metrics_source_trace_id": metrics.source_trace_id,
            "market_health_score": judgement.market_health_score,
            "daily_proxy": True,
        }
        trace_seed = json.dumps(trace_payload, ensure_ascii=False, sort_keys=True)
        judgement = judgement.__class__(
            **{
                **judgement.__dict__,
                "source_trace_id": hashlib.sha1(trace_seed.encode("utf-8")).hexdigest()[:16],
                "source_trace": trace_payload,
            }
        )
        await upsert_row(manager, judgement)

        print(f"[OK] trade_date={judgement.trade_date}")
        print(f"[OK] market_health_score={judgement.market_health_score:.2f}")
        print(f"[OK] market_bias={judgement.market_bias}")
        print(f"[OK] action_bias={judgement.action_bias}")
        print(f"[OK] source_trace_id={judgement.source_trace_id}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

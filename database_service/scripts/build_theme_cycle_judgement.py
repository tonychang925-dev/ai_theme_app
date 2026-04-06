#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.services.cycle_judgement_service import (
    CycleJudgementService,
    ThemeCycleMainlineInput,
    ThemeCycleMarketInput,
    ThemeCycleRecentInput,
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
    parser = argparse.ArgumentParser(description="构建 theme_cycle_judgement")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=10, help="近端题材序列回看天数")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS theme_cycle_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        theme_name VARCHAR(200) NOT NULL,
        is_main_theme BOOLEAN NOT NULL DEFAULT FALSE,
        is_start BOOLEAN NOT NULL DEFAULT FALSE,
        is_fermentation BOOLEAN NOT NULL DEFAULT FALSE,
        is_divergence BOOLEAN NOT NULL DEFAULT FALSE,
        is_rebound BOOLEAN NOT NULL DEFAULT FALSE,
        is_climax BOOLEAN NOT NULL DEFAULT FALSE,
        is_fade BOOLEAN NOT NULL DEFAULT FALSE,
        primary_cycle_stage VARCHAR(40) NOT NULL DEFAULT '',
        limit_up_count INTEGER NOT NULL DEFAULT 0,
        leader_status VARCHAR(80) NOT NULL DEFAULT '',
        board_effect_status VARCHAR(80) NOT NULL DEFAULT '',
        action_bias VARCHAR(80) NOT NULL DEFAULT '',
        confidence NUMERIC(6,2) NOT NULL DEFAULT 0,
        conclusion TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.cycle',
        source_trace_id VARCHAR(40) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_cycle_judgement UNIQUE (trade_date, subject_key)
    );
    CREATE INDEX IF NOT EXISTS idx_tcj_trade_date ON theme_cycle_judgement(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_tcj_stage_trade_date ON theme_cycle_judgement(primary_cycle_stage, trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute("ALTER TABLE theme_cycle_judgement ADD COLUMN IF NOT EXISTS source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.cycle'")
        await conn.execute("ALTER TABLE theme_cycle_judgement ADD COLUMN IF NOT EXISTS source_trace_id VARCHAR(40) NOT NULL DEFAULT ''")
        await conn.execute("ALTER TABLE theme_cycle_judgement ADD COLUMN IF NOT EXISTS source_trace JSONB NOT NULL DEFAULT '{}'::jsonb")
        await conn.execute("ALTER TABLE theme_cycle_judgement ADD COLUMN IF NOT EXISTS source_version VARCHAR(80) NOT NULL DEFAULT ''")
        await conn.execute("ALTER TABLE theme_cycle_judgement ADD COLUMN IF NOT EXISTS rule_version VARCHAR(80) NOT NULL DEFAULT ''")


async def fetch_mainline_rows(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        subject_key,
        theme_name,
        is_main_theme,
        theme_tier,
        event_chain_score,
        event_chain_continuity_score,
        market_recognition_score,
        mainline_stability_score,
        limit_up_count
    FROM theme_mainline_judgement
    WHERE trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_market_rows(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
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
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_recent_rows(manager: PostgresDatabaseManager, trade_date_value: date, lookback_days: int):
    start_date = trade_date_value - timedelta(days=max(lookback_days, 1))
    sql = """
    SELECT
        subject_key,
        rank_date,
        pct_chg,
        his_pct_chg,
        red
    FROM subject_rank_daily
    WHERE rank_date >= $1
      AND rank_date < $2
    ORDER BY subject_key, rank_date DESC
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, start_date, trade_date_value)
    return [dict(r) for r in rows]


def build_recent_map(rows: list[dict]) -> dict[str, ThemeCycleRecentInput]:
    grouped: dict[str, dict] = defaultdict(lambda: {"days": 0, "positive": 0, "red": 0, "negative": 0})
    for row in rows:
        subject_key = str(row.get("subject_key") or "")
        if not subject_key:
            continue
        bucket = grouped[subject_key]
        bucket["days"] += 1
        his_pct = float(row.get("his_pct_chg") or 0)
        if his_pct > 0:
            bucket["positive"] += 1
        if his_pct < 0:
            bucket["negative"] += 1
        if bool(row.get("red")):
            bucket["red"] += 1

    return {
        subject_key: ThemeCycleRecentInput(
            subject_key=subject_key,
            recent_rank_days=stats["days"],
            recent_positive_days=stats["positive"],
            recent_red_days=stats["red"],
            recent_negative_days=stats["negative"],
        )
        for subject_key, stats in grouped.items()
    }


async def upsert_rows(manager: PostgresDatabaseManager, judgements):
    sql = """
    INSERT INTO theme_cycle_judgement (
        trade_date, subject_key, theme_name, is_main_theme,
        is_start, is_fermentation, is_divergence, is_rebound, is_climax, is_fade,
        primary_cycle_stage, limit_up_count, leader_status, board_effect_status,
        action_bias, confidence, conclusion, evidence,
        source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4,
        $5, $6, $7, $8, $9, $10,
        $11, $12, $13, $14,
        $15, $16, $17, $18::jsonb,
        $19, $20, $21::jsonb, $22, $23
    )
    ON CONFLICT (trade_date, subject_key)
    DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        is_main_theme = EXCLUDED.is_main_theme,
        is_start = EXCLUDED.is_start,
        is_fermentation = EXCLUDED.is_fermentation,
        is_divergence = EXCLUDED.is_divergence,
        is_rebound = EXCLUDED.is_rebound,
        is_climax = EXCLUDED.is_climax,
        is_fade = EXCLUDED.is_fade,
        primary_cycle_stage = EXCLUDED.primary_cycle_stage,
        limit_up_count = EXCLUDED.limit_up_count,
        leader_status = EXCLUDED.leader_status,
        board_effect_status = EXCLUDED.board_effect_status,
        action_bias = EXCLUDED.action_bias,
        confidence = EXCLUDED.confidence,
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
            item.is_main_theme,
            item.is_start,
            item.is_fermentation,
            item.is_divergence,
            item.is_rebound,
            item.is_climax,
            item.is_fade,
            item.primary_cycle_stage,
            item.limit_up_count,
            item.leader_status,
            item.board_effect_status,
            item.action_bias,
            item.confidence,
            item.conclusion,
            json.dumps(item.evidence, ensure_ascii=False),
            item.source_type,
            item.source_trace_id,
            json.dumps(item.source_trace, ensure_ascii=False),
            item.source_version,
            item.rule_version,
        )
        for item in judgements
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
        mainline_rows = await fetch_mainline_rows(manager, trade_date_value)
        market_rows = await fetch_market_rows(manager, trade_date_value)
        recent_rows = await fetch_recent_rows(manager, trade_date_value, args.lookback_days)

        mainline_map = {
            str(row["subject_key"]): ThemeCycleMainlineInput(
                subject_key=str(row["subject_key"]),
                theme_name=row["theme_name"],
                is_main_theme=bool(row["is_main_theme"]),
                theme_tier=row["theme_tier"],
                event_chain_score=float(row["event_chain_score"] or 0),
                event_chain_continuity_score=float(row["event_chain_continuity_score"] or 0),
                market_recognition_score=float(row["market_recognition_score"] or 0),
                mainline_stability_score=float(row["mainline_stability_score"] or 0),
                limit_up_count=int(row["limit_up_count"] or 0),
            )
            for row in mainline_rows
        }
        market_map = {
            str(row["subject_key"]): ThemeCycleMarketInput(
                subject_key=str(row["subject_key"]),
                theme_name=row["theme_name"],
                limit_up_count=int(row["limit_up_count"] or 0),
                strong_stock_count=int(row["strong_stock_count"] or 0),
                leader_pct_chg=float(row["leader_pct_chg"] or 0),
                member_count=int(row["member_count"] or 0),
                leader_limit_up=bool(row["leader_limit_up"]),
            )
            for row in market_rows
        }
        recent_map = build_recent_map(recent_rows)

        service = CycleJudgementService()
        judgements = []
        for subject_key in sorted(mainline_map.keys()):
            mainline = mainline_map[subject_key]
            market = market_map.get(
                subject_key,
                ThemeCycleMarketInput(
                    subject_key=subject_key,
                    theme_name=mainline.theme_name,
                    limit_up_count=mainline.limit_up_count,
                    strong_stock_count=0,
                    leader_pct_chg=0.0,
                    member_count=0,
                    leader_limit_up=False,
                ),
            )
            recent = recent_map.get(
                subject_key,
                ThemeCycleRecentInput(
                    subject_key=subject_key,
                    recent_rank_days=0,
                    recent_positive_days=0,
                    recent_red_days=0,
                    recent_negative_days=0,
                ),
            )
            judgement = service.build_judgement(args.trade_date, mainline, market, recent)
            source_trace = {
                "datasets": [
                    "theme_mainline_judgement",
                    "subject_stock_daily_snapshot",
                    "subject_rank_daily",
                ],
                "trade_date": args.trade_date,
                "subject_key": subject_key,
                "limit_up_count": market.limit_up_count,
                "strong_stock_count": market.strong_stock_count,
                "leader_pct_chg": market.leader_pct_chg,
                "recent_rank_days": recent.recent_rank_days,
            }
            source_trace_id = hashlib.md5(
                f"cycle|{args.trade_date}|{subject_key}|{market.limit_up_count}|{market.strong_stock_count}|{recent.recent_rank_days}".encode("utf-8")
            ).hexdigest()[:16]
            judgements.append(
                type(judgement)(
                    **{
                        **judgement.__dict__,
                        "source_trace_id": source_trace_id,
                        "source_trace": source_trace,
                    }
                )
            )

        await upsert_rows(manager, judgements)

        ranked = sorted(
            judgements,
            key=lambda item: (
                0 if item.is_main_theme else 1,
                0 if item.primary_cycle_stage in ("fermentation", "rebound") else 1 if item.primary_cycle_stage == "start" else 2,
                -item.confidence,
                item.subject_key,
            ),
        )
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] rows={len(judgements)}")
        print(f"[OK] start={sum(1 for x in judgements if x.is_start)}")
        print(f"[OK] fermentation={sum(1 for x in judgements if x.is_fermentation)}")
        print(f"[OK] divergence={sum(1 for x in judgements if x.is_divergence)}")
        print(f"[OK] rebound={sum(1 for x in judgements if x.is_rebound)}")
        print(f"[OK] climax={sum(1 for x in judgements if x.is_climax)}")
        print(f"[OK] fade={sum(1 for x in judgements if x.is_fade)}")
        for item in ranked[: args.top_k]:
            print(
                f"[ROW] stage={item.primary_cycle_stage} bias={item.action_bias} "
                f"theme={item.theme_name} main={item.is_main_theme} "
                f"limit_up={item.limit_up_count} confidence={item.confidence:.2f} "
                f"leader={item.leader_status} board={item.board_effect_status}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

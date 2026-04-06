#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.services.mainline_judgement_service import (
    MainlineJudgementService,
    ThemeEventStats,
    ThemeMarketStats,
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
    parser = argparse.ArgumentParser(description="构建 theme_mainline_judgement")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--lookback-days", type=int, default=7, help="事件连续性回看天数")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS theme_mainline_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        theme_name VARCHAR(200) NOT NULL,
        event_chain_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        event_chain_continuity_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        market_recognition_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        mainline_stability_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        is_main_theme BOOLEAN NOT NULL DEFAULT FALSE,
        theme_tier VARCHAR(40) NOT NULL,
        limit_up_count INTEGER NOT NULL DEFAULT 0,
        evidence_logic JSONB NOT NULL DEFAULT '[]'::jsonb,
        evidence_market JSONB NOT NULL DEFAULT '[]'::jsonb,
        conclusion TEXT NOT NULL DEFAULT '',
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.mainline',
        source_trace_id VARCHAR(40) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_mainline_judgement UNIQUE (trade_date, subject_key)
    );
    CREATE INDEX IF NOT EXISTS idx_tmj_trade_date ON theme_mainline_judgement(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_tmj_tier_trade_date ON theme_mainline_judgement(theme_tier, trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute("ALTER TABLE theme_mainline_judgement ADD COLUMN IF NOT EXISTS source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.mainline'")
        await conn.execute("ALTER TABLE theme_mainline_judgement ADD COLUMN IF NOT EXISTS source_trace_id VARCHAR(40) NOT NULL DEFAULT ''")
        await conn.execute("ALTER TABLE theme_mainline_judgement ADD COLUMN IF NOT EXISTS source_trace JSONB NOT NULL DEFAULT '{}'::jsonb")
        await conn.execute("ALTER TABLE theme_mainline_judgement ADD COLUMN IF NOT EXISTS source_version VARCHAR(80) NOT NULL DEFAULT ''")
        await conn.execute("ALTER TABLE theme_mainline_judgement ADD COLUMN IF NOT EXISTS rule_version VARCHAR(80) NOT NULL DEFAULT ''")


async def fetch_event_rows(manager: PostgresDatabaseManager, trade_date_value: date, start_date: date):
    sql = """
    SELECT
        tm.source_id AS subject_key,
        tm.name AS theme_name,
        ne.event_time::date AS event_date,
        COALESCE(ne.summary, '') AS summary
    FROM news_event ne
    JOIN event_theme_map etm
      ON etm.event_id = ne.id
    JOIN theme_master tm
      ON tm.id = etm.theme_id
    WHERE ne.theme_directive->>'jyhf_source_type' = 'jyhf_history'
      AND tm.source_system = 'jyhf'
      AND tm.source_id IS NOT NULL
      AND ne.event_time::date BETWEEN $1 AND $2
    ORDER BY ne.event_time DESC, ne.id DESC
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, start_date, trade_date_value)
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


def build_event_stats(rows: list[dict], trade_date_value: date) -> dict[str, ThemeEventStats]:
    grouped: dict[str, dict] = defaultdict(lambda: {"theme_name": "", "today": 0, "recent": 0, "days": set(), "summaries": []})
    service = MainlineJudgementService()
    for row in rows:
        subject_key = str(row.get("subject_key") or "")
        if not subject_key:
            continue
        bucket = grouped[subject_key]
        bucket["theme_name"] = row.get("theme_name") or bucket["theme_name"] or subject_key
        bucket["recent"] += 1
        event_date = row.get("event_date")
        if event_date == trade_date_value:
            bucket["today"] += 1
        if event_date:
            bucket["days"].add(event_date)
        summary = str(row.get("summary") or "").strip()
        if summary:
            bucket["summaries"].append(summary.splitlines()[0])

    results = {}
    for subject_key, item in grouped.items():
        summaries = item["summaries"]
        results[subject_key] = ThemeEventStats(
            subject_key=subject_key,
            theme_name=item["theme_name"],
            today_event_count=item["today"],
            recent_event_count=item["recent"],
            distinct_event_days=len(item["days"]),
            key_event_count=service.count_key_events(summaries),
            sample_summaries=summaries[:5],
        )
    return results


def build_market_stats(rows: list[dict]) -> dict[str, ThemeMarketStats]:
    results = {}
    for row in rows:
        subject_key = str(row.get("subject_key") or "")
        if not subject_key:
            continue
        results[subject_key] = ThemeMarketStats(
            subject_key=subject_key,
            theme_name=row.get("theme_name") or subject_key,
            limit_up_count=int(row.get("limit_up_count") or 0),
            strong_stock_count=int(row.get("strong_stock_count") or 0),
            leader_pct_chg=float(row.get("leader_pct_chg") or 0),
            member_count=int(row.get("member_count") or 0),
            leader_limit_up=bool(row.get("leader_limit_up")),
        )
    return results


async def upsert_rows(manager: PostgresDatabaseManager, judgements):
    sql = """
    INSERT INTO theme_mainline_judgement (
        trade_date, subject_key, theme_name,
        event_chain_score, event_chain_continuity_score,
        market_recognition_score, mainline_stability_score,
        is_main_theme, theme_tier, limit_up_count,
        evidence_logic, evidence_market, conclusion,
        source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3,
        $4, $5,
        $6, $7,
        $8, $9, $10,
        $11::jsonb, $12::jsonb, $13,
        $14, $15, $16::jsonb, $17, $18
    )
    ON CONFLICT (trade_date, subject_key)
    DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        event_chain_score = EXCLUDED.event_chain_score,
        event_chain_continuity_score = EXCLUDED.event_chain_continuity_score,
        market_recognition_score = EXCLUDED.market_recognition_score,
        mainline_stability_score = EXCLUDED.mainline_stability_score,
        is_main_theme = EXCLUDED.is_main_theme,
        theme_tier = EXCLUDED.theme_tier,
        limit_up_count = EXCLUDED.limit_up_count,
        evidence_logic = EXCLUDED.evidence_logic,
        evidence_market = EXCLUDED.evidence_market,
        conclusion = EXCLUDED.conclusion,
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
            item.event_chain_score,
            item.event_chain_continuity_score,
            item.market_recognition_score,
            item.mainline_stability_score,
            item.is_main_theme,
            item.theme_tier,
            item.limit_up_count,
            json.dumps(item.evidence_logic, ensure_ascii=False),
            json.dumps(item.evidence_market, ensure_ascii=False),
            item.conclusion,
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
    start_date = trade_date_value - timedelta(days=max(args.lookback_days - 1, 0))

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        event_rows = await fetch_event_rows(manager, trade_date_value, start_date)
        market_rows = await fetch_market_rows(manager, trade_date_value)

        event_map = build_event_stats(event_rows, trade_date_value)
        market_map = build_market_stats(market_rows)
        service = MainlineJudgementService()

        judgements = []
        for subject_key in sorted(set(event_map.keys()) | set(market_map.keys())):
            event_stats = event_map.get(
                subject_key,
                ThemeEventStats(
                    subject_key=subject_key,
                    theme_name=market_map.get(subject_key).theme_name if subject_key in market_map else subject_key,
                    today_event_count=0,
                    recent_event_count=0,
                    distinct_event_days=0,
                    key_event_count=0,
                    sample_summaries=[],
                ),
            )
            market_stats = market_map.get(
                subject_key,
                ThemeMarketStats(
                    subject_key=subject_key,
                    theme_name=event_stats.theme_name,
                    limit_up_count=0,
                    strong_stock_count=0,
                    leader_pct_chg=0.0,
                    member_count=0,
                    leader_limit_up=False,
                ),
            )
            judgement = service.build_judgement(args.trade_date, event_stats, market_stats)
            source_trace = {
                "datasets": [
                    "news_event.event_theme_map.jyhf_history",
                    "subject_stock_daily_snapshot",
                ],
                "trade_date": args.trade_date,
                "subject_key": subject_key,
                "today_event_count": event_stats.today_event_count,
                "recent_event_count": event_stats.recent_event_count,
                "distinct_event_days": event_stats.distinct_event_days,
                "limit_up_count": market_stats.limit_up_count,
                "strong_stock_count": market_stats.strong_stock_count,
            }
            source_trace_id = hashlib.md5(
                f"mainline|{args.trade_date}|{subject_key}|{event_stats.today_event_count}|{event_stats.recent_event_count}|{market_stats.limit_up_count}".encode("utf-8")
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
                0 if item.theme_tier == "main" else 1 if item.theme_tier == "strong_branch" else 2,
                -(item.event_chain_score + item.market_recognition_score + item.mainline_stability_score),
                item.subject_key,
            ),
        )
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] rows={len(judgements)}")
        print(f"[OK] main={sum(1 for x in judgements if x.theme_tier == 'main')}")
        print(f"[OK] strong_branch={sum(1 for x in judgements if x.theme_tier == 'strong_branch')}")
        print(f"[OK] failed={sum(1 for x in judgements if x.theme_tier == 'failed')}")
        for item in ranked[: args.top_k]:
            print(
                f"[ROW] tier={item.theme_tier} theme={item.theme_name} "
                f"event={item.event_chain_score:.2f} continuity={item.event_chain_continuity_score:.2f} "
                f"market={item.market_recognition_score:.2f} stability={item.mainline_stability_score:.2f} "
                f"limit_up={item.limit_up_count}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

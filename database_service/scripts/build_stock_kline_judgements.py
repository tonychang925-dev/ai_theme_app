#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.adapters.jyhf_adapter import JyhfAdapter
from stock_service.models import StockDailySnapshot
from stock_service.services.stock_kline_judgement_service import StockKlineJudgementService


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
    parser = argparse.ArgumentParser(description="基于本地 Tushare K 线文件构建个股位置/形态判断")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 只")
    parser.add_argument("--data-root", default=str(PROJECT_ROOT / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar"))
    return parser.parse_args()


def _to_date(value: str):
    return datetime.strptime(value, "%Y-%m-%d").date()


def build_jyhf_current_bar_map(trade_date: str) -> dict[str, StockDailySnapshot]:
    adapter = JyhfAdapter(PROJECT_ROOT)
    result: dict[str, StockDailySnapshot] = {}
    for row in adapter.iter_stock_daily_rows(trade_date):
        stock_id = str(row.get("stock_id") or "").strip().upper()
        if not stock_id or stock_id in result:
            continue
        result[stock_id] = StockDailySnapshot(
            trade_date=trade_date,
            stock_id=stock_id,
            stock_name=row.get("stock_name"),
            open_price=row.get("open_price"),
            high_price=row.get("high_price"),
            low_price=row.get("low_price"),
            close_price=row.get("close_price"),
            pre_close=row.get("pre_close"),
            pct_chg=row.get("pct_chg"),
            volume=row.get("volume"),
            amount=row.get("amount"),
            source_name="jyhf",
        )
    return result


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    sql = """
    CREATE TABLE IF NOT EXISTS stock_position_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100) NOT NULL,
        position_label VARCHAR(40) NOT NULL,
        distance_to_20d_high NUMERIC(12,6) NOT NULL DEFAULT 0,
        distance_to_60d_high NUMERIC(12,6) NOT NULL DEFAULT 0,
        distance_to_120d_high NUMERIC(12,6) NOT NULL DEFAULT 0,
        distance_to_all_time_high NUMERIC(12,6) NOT NULL DEFAULT 0,
        ma_alignment_status VARCHAR(40) NOT NULL DEFAULT '',
        trend_strength_score NUMERIC(12,4) NOT NULL DEFAULT 0,
        conclusion TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase3.stock_position',
        source_trace_id VARCHAR(80) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT 'stock_position_judgement.v1',
        rule_version VARCHAR(80) NOT NULL DEFAULT 'stock_position_judgement.v1',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_stock_position_judgement UNIQUE (trade_date, stock_id)
    );
    CREATE TABLE IF NOT EXISTS stock_pattern_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100) NOT NULL,
        pattern_labels JSONB NOT NULL DEFAULT '[]'::jsonb,
        volume_pattern_status VARCHAR(40) NOT NULL DEFAULT '',
        breakout_status VARCHAR(40) NOT NULL DEFAULT '',
        pullback_status VARCHAR(40) NOT NULL DEFAULT '',
        risk_pattern_status VARCHAR(40) NOT NULL DEFAULT '',
        conclusion TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase3.stock_pattern',
        source_trace_id VARCHAR(80) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT 'stock_pattern_judgement.v1',
        rule_version VARCHAR(80) NOT NULL DEFAULT 'stock_pattern_judgement.v1',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_stock_pattern_judgement UNIQUE (trade_date, stock_id)
    );
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(sql)


async def main_async() -> int:
    args = parse_args()
    service = StockKlineJudgementService()
    data_root = Path(args.data_root)
    files = sorted(data_root.glob("*.jsonl"))
    jyhf_current_bar_map = build_jyhf_current_bar_map(args.trade_date)

    position_rows = []
    pattern_rows = []
    matched_files = []
    for path in files:
        rows = service.load_stock_bars(path)
        rows = [row for row in rows if row.trade_date <= args.trade_date]
        if not rows:
            continue
        latest = rows[-1]
        if latest.trade_date != args.trade_date:
            fallback_row = jyhf_current_bar_map.get(str(latest.stock_id).strip().upper())
            if fallback_row:
                rows.append(fallback_row)
                rows = sorted(rows, key=lambda item: item.trade_date)
        if rows[-1].trade_date != args.trade_date:
            continue
        matched_files.append(path)
        if args.limit and len(matched_files) > args.limit:
            break
        position = service.build_position_judgement(rows)
        pattern = service.build_pattern_judgement(rows)
        if position:
            position_rows.append(position)
        if pattern:
            pattern_rows.append(pattern)

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_tables(manager)
        async with manager.pool.acquire() as conn:
            if position_rows:
                await conn.executemany(
                    """
                    INSERT INTO stock_position_judgement (
                        trade_date, stock_id, stock_name, position_label,
                        distance_to_20d_high, distance_to_60d_high, distance_to_120d_high, distance_to_all_time_high,
                        ma_alignment_status, trend_strength_score, conclusion, evidence,
                        source_type, source_trace_id, source_trace, source_version, rule_version
                    ) VALUES (
                        $1, $2, $3, $4,
                        $5, $6, $7, $8,
                        $9, $10, $11, $12::jsonb,
                        $13, $14, $15::jsonb, $16, $17
                    )
                    ON CONFLICT (trade_date, stock_id) DO UPDATE SET
                        stock_name=EXCLUDED.stock_name,
                        position_label=EXCLUDED.position_label,
                        distance_to_20d_high=EXCLUDED.distance_to_20d_high,
                        distance_to_60d_high=EXCLUDED.distance_to_60d_high,
                        distance_to_120d_high=EXCLUDED.distance_to_120d_high,
                        distance_to_all_time_high=EXCLUDED.distance_to_all_time_high,
                        ma_alignment_status=EXCLUDED.ma_alignment_status,
                        trend_strength_score=EXCLUDED.trend_strength_score,
                        conclusion=EXCLUDED.conclusion,
                        evidence=EXCLUDED.evidence,
                        source_type=EXCLUDED.source_type,
                        source_trace_id=EXCLUDED.source_trace_id,
                        source_trace=EXCLUDED.source_trace,
                        source_version=EXCLUDED.source_version,
                        rule_version=EXCLUDED.rule_version,
                        updated_at=NOW()
                    """,
                    [
                        (
                            _to_date(item.trade_date),
                            item.stock_id,
                            item.stock_name,
                            item.position_label,
                            item.distance_to_20d_high,
                            item.distance_to_60d_high,
                            item.distance_to_120d_high,
                            item.distance_to_all_time_high,
                            item.ma_alignment_status,
                            item.trend_strength_score,
                            item.conclusion,
                            json.dumps(item.evidence, ensure_ascii=False),
                            item.source_type,
                            item.source_trace_id,
                            json.dumps(item.source_trace, ensure_ascii=False),
                            item.source_version,
                            item.rule_version,
                        )
                        for item in position_rows
                    ],
                )
            if pattern_rows:
                await conn.executemany(
                    """
                    INSERT INTO stock_pattern_judgement (
                        trade_date, stock_id, stock_name, pattern_labels,
                        volume_pattern_status, breakout_status, pullback_status, risk_pattern_status,
                        conclusion, evidence, source_type, source_trace_id, source_trace, source_version, rule_version
                    ) VALUES (
                        $1, $2, $3, $4::jsonb,
                        $5, $6, $7, $8,
                        $9, $10::jsonb, $11, $12, $13::jsonb, $14, $15
                    )
                    ON CONFLICT (trade_date, stock_id) DO UPDATE SET
                        stock_name=EXCLUDED.stock_name,
                        pattern_labels=EXCLUDED.pattern_labels,
                        volume_pattern_status=EXCLUDED.volume_pattern_status,
                        breakout_status=EXCLUDED.breakout_status,
                        pullback_status=EXCLUDED.pullback_status,
                        risk_pattern_status=EXCLUDED.risk_pattern_status,
                        conclusion=EXCLUDED.conclusion,
                        evidence=EXCLUDED.evidence,
                        source_type=EXCLUDED.source_type,
                        source_trace_id=EXCLUDED.source_trace_id,
                        source_trace=EXCLUDED.source_trace,
                        source_version=EXCLUDED.source_version,
                        rule_version=EXCLUDED.rule_version,
                        updated_at=NOW()
                    """,
                    [
                        (
                            _to_date(item.trade_date),
                            item.stock_id,
                            item.stock_name,
                            json.dumps(item.pattern_labels, ensure_ascii=False),
                            item.volume_pattern_status,
                            item.breakout_status,
                            item.pullback_status,
                            item.risk_pattern_status,
                            item.conclusion,
                            json.dumps(item.evidence, ensure_ascii=False),
                            item.source_type,
                            item.source_trace_id,
                            json.dumps(item.source_trace, ensure_ascii=False),
                            item.source_version,
                            item.rule_version,
                        )
                        for item in pattern_rows
                    ],
                )
    finally:
        await manager.disconnect()

    print(f"[OK] trade_date={args.trade_date}")
    print(f"[OK] matched_files={len(matched_files)}")
    print(f"[OK] position_rows={len(position_rows)}")
    print(f"[OK] pattern_rows={len(pattern_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

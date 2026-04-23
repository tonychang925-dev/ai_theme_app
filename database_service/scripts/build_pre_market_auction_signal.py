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
from stock_service.services.auction_signal_service import AuctionCandidateInput, AuctionSignalService
from stock_service.models import PreMarketAuctionSnapshot


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
    parser = argparse.ArgumentParser(description="构建 pre_market_auction_signal")
    parser.add_argument("--trade-date", required=True, help="目标交易日 YYYY-MM-DD")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _coerce_json_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return list(value) if hasattr(value, "__iter__") else []


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS pre_market_auction_signal (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        stock_id TEXT NOT NULL,
        stock_name TEXT NOT NULL DEFAULT '',
        subject_key TEXT NOT NULL DEFAULT '',
        theme_name TEXT NOT NULL DEFAULT '',
        role_label TEXT NOT NULL DEFAULT '',
        auction_signal_score NUMERIC(8,4) NOT NULL DEFAULT 0,
        auction_signal_level TEXT NOT NULL DEFAULT '',
        signal_type TEXT NOT NULL DEFAULT '',
        leader_status TEXT NOT NULL DEFAULT '',
        action_today TEXT NOT NULL DEFAULT '',
        hard_reject_reason TEXT NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type TEXT NOT NULL DEFAULT 'p3.phase3.auction_signal',
        source_trace_id TEXT NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version TEXT NOT NULL DEFAULT 'auction_signal.v1',
        rule_version TEXT NOT NULL DEFAULT 'auction_signal.v1',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_pre_market_auction_signal UNIQUE (trade_date, stock_id)
    );
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute(
            "ALTER TABLE pre_market_auction_signal ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
        )


async def fetch_snapshots(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT *
    FROM pre_market_auction_snapshot
    WHERE trade_date = $1
    ORDER BY theme_name, stock_id
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_watch_universe(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        u.stock_id,
        u.subject_key,
        u.theme_name,
        u.role_label,
        u.mainline_alive,
        u.action_bias,
        u.is_reversal_watch,
        COALESCE(p.position_label, '') AS position_label,
        COALESCE(x.pattern_labels, '[]'::jsonb) AS pattern_labels
    FROM auction_watch_universe u
    LEFT JOIN stock_position_judgement p
      ON p.trade_date = u.source_trade_date
     AND split_part(p.stock_id, '.', 1) = split_part(u.stock_id, '.', 1)
    LEFT JOIN stock_pattern_judgement x
      ON x.trade_date = u.source_trade_date
     AND split_part(x.stock_id, '.', 1) = split_part(u.stock_id, '.', 1)
    WHERE u.trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    result = {}
    for row in rows:
        item = dict(row)
        if isinstance(item.get("pattern_labels"), str):
            try:
                item["pattern_labels"] = json.loads(item["pattern_labels"])
            except Exception:
                item["pattern_labels"] = []
        result[(str(row["stock_id"]).upper(), str(row["subject_key"]))] = item
    return result


async def upsert_rows(manager: PostgresDatabaseManager, items):
    sql = """
    INSERT INTO pre_market_auction_signal (
        trade_date, stock_id, stock_name, subject_key, theme_name, role_label,
        auction_signal_score, auction_signal_level, signal_type, leader_status, action_today,
        hard_reject_reason, evidence, source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5, $6,
        $7, $8, $9, $10, $11,
        $12, $13::jsonb, $14, $15, $16::jsonb, $17, $18
    )
    ON CONFLICT (trade_date, stock_id)
    DO UPDATE SET
        stock_name = EXCLUDED.stock_name,
        subject_key = EXCLUDED.subject_key,
        theme_name = EXCLUDED.theme_name,
        role_label = EXCLUDED.role_label,
        auction_signal_score = EXCLUDED.auction_signal_score,
        auction_signal_level = EXCLUDED.auction_signal_level,
        signal_type = EXCLUDED.signal_type,
        leader_status = EXCLUDED.leader_status,
        action_today = EXCLUDED.action_today,
        hard_reject_reason = EXCLUDED.hard_reject_reason,
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
            item.stock_id,
            item.stock_name,
            item.subject_key,
            item.theme_name,
            item.role_label,
            item.auction_signal_score,
            item.auction_signal_level,
            item.signal_type,
            item.leader_status,
            item.action_today,
            item.hard_reject_reason,
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
        watch_map = await fetch_watch_universe(manager, trade_date_value)
        rows = await fetch_snapshots(manager, trade_date_value)
        service = AuctionSignalService()
        items = []
        for row in rows:
            key = (str(row["stock_id"]).upper(), str(row["subject_key"]))
            candidate_row = watch_map.get(key)
            if not candidate_row:
                continue
            snapshot = PreMarketAuctionSnapshot(
                trade_date=args.trade_date,
                stock_id=str(row["stock_id"]).upper(),
                stock_name=row["stock_name"],
                subject_key=str(row["subject_key"]),
                theme_name=row["theme_name"],
                role_label=row["role_label"],
                window_start_time=row["window_start_time"],
                window_end_time=row["window_end_time"],
                last_minute_start_time=row["last_minute_start_time"],
                last_30s_start_time=row["last_30s_start_time"],
                auction_open_price=float(row["auction_open_price"] or 0.0),
                pre_close=float(row["pre_close"] or 0.0),
                auction_open_pct=float(row["auction_open_pct"] or 0.0),
                auction_volume=float(row["auction_volume"] or 0.0),
                auction_amount=float(row["auction_amount"] or 0.0),
                last_minute_amount=float(row["last_minute_amount"] or 0.0),
                last_minute_ratio=float(row["last_minute_ratio"] or 0.0),
                prev_day_max_intraday_amount=float(row["prev_day_max_intraday_amount"] or 0.0),
                carry_ratio=float(row["carry_ratio"] or 0.0),
                price_path_stability_score=float(row["price_path_stability_score"] or 0.0),
                is_red_zone=bool(row["is_red_zone"]),
                has_end_spike=bool(row["has_end_spike"]),
                has_end_drop=bool(row["has_end_drop"]),
                shape_features=_coerce_json_list(row["shape_features"]),
                source_type=row["source_type"],
                source_trace_id=row["source_trace_id"],
                source_trace=row["source_trace"] or {},
                source_version=row["source_version"],
                rule_version=row["rule_version"],
            )
            candidate = AuctionCandidateInput(
                trade_date=args.trade_date,
                stock_id=str(candidate_row["stock_id"]).upper(),
                stock_name=row["stock_name"],
                subject_key=str(candidate_row["subject_key"]),
                theme_name=candidate_row["theme_name"],
                role_label=candidate_row["role_label"],
                mainline_alive=bool(candidate_row.get("mainline_alive")),
                action_bias=candidate_row["action_bias"],
                position_label=str(candidate_row.get("position_label") or ""),
                pattern_labels=tuple(str(x) for x in (candidate_row.get("pattern_labels") or [])),
                is_reversal_watch=bool(candidate_row["is_reversal_watch"]),
            )
            items.append(service.build_signal(snapshot, candidate))

        await upsert_rows(manager, items)
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] signal_rows={len(items)}")
        print(f"[OK] strong={sum(1 for x in items if x.auction_signal_level == 'strong')}")
        print(f"[OK] watch={sum(1 for x in items if x.auction_signal_level == 'watch')}")
        print(f"[OK] weak={sum(1 for x in items if x.auction_signal_level == 'weak')}")
        print(f"[OK] invalid={sum(1 for x in items if x.auction_signal_level == 'invalid')}")
        for item in items[: args.top_k]:
            print(
                f"[ROW] theme={item.theme_name} stock={item.stock_name} level={item.auction_signal_level} "
                f"type={item.signal_type} action={item.action_today} reject={item.hard_reject_reason or '--'}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

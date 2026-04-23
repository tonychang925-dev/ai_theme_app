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
from stock_service.services.leader_candidate_service import (
    LeaderCandidateService,
    ThemeLeaderInput,
)


DATA_ROOT = PROJECT_ROOT / "theme_data_complete" / "stock_daily"


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
    parser = argparse.ArgumentParser(description="构建 theme_leader_candidate")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--top-k", type=int, default=20, help="输出预览前 K 条")
    return parser.parse_args()


def _parse_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _to_float(value):
    if value in (None, "", "null"):
        return 0.0
    try:
        return float(value)
    except Exception:
        return 0.0


async def ensure_tables(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS theme_leader_candidate (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        theme_name VARCHAR(200) NOT NULL,
        stock_id VARCHAR(20) NOT NULL,
        stock_name VARCHAR(100) NOT NULL,
        purity_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        leading_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        capital_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        structure_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        resilience_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        composite_score NUMERIC(6,2) NOT NULL DEFAULT 0,
        is_limit_up BOOLEAN NOT NULL DEFAULT FALSE,
        limit_up_type VARCHAR(80) NOT NULL DEFAULT '',
        turnover_rate NUMERIC(8,2) NOT NULL DEFAULT 0,
        volume_ratio NUMERIC(8,2) NOT NULL DEFAULT 0,
        main_net_inflow NUMERIC(18,2) NOT NULL DEFAULT 0,
        is_new_stock BOOLEAN NOT NULL DEFAULT FALSE,
        candidate_rank INTEGER NOT NULL DEFAULT 0,
        role_label VARCHAR(40) NOT NULL DEFAULT '',
        evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
        source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.leader_candidate',
        source_trace_id VARCHAR(40) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(80) NOT NULL DEFAULT '',
        rule_version VARCHAR(80) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_leader_candidate UNIQUE (trade_date, subject_key, stock_id)
    );
    CREATE INDEX IF NOT EXISTS idx_tlc_trade_date ON theme_leader_candidate(trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_tlc_subject_date ON theme_leader_candidate(subject_key, trade_date DESC);
    CREATE INDEX IF NOT EXISTS idx_tlc_rank_date ON theme_leader_candidate(candidate_rank, trade_date DESC);
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute("ALTER TABLE theme_leader_candidate ADD COLUMN IF NOT EXISTS source_type VARCHAR(80) NOT NULL DEFAULT 'p3.phase2.leader_candidate'")
        await conn.execute("ALTER TABLE theme_leader_candidate ADD COLUMN IF NOT EXISTS source_trace_id VARCHAR(40) NOT NULL DEFAULT ''")
        await conn.execute("ALTER TABLE theme_leader_candidate ADD COLUMN IF NOT EXISTS source_trace JSONB NOT NULL DEFAULT '{}'::jsonb")
        await conn.execute("ALTER TABLE theme_leader_candidate ADD COLUMN IF NOT EXISTS source_version VARCHAR(80) NOT NULL DEFAULT ''")
        await conn.execute("ALTER TABLE theme_leader_candidate ADD COLUMN IF NOT EXISTS rule_version VARCHAR(80) NOT NULL DEFAULT ''")


async def fetch_main_themes(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        v2.subject_key,
        COALESCE(NULLIF(v2.theme_name, ''), NULLIF(e.theme_name, ''), v2.subject_key) AS theme_name
    FROM theme_cycle_judgement_v2 v2
    LEFT JOIN theme_cycle_evidence_daily e
      ON e.trade_date = v2.trade_date
     AND e.subject_key = v2.subject_key
    WHERE v2.trade_date = $1
      AND COALESCE(v2.final_mainline_alive, FALSE) = TRUE
      AND COALESCE(v2.fade_confirmed, FALSE) = FALSE
    ORDER BY
      COALESCE(v2.mainline_strength_score, 0) DESC,
      v2.subject_key
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    return [dict(r) for r in rows]


async def fetch_subject_rows(manager: PostgresDatabaseManager, trade_date_value: date, subject_keys: list[str]):
    sql = """
    SELECT
        subject_key,
        stock_id,
        stock_name,
        rank_order,
        COALESCE(pct_chg, 0) AS pct_chg,
        COALESCE(close_price, 0) AS close_price,
        is_leader,
        limit_up
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $1
      AND subject_key = ANY($2::varchar[])
    ORDER BY subject_key, rank_order ASC
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value, subject_keys)
    return [dict(r) for r in rows]


async def fetch_kline_fact_map(manager: PostgresDatabaseManager, trade_date_value: date):
    sql = """
    SELECT
        split_part(p.stock_id, '.', 1) AS stock_code,
        p.position_label,
        p.trend_strength_score,
        COALESCE(x.pattern_labels, '[]'::jsonb) AS pattern_labels
    FROM stock_position_judgement p
    LEFT JOIN stock_pattern_judgement x
      ON x.trade_date = p.trade_date
     AND x.stock_id = p.stock_id
    WHERE p.trade_date = $1
    """
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value)
    result = {}
    for row in rows:
        item = dict(row)
        pattern_labels = item.get("pattern_labels")
        if isinstance(pattern_labels, str):
            try:
                pattern_labels = json.loads(pattern_labels)
            except Exception:
                pattern_labels = []
        result[str(item["stock_code"])] = {
            "position_label": item.get("position_label") or "",
            "trend_strength_score": float(item.get("trend_strength_score") or 0),
            "pattern_labels": tuple(str(x) for x in (pattern_labels or [])),
        }
    return result


def load_raw_fact_map(trade_date: str, subject_keys: list[str]) -> dict[tuple[str, str], dict]:
    result: dict[tuple[str, str], dict] = {}
    trade_date_value = _parse_trade_date(trade_date)
    for subject_key in subject_keys:
        path = DATA_ROOT / f"{subject_key}_{trade_date}_stocks.jsonl"
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if not isinstance(row, list) or len(row) < 19:
                    continue
                stock_id = str(row[2]).strip()
                if not stock_id:
                    continue
                list_date = None
                if len(row) > 25 and row[25]:
                    try:
                        list_date = datetime.strptime(str(row[25]).split(" ")[0], "%Y-%m-%d").date()
                    except Exception:
                        list_date = None
                is_new_stock = bool(list_date and (trade_date_value - list_date).days <= 365)
                result[(subject_key, stock_id)] = {
                    "volume_ratio": _to_float(row[17] if len(row) > 17 else None),
                    "turnover_rate": _to_float(row[18] if len(row) > 18 else None),
                    "main_net_inflow": _to_float(row[35] if len(row) > 35 else None),
                    "is_new_stock": is_new_stock,
                }
    return result


async def upsert_rows(manager: PostgresDatabaseManager, candidates):
    sql = """
    INSERT INTO theme_leader_candidate (
        trade_date, subject_key, theme_name, stock_id, stock_name,
        purity_score, leading_score, capital_score, structure_score, resilience_score,
        composite_score, is_limit_up, limit_up_type, turnover_rate, volume_ratio,
        main_net_inflow, is_new_stock, candidate_rank, role_label, evidence
        , source_type, source_trace_id, source_trace, source_version, rule_version
    ) VALUES (
        $1, $2, $3, $4, $5,
        $6, $7, $8, $9, $10,
        $11, $12, $13, $14, $15,
        $16, $17, $18, $19, $20::jsonb,
        $21, $22, $23::jsonb, $24, $25
    )
    ON CONFLICT (trade_date, subject_key, stock_id)
    DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        stock_name = EXCLUDED.stock_name,
        purity_score = EXCLUDED.purity_score,
        leading_score = EXCLUDED.leading_score,
        capital_score = EXCLUDED.capital_score,
        structure_score = EXCLUDED.structure_score,
        resilience_score = EXCLUDED.resilience_score,
        composite_score = EXCLUDED.composite_score,
        is_limit_up = EXCLUDED.is_limit_up,
        limit_up_type = EXCLUDED.limit_up_type,
        turnover_rate = EXCLUDED.turnover_rate,
        volume_ratio = EXCLUDED.volume_ratio,
        main_net_inflow = EXCLUDED.main_net_inflow,
        is_new_stock = EXCLUDED.is_new_stock,
        candidate_rank = EXCLUDED.candidate_rank,
        role_label = EXCLUDED.role_label,
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
            item.stock_id,
            item.stock_name,
            item.purity_score,
            item.leading_score,
            item.capital_score,
            item.structure_score,
            item.resilience_score,
            item.composite_score,
            item.is_limit_up,
            item.limit_up_type,
            item.turnover_rate,
            item.volume_ratio,
            item.main_net_inflow,
            item.is_new_stock,
            item.candidate_rank,
            item.role_label,
            json.dumps(item.evidence, ensure_ascii=False),
            item.source_type,
            item.source_trace_id,
            json.dumps(item.source_trace, ensure_ascii=False),
            item.source_version,
            item.rule_version,
        )
        for item in candidates
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
        main_themes = await fetch_main_themes(manager, trade_date_value)
        subject_keys = [str(row["subject_key"]) for row in main_themes]
        subject_rows = await fetch_subject_rows(manager, trade_date_value, subject_keys) if subject_keys else []
        raw_fact_map = load_raw_fact_map(args.trade_date, subject_keys)
        kline_fact_map = await fetch_kline_fact_map(manager, trade_date_value)

        theme_name_map = {str(row["subject_key"]): row["theme_name"] for row in main_themes}
        grouped: dict[str, list[ThemeLeaderInput]] = {}
        for row in subject_rows:
            subject_key = str(row["subject_key"])
            stock_key = (subject_key, str(row["stock_id"]))
            raw = raw_fact_map.get(stock_key, {})
            kline = kline_fact_map.get(str(row["stock_id"]).split(".")[0], {})
            grouped.setdefault(subject_key, []).append(
                ThemeLeaderInput(
                    trade_date=args.trade_date,
                    subject_key=subject_key,
                    theme_name=theme_name_map.get(subject_key, subject_key),
                    stock_id=str(row["stock_id"]),
                    stock_name=row["stock_name"],
                    rank_order=int(row["rank_order"] or 0),
                    pct_chg=float(row["pct_chg"] or 0),
                    is_leader=bool(row["is_leader"]),
                    is_limit_up=bool(row["limit_up"]),
                    turnover_rate=float(raw.get("turnover_rate") or 0),
                    volume_ratio=float(raw.get("volume_ratio") or 0),
                    main_net_inflow=float(raw.get("main_net_inflow") or 0),
                    is_new_stock=bool(raw.get("is_new_stock")),
                    close_price=float(row["close_price"] or 0),
                    position_label=str(kline.get("position_label") or ""),
                    trend_strength_score=float(kline.get("trend_strength_score") or 0),
                    pattern_labels=tuple(kline.get("pattern_labels") or ()),
                )
            )

        service = LeaderCandidateService()
        candidates = []
        for subject_key, rows in grouped.items():
            built = service.build_theme_candidates(rows)
            for item in built:
                source_trace = {
                    "datasets": [
                        "theme_cycle_judgement_v2",
                        "theme_cycle_evidence_daily",
                        "subject_stock_daily_snapshot",
                        "theme_data_complete.stock_daily",
                        "stock_position_judgement",
                        "stock_pattern_judgement",
                    ],
                    "trade_date": args.trade_date,
                    "subject_key": subject_key,
                    "stock_id": item.stock_id,
                    "candidate_rank": item.candidate_rank,
                    "rank_order": next((row.rank_order for row in rows if row.stock_id == item.stock_id), 0),
                }
                source_trace_id = hashlib.md5(
                    f"leader|{args.trade_date}|{subject_key}|{item.stock_id}|{item.candidate_rank}|{item.role_label}".encode("utf-8")
                ).hexdigest()[:16]
                candidates.append(
                    type(item)(
                        **{
                            **item.__dict__,
                            "source_trace_id": source_trace_id,
                            "source_trace": source_trace,
                        }
                    )
                )

        await upsert_rows(manager, candidates)

        ranked = sorted(candidates, key=lambda item: (item.subject_key, item.candidate_rank))
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] themes={len(grouped)}")
        print(f"[OK] rows={len(candidates)}")
        for item in ranked[: args.top_k]:
            print(
                f"[ROW] theme={item.theme_name} rank={item.candidate_rank} role={item.role_label} "
                f"stock={item.stock_name} score={item.composite_score:.2f} "
                f"pct={item.leading_score:.2f} turnover={item.turnover_rate:.2f} vr={item.volume_ratio:.2f}"
            )
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

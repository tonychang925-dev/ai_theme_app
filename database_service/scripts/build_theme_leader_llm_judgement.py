from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
import sys

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from stock_service.services.theme_leader_llm_judgement_service import (
    ThemeLeaderLlmCandidateInput,
    ThemeLeaderLlmJudgementService,
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


async def ensure_table(manager: PostgresDatabaseManager) -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS theme_leader_llm_judgement (
        id BIGSERIAL PRIMARY KEY,
        trade_date DATE NOT NULL,
        subject_key VARCHAR(80) NOT NULL,
        theme_name VARCHAR(120) NOT NULL,
        candidate_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
        prompt_text TEXT NOT NULL DEFAULT '',
        leader_stock_id VARCHAR(20) NOT NULL DEFAULT '',
        leader_status VARCHAR(40) NOT NULL DEFAULT '',
        confirmation_basis VARCHAR(40) NOT NULL DEFAULT '',
        runner_up_stock_id VARCHAR(20) NOT NULL DEFAULT '',
        card_position_stock_id VARCHAR(20) NOT NULL DEFAULT '',
        supplement_stock_id VARCHAR(20) NOT NULL DEFAULT '',
        eliminated_stock_id VARCHAR(20) NOT NULL DEFAULT '',
        judgement_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        reasoning_summary TEXT NOT NULL DEFAULT '',
        model_name VARCHAR(120) NOT NULL DEFAULT '',
        prompt_version VARCHAR(120) NOT NULL DEFAULT '',
        source_type VARCHAR(80) NOT NULL DEFAULT '',
        source_trace_id VARCHAR(120) NOT NULL DEFAULT '',
        source_trace JSONB NOT NULL DEFAULT '{}'::jsonb,
        source_version VARCHAR(120) NOT NULL DEFAULT '',
        rule_version VARCHAR(120) NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        CONSTRAINT uq_theme_leader_llm_judgement UNIQUE (trade_date, subject_key)
    );
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(ddl)
        await conn.execute("ALTER TABLE theme_leader_llm_judgement ADD COLUMN IF NOT EXISTS leader_status VARCHAR(40) NOT NULL DEFAULT ''")
        await conn.execute("ALTER TABLE theme_leader_llm_judgement ADD COLUMN IF NOT EXISTS confirmation_basis VARCHAR(40) NOT NULL DEFAULT ''")


async def fetch_rows(
    manager: PostgresDatabaseManager,
    trade_date: str,
    limit_themes: int | None,
    only_queued: bool = False,
) -> list[ThemeLeaderLlmCandidateInput]:
    chosen_themes_sql = """
        SELECT subject_key, theme_name
        FROM theme_mainline_judgement
        WHERE trade_date = $1::date
          AND theme_tier IN ('main', 'strong_branch')
        ORDER BY
            CASE theme_tier WHEN 'main' THEN 0 ELSE 1 END,
            (event_chain_score + market_recognition_score + mainline_stability_score) DESC,
            subject_key
        LIMIT COALESCE($2::int, 99999)
    """
    if only_queued:
        chosen_themes_sql = """
        SELECT subject_key, theme_name
        FROM theme_leader_llm_queue
        WHERE trade_date = $1::date
          AND need_llm_judgement = TRUE
        ORDER BY queue_priority DESC, subject_key
        LIMIT COALESCE($2::int, 99999)
        """
    sql = f"""
    WITH chosen_themes AS (
        {chosen_themes_sql}
    )
    SELECT
        s.trade_date::text AS trade_date,
        s.subject_key,
        t.theme_name,
        s.stock_id,
        s.stock_name,
        COALESCE(s.rank_order, 9999) AS rank_order,
        COALESCE(s.pct_chg, 0) AS pct_chg,
        COALESCE(s.is_leader, FALSE) AS is_leader,
        COALESCE(s.limit_up, FALSE) AS is_limit_up,
        COALESCE(c.turnover_rate, 0) AS turnover_rate,
        COALESCE(c.volume_ratio, 0) AS volume_ratio,
        COALESCE(c.main_net_inflow, 0) AS main_net_inflow,
        COALESCE(s.amount, 0) AS amount,
        COALESCE(s.open_price, 0) AS open_price,
        COALESCE(s.high_price, 0) AS high_price,
        COALESCE(s.low_price, 0) AS low_price,
        COALESCE(s.close_price, 0) AS close_price,
        COALESCE(s.pre_close, 0) AS pre_close,
        COALESCE(c.role_label, '') AS role_label,
        COALESCE(c.candidate_rank, 0) AS candidate_rank,
        COALESCE(c.purity_score, 0) AS purity_score,
        COALESCE(c.leading_score, 0) AS leading_score,
        COALESCE(c.capital_score, 0) AS capital_score,
        COALESCE(c.structure_score, 0) AS structure_score,
        COALESCE(c.resilience_score, 0) AS resilience_score,
        COALESCE(c.composite_score, 0) AS composite_score,
        COALESCE(p.position_label, '') AS position_label,
        COALESCE(pat.pattern_labels, '[]'::jsonb) AS pattern_labels,
        COALESCE(d.remark, '') AS stock_remark
    FROM chosen_themes t
    JOIN subject_stock_daily_snapshot s
      ON s.trade_date = $1::date
     AND s.subject_key = t.subject_key
    LEFT JOIN theme_leader_candidate c
      ON c.trade_date = s.trade_date
     AND c.subject_key = s.subject_key
     AND split_part(c.stock_id, '.', 1) = split_part(s.stock_id, '.', 1)
    LEFT JOIN stock_position_judgement p
      ON p.trade_date = s.trade_date
     AND split_part(p.stock_id, '.', 1) = split_part(s.stock_id, '.', 1)
    LEFT JOIN stock_pattern_judgement pat
      ON pat.trade_date = s.trade_date
     AND split_part(pat.stock_id, '.', 1) = split_part(s.stock_id, '.', 1)
    LEFT JOIN subject_stock_detail_staging d
      ON d.stock_id = split_part(s.stock_id, '.', 1)
    ORDER BY s.subject_key, COALESCE(s.rank_order, 9999), s.stock_id
    """
    trade_date_value = datetime.strptime(str(trade_date), "%Y-%m-%d").date()
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value, limit_themes)
    results: list[ThemeLeaderLlmCandidateInput] = []
    for row in rows:
        patterns = row["pattern_labels"]
        if isinstance(patterns, str):
            try:
                patterns = json.loads(patterns)
            except Exception:
                patterns = []
        results.append(
            ThemeLeaderLlmCandidateInput(
                trade_date=row["trade_date"],
                subject_key=row["subject_key"],
                theme_name=row["theme_name"],
                stock_id=row["stock_id"],
                stock_name=row["stock_name"],
                rank_order=int(row["rank_order"] or 0),
                pct_chg=float(row["pct_chg"] or 0),
                is_leader=bool(row["is_leader"]),
                is_limit_up=bool(row["is_limit_up"]),
                turnover_rate=float(row["turnover_rate"] or 0),
                volume_ratio=float(row["volume_ratio"] or 0),
                main_net_inflow=float(row["main_net_inflow"] or 0),
                amount=float(row["amount"] or 0),
                open_price=float(row["open_price"] or 0),
                high_price=float(row["high_price"] or 0),
                low_price=float(row["low_price"] or 0),
                close_price=float(row["close_price"] or 0),
                pre_close=float(row["pre_close"] or 0),
                role_label=row["role_label"] or "",
                candidate_rank=int(row["candidate_rank"] or 0),
                purity_score=float(row["purity_score"] or 0),
                leading_score=float(row["leading_score"] or 0),
                capital_score=float(row["capital_score"] or 0),
                structure_score=float(row["structure_score"] or 0),
                resilience_score=float(row["resilience_score"] or 0),
                composite_score=float(row["composite_score"] or 0),
                position_label=row["position_label"] or "",
                pattern_labels=tuple(str(x) for x in (patterns or [])),
                stock_remark=row["stock_remark"] or "",
            )
        )
    return results


async def upsert_rows(manager: PostgresDatabaseManager, items: list[dict[str, Any]]) -> None:
    if not items:
        return
    sql = """
    INSERT INTO theme_leader_llm_judgement (
        trade_date, subject_key, theme_name, candidate_payload, prompt_text,
        leader_stock_id, leader_status, confirmation_basis, runner_up_stock_id, card_position_stock_id, supplement_stock_id, eliminated_stock_id,
        judgement_json, reasoning_summary, model_name, prompt_version,
        source_type, source_trace_id, source_trace, source_version, rule_version, updated_at
    ) VALUES (
        $1::date, $2, $3, $4::jsonb, $5,
        $6, $7, $8, $9, $10, $11, $12,
        $13::jsonb, $14, $15, $16,
        $17, $18, $19::jsonb, $20, $21, NOW()
    )
    ON CONFLICT (trade_date, subject_key)
    DO UPDATE SET
        theme_name = EXCLUDED.theme_name,
        candidate_payload = EXCLUDED.candidate_payload,
        prompt_text = EXCLUDED.prompt_text,
        leader_stock_id = CASE WHEN EXCLUDED.leader_stock_id <> '' THEN EXCLUDED.leader_stock_id ELSE theme_leader_llm_judgement.leader_stock_id END,
        leader_status = CASE WHEN EXCLUDED.leader_status <> '' THEN EXCLUDED.leader_status ELSE theme_leader_llm_judgement.leader_status END,
        confirmation_basis = CASE WHEN EXCLUDED.confirmation_basis <> '' THEN EXCLUDED.confirmation_basis ELSE theme_leader_llm_judgement.confirmation_basis END,
        runner_up_stock_id = CASE WHEN EXCLUDED.runner_up_stock_id <> '' THEN EXCLUDED.runner_up_stock_id ELSE theme_leader_llm_judgement.runner_up_stock_id END,
        card_position_stock_id = CASE WHEN EXCLUDED.card_position_stock_id <> '' THEN EXCLUDED.card_position_stock_id ELSE theme_leader_llm_judgement.card_position_stock_id END,
        supplement_stock_id = CASE WHEN EXCLUDED.supplement_stock_id <> '' THEN EXCLUDED.supplement_stock_id ELSE theme_leader_llm_judgement.supplement_stock_id END,
        eliminated_stock_id = CASE WHEN EXCLUDED.eliminated_stock_id <> '' THEN EXCLUDED.eliminated_stock_id ELSE theme_leader_llm_judgement.eliminated_stock_id END,
        judgement_json = CASE WHEN EXCLUDED.judgement_json <> '{}'::jsonb THEN EXCLUDED.judgement_json ELSE theme_leader_llm_judgement.judgement_json END,
        reasoning_summary = CASE WHEN EXCLUDED.reasoning_summary <> '' THEN EXCLUDED.reasoning_summary ELSE theme_leader_llm_judgement.reasoning_summary END,
        model_name = CASE WHEN EXCLUDED.model_name <> '' THEN EXCLUDED.model_name ELSE theme_leader_llm_judgement.model_name END,
        prompt_version = EXCLUDED.prompt_version,
        source_type = EXCLUDED.source_type,
        source_trace_id = EXCLUDED.source_trace_id,
        source_trace = EXCLUDED.source_trace,
        source_version = EXCLUDED.source_version,
        rule_version = EXCLUDED.rule_version,
        updated_at = NOW()
    """
    payload = [
        (
            datetime.strptime(str(item["trade_date"]), "%Y-%m-%d").date(),
            item["subject_key"],
            item["theme_name"],
            json.dumps(item["candidate_payload"], ensure_ascii=False),
            item["prompt_text"],
            item.get("leader_stock_id", ""),
            item.get("leader_status", ""),
            item.get("confirmation_basis", ""),
            item.get("runner_up_stock_id", ""),
            item.get("card_position_stock_id", ""),
            item.get("supplement_stock_id", ""),
            item.get("eliminated_stock_id", ""),
            json.dumps(item.get("judgement_json", {}), ensure_ascii=False),
            item.get("reasoning_summary", ""),
            item.get("model_name", ""),
            item.get("prompt_version", ""),
            item.get("source_type", ""),
            item.get("source_trace_id", ""),
            json.dumps(item.get("source_trace", {}), ensure_ascii=False),
            item.get("source_version", ""),
            item.get("rule_version", ""),
        )
        for item in items
    ]
    async with manager.pool.acquire() as conn:
        await conn.executemany(sql, payload)


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Build theme leader LLM judgement candidate payloads")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--limit-themes", type=int, default=None)
    parser.add_argument("--only-queued", action="store_true")
    args = parser.parse_args()

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        await ensure_table(manager)
        rows = await fetch_rows(manager, args.trade_date, args.limit_themes, only_queued=args.only_queued)
        service = ThemeLeaderLlmJudgementService()
        grouped: dict[str, list[ThemeLeaderLlmCandidateInput]] = {}
        for row in rows:
            grouped.setdefault(row.subject_key, []).append(row)
        items: list[dict[str, Any]] = []
        for subject_key, group in grouped.items():
            judgement = service.build_placeholder_judgement(group)
            items.append(judgement.__dict__)
        await upsert_rows(manager, items)
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] theme_count={len(items)}")
        if items:
            sample = items[0]
            print(f"[OK] sample_theme={sample['theme_name']}")
            print(f"[OK] sample_candidates={len(sample['candidate_payload'].get('candidates') or [])}")
            print(f"[OK] prompt_version={sample['prompt_version']}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

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
from stock_service.models import ThemeLeaderLlmJudgement
from stock_service.services.theme_leader_llm_judgement_service import ThemeLeaderLlmJudgementService


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


async def fetch_existing(manager: PostgresDatabaseManager, trade_date: str, subject_key: str) -> ThemeLeaderLlmJudgement | None:
    sql = """
    SELECT *
    FROM theme_leader_llm_judgement
    WHERE trade_date = $1::date
      AND subject_key = $2
    """
    trade_date_value = datetime.strptime(str(trade_date), "%Y-%m-%d").date()
    async with manager.pool.acquire() as conn:
        row = await conn.fetchrow(sql, trade_date_value, subject_key)
    if not row:
        return None
    data = dict(row)
    candidate_payload = data.get("candidate_payload") or {}
    if isinstance(candidate_payload, str):
        try:
            candidate_payload = json.loads(candidate_payload)
        except Exception:
            candidate_payload = {}
    judgement_json = data.get("judgement_json") or {}
    if isinstance(judgement_json, str):
        try:
            judgement_json = json.loads(judgement_json)
        except Exception:
            judgement_json = {}
    source_trace = data.get("source_trace") or {}
    if isinstance(source_trace, str):
        try:
            source_trace = json.loads(source_trace)
        except Exception:
            source_trace = {}
    return ThemeLeaderLlmJudgement(
        trade_date=str(data["trade_date"]),
        subject_key=data["subject_key"],
        theme_name=data["theme_name"],
        candidate_payload=candidate_payload,
        prompt_text=data.get("prompt_text") or "",
        leader_stock_id=data.get("leader_stock_id") or "",
        leader_status=data.get("leader_status") or "",
        confirmation_basis=data.get("confirmation_basis") or "",
        runner_up_stock_id=data.get("runner_up_stock_id") or "",
        card_position_stock_id=data.get("card_position_stock_id") or "",
        supplement_stock_id=data.get("supplement_stock_id") or "",
        eliminated_stock_id=data.get("eliminated_stock_id") or "",
        judgement_json=judgement_json,
        reasoning_summary=data.get("reasoning_summary") or "",
        model_name=data.get("model_name") or "",
        prompt_version=data.get("prompt_version") or "",
        source_type=data.get("source_type") or "",
        source_trace_id=data.get("source_trace_id") or "",
        source_trace=source_trace,
        source_version=data.get("source_version") or "",
        rule_version=data.get("rule_version") or "",
    )


async def upsert(manager: PostgresDatabaseManager, item: ThemeLeaderLlmJudgement) -> None:
    sql = """
    UPDATE theme_leader_llm_judgement
    SET leader_stock_id = $3,
        leader_status = $4,
        confirmation_basis = $5,
        runner_up_stock_id = $6,
        card_position_stock_id = $7,
        supplement_stock_id = $8,
        eliminated_stock_id = $9,
        judgement_json = $10::jsonb,
        reasoning_summary = $11,
        model_name = $12,
        updated_at = NOW()
    WHERE trade_date = $1::date
      AND subject_key = $2
    """
    async with manager.pool.acquire() as conn:
        await conn.execute(
            sql,
            datetime.strptime(str(item.trade_date), "%Y-%m-%d").date(),
            item.subject_key,
            item.leader_stock_id,
            item.leader_status,
            item.confirmation_basis,
            item.runner_up_stock_id,
            item.card_position_stock_id,
            item.supplement_stock_id,
            item.eliminated_stock_id,
            json.dumps(item.judgement_json, ensure_ascii=False),
            item.reasoning_summary,
            item.model_name,
        )


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Apply LLM response to theme_leader_llm_judgement")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--subject-key", required=True)
    parser.add_argument("--response-json", required=True, help="Path to LLM JSON response")
    parser.add_argument("--model-name", required=True)
    args = parser.parse_args()

    response = json.loads(Path(args.response_json).read_text(encoding="utf-8"))
    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    try:
        existing = await fetch_existing(manager, args.trade_date, args.subject_key)
        if not existing:
            raise SystemExit(f"missing theme_leader_llm_judgement seed row: {args.trade_date} {args.subject_key}")
        service = ThemeLeaderLlmJudgementService()
        updated = service.apply_llm_response(existing, response, args.model_name)
        await upsert(manager, updated)
        print(f"[OK] trade_date={args.trade_date}")
        print(f"[OK] subject_key={args.subject_key}")
        print(f"[OK] leader={updated.leader_stock_id}")
        print(f"[OK] leader_status={updated.leader_status}")
        print(f"[OK] confirmation_basis={updated.confirmation_basis}")
        print(f"[OK] runner_up={updated.runner_up_stock_id}")
        print(f"[OK] card_position={updated.card_position_stock_id}")
        print(f"[OK] supplement={updated.supplement_stock_id}")
        print(f"[OK] eliminated={updated.eliminated_stock_id}")
        print(f"[OK] model_name={updated.model_name}")
        return 0
    finally:
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

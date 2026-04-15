from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from database_service.config import DatabaseConfig, DatabaseType, RedisConfig
from database_service.managers.postgres_manager import PostgresDatabaseManager
from database_service.scripts.build_theme_leader_llm_judgement import (
    ThemeLeaderLlmCandidateInput,
    ensure_table,
    fetch_rows as fetch_candidate_rows,
    upsert_rows as upsert_seed_rows,
)
from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call LLM for theme leader judgement")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--subject-key", help="单个题材 subject_key")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--limit-themes", type=int, default=None)
    parser.add_argument("--api-key", default="")
    parser.add_argument("--model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--skip-health-check", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-queued", action="store_true")
    parser.add_argument("--only-pending", action="store_true")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "tmp" / "theme_leader_llm"))
    return parser.parse_args()


async def fetch_seed_rows(
    manager: PostgresDatabaseManager,
    trade_date: str,
    subject_key: str | None,
    limit: int,
    *,
    only_queued: bool = False,
    only_pending: bool = False,
) -> list[ThemeLeaderLlmJudgement]:
    sql = """
    SELECT j.*
    FROM theme_leader_llm_judgement j
    LEFT JOIN theme_mainline_judgement m
      ON m.trade_date = j.trade_date
     AND m.subject_key = j.subject_key
    LEFT JOIN theme_leader_llm_queue q
      ON q.trade_date = j.trade_date
     AND q.subject_key = j.subject_key
    WHERE j.trade_date = $1::date
      AND ($2::text IS NULL OR j.subject_key = $2)
      AND ($4::boolean = FALSE OR COALESCE(q.need_llm_judgement, FALSE) = TRUE)
      AND ($5::boolean = FALSE OR COALESCE(j.model_name, '') = '' OR COALESCE(j.leader_status, '') = '')
    ORDER BY
      COALESCE(q.queue_priority, 0) DESC,
      CASE m.theme_tier
        WHEN 'main' THEN 0
        WHEN 'strong_branch' THEN 1
        ELSE 2
      END,
      (COALESCE(m.event_chain_score, 0) + COALESCE(m.market_recognition_score, 0) + COALESCE(m.mainline_stability_score, 0)) DESC,
      j.subject_key
    LIMIT $3
    """
    trade_date_value = datetime.strptime(str(trade_date), "%Y-%m-%d").date()
    async with manager.pool.acquire() as conn:
        rows = await conn.fetch(sql, trade_date_value, subject_key, limit, only_queued, only_pending)
    results: list[ThemeLeaderLlmJudgement] = []
    for row in rows:
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
        results.append(
            ThemeLeaderLlmJudgement(
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
        )
    return results


async def upsert_result(manager: PostgresDatabaseManager, item: ThemeLeaderLlmJudgement) -> None:
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


async def call_model(parser: ReliableDeepSeekParser, prompt_text: str) -> dict[str, Any]:
    response = await parser.parse_content(prompt_text)
    if response is None:
        raise RuntimeError("ReliableDeepSeekParser returned empty response")
    if not isinstance(response, dict):
        raise RuntimeError(f"ReliableDeepSeekParser returned non-dict response: {type(response)!r}")
    return response


async def build_seed_rows(
    manager: PostgresDatabaseManager,
    trade_date: str,
    limit_themes: int | None,
    subject_key: str | None,
    only_queued: bool,
) -> int:
    rows = await fetch_candidate_rows(manager, trade_date, limit_themes, only_queued=only_queued)
    if subject_key:
        rows = [row for row in rows if row.subject_key == subject_key]
    grouped: dict[str, list[ThemeLeaderLlmCandidateInput]] = {}
    for row in rows:
        grouped.setdefault(row.subject_key, []).append(row)
    if not grouped:
        return 0
    service = ThemeLeaderLlmJudgementService()
    items: list[dict[str, Any]] = []
    for _, group in grouped.items():
        judgement = service.build_placeholder_judgement(group)
        items.append(judgement.__dict__)
    await upsert_seed_rows(manager, items)
    return len(items)


async def main_async() -> int:
    args = parse_args()
    api_key = args.api_key or os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise SystemExit("missing api key: use --api-key or DEEPSEEK_API_KEY")

    os.environ["DEEPSEEK_API_KEY"] = api_key

    manager = PostgresDatabaseManager(get_postgres_config())
    await manager.connect()
    parser: ReliableDeepSeekParser | None = ReliableDeepSeekParser(
        model_name=args.model,
        config={
            "max_retries": args.max_retries,
            "timeout": args.timeout,
            "temperature": args.temperature,
            "model_name": args.model,
        },
    )
    try:
        await ensure_table(manager)
        seed_count = await build_seed_rows(manager, args.trade_date, args.limit_themes, args.subject_key, args.only_queued)
        print(f"[OK] seed_rows={seed_count}")
        rows = await fetch_seed_rows(
            manager,
            args.trade_date,
            args.subject_key,
            args.limit,
            only_queued=args.only_queued,
            only_pending=args.only_pending,
        )
        if not rows:
            if args.only_pending:
                print("[OK] no_pending_rows=1")
                print("[OK] skip_reason=all queued themes already have llm results")
                return 0
            raise SystemExit("missing seed rows after auto-build")

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        service = ThemeLeaderLlmJudgementService()

        if not args.skip_health_check:
            health = await parser.health_check()
            if not health.get("is_healthy", False):
                raise SystemExit(f"ReliableDeepSeekParser health check failed: {json.dumps(health, ensure_ascii=False)}")
            print(f"[OK] parser_health={health.get('service_status', 'unknown')}")
            print(f"[OK] parser_model={args.model}")

        for item in rows:
            response = await call_model(parser, item.prompt_text)
            response_path = output_dir / f"{item.trade_date}_{item.subject_key.replace(':', '_')}.json"
            response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[OK] subject_key={item.subject_key}")
            print(f"[OK] response_file={response_path}")
            if args.dry_run:
                continue
            updated = service.apply_llm_response(item, response, args.model)
            await upsert_result(manager, updated)
            print(f"[OK] leader={updated.leader_stock_id}")
            print(f"[OK] leader_status={updated.leader_status}")
            print(f"[OK] confirmation_basis={updated.confirmation_basis}")
            print(f"[OK] runner_up={updated.runner_up_stock_id}")
        return 0
    finally:
        if parser is not None:
            await parser.close()
        await manager.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

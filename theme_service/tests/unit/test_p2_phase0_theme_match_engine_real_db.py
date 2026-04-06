from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import asyncpg
import pytest

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway, get_gateway
from theme_service.services.theme_service import ThemeService


DATASET_PATH = Path("/Users/admin/Desktop/ai_theme_app/evaluate_service/data/raw/validation_dataset.json")
PREVIEW_PATH = Path("/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_theme_match_engine_5.preview.json")
PREVIEW_10_PATH = Path("/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_theme_match_engine_10.preview.json")
EXPECTED_SUBJECT_KEY = "9030409"
EXPECTED_THEME_NAME = "AR眼镜"


def _pg_connect_kwargs() -> dict:
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        "database": os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    }


def _load_ai_ar_cases(limit: int) -> list[dict]:
    rows = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    selected = [row for row in rows if row.get("theme") == "AI/AR眼镜"][:limit]
    assert len(selected) == limit, f"validation_dataset.json 中缺少 {limit} 条 AI/AR眼镜 样本"
    return selected


def _normalize_publish_date(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return "2026-03-01"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
    return "2026-03-01"


async def _run_ai_ar_match_case_batch(limit: int) -> list[dict]:
    cfg = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
    )
    cfg.redis.enabled = False
    init_config(cfg)
    DatabaseGateway._instance = None

    gateway = await get_gateway()
    service = ThemeService()
    service.set_database_gateway(gateway)

    conn = await asyncpg.connect(**_pg_connect_kwargs())
    created_news_event_ids: list[int] = []
    created_news_raw_ids: list[int] = []
    preview_rows: list[dict] = []

    try:
        profiles = await gateway.load_theme_match_profiles()
        assert any(str(row.get("subject_key")) == EXPECTED_SUBJECT_KEY for row in profiles), (
            f"stock_data_test 中缺少 subject_key={EXPECTED_SUBJECT_KEY} 的题材画像"
        )

        for row in _load_ai_ar_cases(limit):
            external_news_id = f"tc_p2_ar_{row['test_id']}_{uuid.uuid4().hex[:8]}"
            news_data = {
                "news_id": external_news_id,
                "title": row["title"],
                "content": row["content"],
                "source": "pytest_p2_phase0_theme_match_engine",
                "publish_date": _normalize_publish_date(row.get("date")),
                "metadata": {"source_test_id": row["test_id"], "ground_truth_theme": row["theme"]},
            }
            created_external_id = await gateway.create_news(news_data)
            assert created_external_id == external_news_id

            news_row = await gateway.get_news(external_news_id)
            assert news_row is not None and news_row.get("id") is not None
            created_news_raw_ids.append(int(news_row["id"]))

            event_summary = (row.get("content") or row.get("title") or "")[:180]
            event_payload = {
                "news_id": int(news_row["id"]),
                "event_type": row.get("event_type") or "行业动态",
                "impact_industries": row.get("impact_industries") or ["AI/AR眼镜"],
                "direction": "利好",
                "confidence": 0.95,
                "summary": event_summary,
                "theme_directive": {},
                "theme_directive_processed": False,
                "severity_score": 0.8,
                "source_weight": 1.0,
                "event_time": f"{_normalize_publish_date(row.get('date'))} 00:00:00",
                "entities": [],
                "causal_claim": [event_summary] if event_summary else [],
                "evidence_set": {"core_concepts": ["AI眼镜", "AR眼镜", "智能眼镜"]},
                "raw_event_json": {
                    "title": row["title"],
                    "content": row["content"],
                    "source_test_id": row["test_id"],
                    "ground_truth_theme": row["theme"],
                },
            }
            event_id = await gateway.create_news_event(event_payload)
            assert event_id is not None
            created_news_event_ids.append(int(event_id))

            event_row = await gateway.get_news_event_for_match(int(event_id))
            assert event_row is not None

            result = await service.match_event(event_row)
            preview_rows.append(
                {
                    "test_id": row["test_id"],
                    "event_id": int(event_id),
                    "title": row["title"],
                    "decision": result["decision"],
                    "matched_subject_key": result.get("matched_subject_key"),
                    "matched_theme_name": result.get("matched_theme_name"),
                    "matched_theme_id": result.get("matched_theme_id"),
                    "confidence": result.get("confidence"),
                    "reason_code": result.get("reason_code"),
                    "expected_subject_key": EXPECTED_SUBJECT_KEY,
                    "top1_hit": str(result.get("matched_subject_key")) == EXPECTED_SUBJECT_KEY,
                }
            )
        return preview_rows

    finally:
        try:
            if created_news_event_ids:
                await conn.execute("DELETE FROM news_event WHERE id = ANY($1::int[])", created_news_event_ids)
            if created_news_raw_ids:
                await conn.execute("DELETE FROM news_raw WHERE id = ANY($1::int[])", created_news_raw_ids)
        finally:
            await conn.close()
            if hasattr(gateway, "close"):
                await gateway.close()


@pytest.mark.asyncio
async def test_theme_match_engine_matches_five_ai_ar_cases_against_real_db():
    preview_rows = await _run_ai_ar_match_case_batch(limit=5)
    PREVIEW_PATH.write_text(
        json.dumps(preview_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert len(preview_rows) == 5
    for result in preview_rows:
        assert result["decision"] == "MATCH"
        assert str(result.get("matched_subject_key")) == EXPECTED_SUBJECT_KEY
        assert result.get("matched_theme_name") == EXPECTED_THEME_NAME


@pytest.mark.asyncio
async def test_theme_match_engine_top1_accuracy_on_first_ten_ai_ar_cases_is_at_least_097():
    preview_rows = await _run_ai_ar_match_case_batch(limit=10)
    PREVIEW_10_PATH.write_text(
        json.dumps(preview_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    assert len(preview_rows) == 10

    hit_count = sum(1 for row in preview_rows if row["top1_hit"])
    top1_accuracy = hit_count / len(preview_rows)

    assert top1_accuracy >= 0.97, (
        f"前10条 AI/AR眼镜 样本 top1_accuracy={top1_accuracy:.4f}，"
        f"未达到 0.97；详情见 {PREVIEW_10_PATH}"
    )

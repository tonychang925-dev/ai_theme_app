from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path

import asyncpg
import pytest
import redis.asyncio as redis

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway
from database_service.streams.handlers.theme_processor import ThemeProcessor


DATASET_PATH = Path("/Users/admin/Desktop/ai_theme_app/evaluate_service/data/raw/validation_dataset.json")
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


def _load_five_ai_ar_cases() -> list[dict]:
    rows = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    selected = [row for row in rows if row.get("theme") == "AI/AR眼镜"][:5]
    assert len(selected) == 5
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


async def _wait_for_decisions(redis_client, stream_name: str, expected_count: int, timeout_s: float = 60.0) -> list[dict]:
    import asyncio
    import time

    started = time.time()
    decisions: list[dict] = []
    seen_ids = set()
    while time.time() - started < timeout_s:
        messages = await redis_client.xread({stream_name: "0-0"}, count=100, block=1000)
        for _stream, message_list in messages:
            for message_id, payload in message_list:
                if message_id in seen_ids:
                    continue
                seen_ids.add(message_id)
                raw = payload.get("decision")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                decisions.append(json.loads(raw))
        if len(decisions) >= expected_count:
            return decisions
        await asyncio.sleep(0.2)
    return decisions


@pytest.mark.asyncio
async def test_theme_processor_consumes_structured_events_and_publishes_match_decisions():
    run_id = uuid.uuid4().hex[:8]
    structured_stream = f"stream:p2phase0:test:structured:{run_id}"
    decision_stream = f"stream:p2phase0:test:decision:{run_id}"
    dead_letter_stream = f"stream:p2phase0:test:dead:{run_id}"
    consumer_group = f"theme_processors_p2_{run_id}"
    consumer_name = f"pytest_tp_{run_id}"

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

    processor = ThemeProcessor(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        enable_classification_first=False,
        consumer_name=consumer_name,
        config={
            "stream_structured": structured_stream,
            "stream_decision": decision_stream,
            "stream_dead_letter": dead_letter_stream,
            "consumer_group": consumer_group,
            "structured_batch_size": 10,
            "structured_block_time": 500,
        },
    )

    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    conn = await asyncpg.connect(**_pg_connect_kwargs())
    created_news_event_ids: list[int] = []
    created_news_raw_ids: list[int] = []

    try:
        ok = await processor.initialize()
        assert ok is True
        await processor.start()

        for row in _load_five_ai_ar_cases():
            external_news_id = f"tp_it_{row['test_id']}_{uuid.uuid4().hex[:8]}"
            news_data = {
                "news_id": external_news_id,
                "title": row["title"],
                "content": row["content"],
                "source": "pytest_p2_phase0_theme_processor",
                "publish_date": _normalize_publish_date(row.get("date")),
                "metadata": {"source_test_id": row["test_id"], "ground_truth_theme": row["theme"]},
            }
            await processor.gateway.create_news(news_data)
            news_row = await processor.gateway.get_news(external_news_id)
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
            event_id = await processor.gateway.create_news_event(event_payload)
            created_news_event_ids.append(int(event_id))

            await redis_client.xadd(
                structured_stream,
                {"payload": json.dumps({"event_id": int(event_id)}, ensure_ascii=False)},
                maxlen=1000,
            )

        decisions = await _wait_for_decisions(redis_client, decision_stream, expected_count=5, timeout_s=90.0)
        assert len(decisions) == 5, f"仅收到 {len(decisions)} 条 decision"

        for decision in decisions:
            assert decision["action"] == "update_theme"
            assert decision["decision_type"] == "phase0_match"
            assert decision["match_result"]["decision"] == "MATCH"
            assert str(decision["match_result"]["matched_subject_key"]) == EXPECTED_SUBJECT_KEY
            assert decision["match_result"]["matched_theme_name"] == EXPECTED_THEME_NAME
            assert decision["theme_data"]["subject_key"] == EXPECTED_SUBJECT_KEY

        dead_letter = await redis_client.xrange(dead_letter_stream, min="-", max="+")
        assert dead_letter == []

    finally:
        try:
            await processor.stop()
        finally:
            try:
                if created_news_event_ids:
                    await conn.execute("DELETE FROM news_event WHERE id = ANY($1::int[])", created_news_event_ids)
                if created_news_raw_ids:
                    await conn.execute("DELETE FROM news_raw WHERE id = ANY($1::int[])", created_news_raw_ids)
            finally:
                await conn.close()
                await redis_client.delete(structured_stream, decision_stream, dead_letter_stream)

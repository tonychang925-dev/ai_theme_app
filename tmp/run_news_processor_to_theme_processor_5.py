import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import asyncpg
import redis.asyncio as redis

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway, get_gateway
from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.handlers.theme_processor import ThemeProcessor


DATASET_PATH = Path("/Users/admin/Desktop/ai_theme_app/evaluate_service/data/raw/validation_dataset.json")
OUT_PATH = Path("/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_news_to_theme_5.preview.json")
EXPECTED_SUBJECT_KEY = "9030409"
EXPECTED_THEME_NAME = "AR眼镜"
SAMPLE_SIZE = int(os.getenv("P2_PHASE0_SAMPLE_SIZE", "5"))


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
    assert len(selected) == limit
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


class RedisStructuredEventBus:
    def __init__(self, redis_client, structured_stream: str):
        self.redis_client = redis_client
        self.structured_stream = structured_stream

    async def publish_to_stream(self, stream_key: str, data: dict):
        target = self.structured_stream if stream_key == "stream:events:structured" else stream_key
        payload = {"payload": json.dumps(data, ensure_ascii=False)}
        return await self.redis_client.xadd(target, payload, maxlen=5000)


async def _wait_for_decisions(redis_client, stream_name: str, expected_count: int, timeout_s: float = 240.0) -> list[dict]:
    import time

    started = time.time()
    decisions: list[dict] = []
    seen_ids = set()
    while time.time() - started < timeout_s:
        messages = await redis_client.xread({stream_name: "0-0"}, count=200, block=1000)
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


async def main():
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
    gateway = await get_gateway()

    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    conn = await asyncpg.connect(**_pg_connect_kwargs())

    theme_processor = ThemeProcessor(
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

    event_bus = RedisStructuredEventBus(redis_client, structured_stream)
    news_processor = NewsStreamProcessor(
        event_bus=event_bus,
        config={"database_gateway": gateway},
    )

    created_news_ids: list[int] = []
    created_event_ids: list[int] = []

    try:
        ok = await theme_processor.initialize()
        assert ok is True
        await theme_processor.start()

        process_results: list[dict] = []
        for row in _load_ai_ar_cases(SAMPLE_SIZE):
            external_news_id = f"n2t5_{row['test_id']}_{uuid.uuid4().hex[:8]}"
            news_data = {
                "news_id": external_news_id,
                "title": row["title"],
                "content": row["content"],
                "source": "pytest_p2_phase0_news_to_theme",
                "publish_date": _normalize_publish_date(row.get("date")),
                "metadata": {"source_test_id": row["test_id"], "ground_truth_theme": row["theme"]},
            }
            await gateway.create_news(news_data)
            news_row = await gateway.get_news(external_news_id)
            created_news_ids.append(int(news_row["id"]))

            stored_message = {
                "payload": {
                    "news_data": {
                        "id": int(news_row["id"]),
                        "news_row_id": int(news_row["id"]),
                        "news_id": external_news_id,
                        "title": row["title"],
                        "content": row["content"],
                        "source": news_row.get("source") or "pytest",
                        "publish_date": _normalize_publish_date(row.get("date")),
                    }
                }
            }
            result = await news_processor.process_stream_message(
                message_id=f"stored_{uuid.uuid4().hex[:8]}",
                message_data=stored_message,
            )
            process_results.append(result)
            if result.get("news_event_id"):
                created_event_ids.append(int(result["news_event_id"]))

        decisions = await _wait_for_decisions(redis_client, decision_stream, expected_count=SAMPLE_SIZE, timeout_s=300.0)

        preview = []
        for proc in process_results:
            preview.append(
                {
                    "news_event_id": proc.get("news_event_id"),
                    "structured_stream_published": proc.get("structured_stream_published"),
                    "success": proc.get("success"),
                    "error": proc.get("error"),
                }
            )

        for decision in decisions:
            match_result = decision.get("match_result", {})
            preview.append(
                {
                    "event_id": decision.get("event_id"),
                    "decision_type": decision.get("decision_type"),
                    "action": decision.get("action"),
                    "matched_subject_key": match_result.get("matched_subject_key"),
                    "matched_theme_name": match_result.get("matched_theme_name"),
                    "confidence": match_result.get("confidence"),
                    "reason_code": match_result.get("reason_code"),
                    "top1_hit": str(match_result.get("matched_subject_key")) == EXPECTED_SUBJECT_KEY,
                }
            )

        OUT_PATH.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
        decision_rows = [row for row in preview if "top1_hit" in row]
        hits = sum(1 for row in decision_rows if row["top1_hit"])
        print(
            json.dumps(
                {
                    "events": len(decision_rows),
                    "top1_hits": hits,
                    "top1_accuracy": hits / len(decision_rows) if decision_rows else 0.0,
                    "all_structured_published": all(r.get("structured_stream_published") for r in process_results),
                    "preview_path": str(OUT_PATH),
                },
                ensure_ascii=False,
            )
        )

    finally:
        try:
            await theme_processor.stop()
        finally:
            try:
                if created_event_ids:
                    await conn.execute("DELETE FROM news_event WHERE id = ANY($1::int[])", created_event_ids)
                if created_news_ids:
                    await conn.execute("DELETE FROM news_raw WHERE id = ANY($1::int[])", created_news_ids)
            finally:
                await conn.close()
                await redis_client.delete(structured_stream, decision_stream, dead_letter_stream)
                if hasattr(gateway, "close"):
                    await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())

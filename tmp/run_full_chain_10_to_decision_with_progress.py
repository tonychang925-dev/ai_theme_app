import asyncio
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import asyncpg
import redis.asyncio as redis

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "theme_service"))

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway
from database_service.managers.redis_stream_bus import UnifiedRedisStreamBus
from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.handlers.theme_processor import ThemeProcessor
from database_service.streams.gateway_integration import get_gateway


RAW_PATH = PROJECT_ROOT / "evaluate_service/data/raw/test_cases.txt"
OUT_PATH = PROJECT_ROOT / "tmp/p2_phase0_full_chain_10_to_decision.preview.json"
EXPECTED_SUBJECT_KEY = "9030409"
EXPECTED_THEME_NAME = "AR眼镜"
SAMPLE_SIZE = 10
TEST_NEWS_PREFIX = "p2_full_chain%"


def _pg_kwargs() -> Dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        "database": os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    }


def _load_first_ai_ar_raws(limit: int) -> List[str]:
    text = RAW_PATH.read_text(encoding="utf-8")
    match = re.search(r"测试集1:题材名称:AI/AR眼镜\n(.*?)(?:\n测试集2:题材名称:|\Z)", text, re.S)
    if not match:
        raise RuntimeError("未找到 AI/AR眼镜 测试段")
    block = match.group(1)
    rows: List[str] = []
    for line in block.splitlines():
        value = line.strip()
        if not value.startswith("- "):
            continue
        value = value[2:].strip().rstrip("*").strip()
        if value:
            rows.append(value)
    if len(rows) < limit:
        raise RuntimeError(f"AI/AR眼镜 原始样本不足 {limit} 条，当前 {len(rows)}")
    return rows[:limit]


class _RedisStructuredEventBus:
    def __init__(self, redis_client: redis.Redis, structured_stream: str):
        self.redis_client = redis_client
        self.structured_stream = structured_stream

    async def publish_to_stream(self, stream_key: str, data: Dict[str, Any]):
        target = self.structured_stream if stream_key == "stream:events:structured" else stream_key
        payload = {"payload": json.dumps(data, ensure_ascii=False)}
        return await self.redis_client.xadd(target, payload, maxlen=5000)


def _build_v2_payload(raw_text: str, news_id: str, sequence: int, batch_id: str) -> Dict[str, Any]:
    title = "AI/AR眼镜相关新闻"
    return {
        "_t": "news",
        "_v": 2,
        "id": news_id,
        "t": title,
        "c": raw_text,
        "s": "cls",
        "d": "2026-03-01",
        "tm": "00:00:00",
        "_b": batch_id,
        "_s": sequence,
    }


async def _wait_for_news_raw(
    gateway: Any,
    external_news_id: str,
    timeout_s: float = 30.0,
) -> Optional[Dict[str, Any]]:
    started = time.time()
    while time.time() - started < timeout_s:
        row = await gateway.get_news(external_news_id)
        if row:
            return row
        await asyncio.sleep(0.2)
    return None


async def _wait_for_decisions(
    redis_client: redis.Redis,
    stream_name: str,
    expected_count: int,
    seen_ids: set[str],
    timeout_s: float = 180.0,
) -> List[Dict[str, Any]]:
    started = time.time()
    decisions: List[Dict[str, Any]] = []
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
            break
        await asyncio.sleep(0.2)
    return decisions


def _print_progress(stage: str, current: int, total: int, extra: str = "") -> None:
    suffix = f" {extra}" if extra else ""
    print(f"[{current}/{total}] {stage}{suffix}", flush=True)


async def _cleanup_previous_test_data(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        DELETE FROM event_theme_map
        WHERE event_id IN (
            SELECT e.id
            FROM news_event e
            JOIN news_raw n ON n.id = e.news_id
            WHERE n.news_id LIKE $1
        )
        """,
        TEST_NEWS_PREFIX,
    )
    await conn.execute(
        """
        DELETE FROM news_event
        WHERE news_id IN (
            SELECT id FROM news_raw WHERE news_id LIKE $1
        )
        """,
        TEST_NEWS_PREFIX,
    )
    await conn.execute("DELETE FROM news_raw WHERE news_id LIKE $1", TEST_NEWS_PREFIX)


async def main() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")

    run_id = uuid.uuid4().hex[:8]
    batch_id = f"p2_full_chain_{run_id}"
    raw_stream = "stream:news:raw"
    structured_stream = "stream:events:structured"
    decision_stream = "stream:events:decision"
    dead_letter_stream = "stream:dead:letter"
    consumer_group = f"theme_processors_p2_{run_id}"
    consumer_name = f"tp_fc10_{run_id}"

    cfg = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
    )
    cfg.redis.enabled = True
    init_config(cfg)
    DatabaseGateway._instance = None

    stream_gateway = await get_gateway(enable_retry=True, retry_config={"max_retries": 2})
    base_gateway = stream_gateway.base_gateway

    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    await redis_client.ping()
    stream_bus = UnifiedRedisStreamBus(redis_client, cfg)

    await stream_bus.ensure_consumer_group("news_raw", "news_storage_handlers")
    for stream_name in (raw_stream, structured_stream, decision_stream, dead_letter_stream):
        await redis_client.delete(stream_name)
    await stream_bus.ensure_consumer_group("news_raw", "news_storage_handlers")

    news_handler = NewsStreamHandler(
        stream_bus=stream_bus,
        database_gateway=base_gateway,
        config={
            "consumer_group": "news_storage_handlers",
            "stream_name": "news_raw",
            "batch_size": 5,
            "block_time": 500,
        },
    )

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

    news_processor = NewsStreamProcessor(
        event_bus=_RedisStructuredEventBus(redis_client, structured_stream),
        config={"database_gateway": base_gateway},
    )

    raw_cases = _load_first_ai_ar_raws(SAMPLE_SIZE)
    created_news_raw_ids: List[int] = []
    created_news_event_ids: List[int] = []
    seen_decision_ids: set[str] = set()
    preview: List[Dict[str, Any]] = []
    conn = await asyncpg.connect(**_pg_kwargs())

    try:
        print(f"开始真实全链路测试，样本数={SAMPLE_SIZE}", flush=True)
        await _cleanup_previous_test_data(conn)
        await news_handler.start_storage_service()
        ok = await theme_processor.initialize()
        if not ok:
            raise RuntimeError("theme_processor 初始化失败")
        await theme_processor.start()

        processed_decisions = 0
        for idx, raw_text in enumerate(raw_cases, start=1):
            external_news_id = f"{batch_id}_{idx:03d}_{uuid.uuid4().hex[:6]}"
            payload = _build_v2_payload(raw_text, external_news_id, idx, batch_id)

            await stream_bus.publish_to_stream("news_raw", {"payload": payload})
            _print_progress("news_raw injected", idx, SAMPLE_SIZE, external_news_id)

            stored_news = await _wait_for_news_raw(base_gateway, external_news_id, timeout_s=60.0)
            if not stored_news:
                raise RuntimeError(f"news_raw 未落库: {external_news_id}")
            created_news_raw_ids.append(int(stored_news["id"]))
            _print_progress("news_raw persisted", idx, SAMPLE_SIZE, f"id={stored_news['id']}")

            stored_message = {
                "payload": {
                    "news_data": {
                        "id": int(stored_news["id"]),
                        "news_row_id": int(stored_news["id"]),
                        "news_id": external_news_id,
                        "title": stored_news.get("title") or "AI/AR眼镜相关新闻",
                        "content": stored_news.get("content") or raw_text,
                        "source": stored_news.get("source") or "pytest",
                        "publish_date": str(stored_news.get("publish_date") or "2026-03-01"),
                    }
                }
            }
            processor_result = await news_processor.process_stream_message(
                message_id=f"stored_{uuid.uuid4().hex[:8]}",
                message_data=stored_message,
            )
            if not processor_result.get("success"):
                raise RuntimeError(f"news_stream_processor 失败: {processor_result}")

            news_event_id = processor_result.get("news_event_id")
            if not news_event_id:
                raise RuntimeError(f"未生成 news_event_id: {processor_result}")
            created_news_event_ids.append(int(news_event_id))
            _print_progress("news_event persisted", idx, SAMPLE_SIZE, f"event_id={news_event_id}")

            if not processor_result.get("structured_stream_published"):
                raise RuntimeError(f"structured stream 未发布: {processor_result}")
            _print_progress("structured event published", idx, SAMPLE_SIZE)

            new_decisions = await _wait_for_decisions(
                redis_client,
                decision_stream,
                expected_count=1,
                seen_ids=seen_decision_ids,
                timeout_s=180.0,
            )
            if not new_decisions:
                raise RuntimeError(f"未收到 decision: news_event_id={news_event_id}")

            for decision in new_decisions:
                match_result = decision.get("match_result", {}) or {}
                predicted = str(match_result.get("matched_subject_key") or "")
                processed_decisions += 1
                top1_hit = predicted == EXPECTED_SUBJECT_KEY
                preview.append(
                    {
                        "index": processed_decisions,
                        "news_id": external_news_id,
                        "news_event_id": news_event_id,
                        "decision_type": decision.get("decision_type"),
                        "action": decision.get("action"),
                        "matched_subject_key": predicted,
                        "matched_theme_name": match_result.get("matched_theme_name"),
                        "confidence": match_result.get("confidence"),
                        "reason_code": match_result.get("reason_code"),
                        "top1_hit": top1_hit,
                    }
                )
                _print_progress(
                    "decision received",
                    processed_decisions,
                    SAMPLE_SIZE,
                    f"{decision.get('action')} -> {predicted}",
                )

        hits = sum(1 for row in preview if row["top1_hit"])
        report = {
            "events": len(preview),
            "processed": len(preview),
            "top1_hits": hits,
            "top1_accuracy": hits / len(preview) if preview else 0.0,
            "expected_subject_key": EXPECTED_SUBJECT_KEY,
            "expected_theme_name": EXPECTED_THEME_NAME,
            "details": preview,
        }
        OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in report.items() if k != "details"} | {"preview_path": str(OUT_PATH)}, ensure_ascii=False), flush=True)

    finally:
        try:
            await news_handler.stop_storage_service()
        except Exception:
            pass
        try:
            await theme_processor.stop()
        except Exception:
            pass
        await conn.close()
        await redis_client.delete(raw_stream, structured_stream, decision_stream, dead_letter_stream)
        if hasattr(base_gateway, "close"):
            await base_gateway.close()


if __name__ == "__main__":
    asyncio.run(main())

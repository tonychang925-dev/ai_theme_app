import asyncio
import json
import os
import re
import sys
import time
import uuid
from collections import Counter, defaultdict
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
from database_service.streams.gateway_integration import get_gateway
from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.handlers.theme_processor import ThemeProcessor


RAW_PATH = PROJECT_ROOT / "evaluate_service/data/raw/test_cases.txt"
GT_OVERRIDE_PATH = PROJECT_ROOT / "structured_events_with_gt.jsonl"
OUT_PATH = PROJECT_ROOT / "tmp/p2_phase0_full_chain_100_to_decision.report.json"
SAMPLE_SIZE = 100
TEST_NEWS_PREFIX = "p2_full_chain%"

THEME_KEY_MAP = {
    "AI/AR眼镜": "9030409",
    "SpaceX": "9064166",
    "可控核聚变": "9017950",
    "对日制裁": "9059919",
    "稀土永磁": "9010367",
    "海洋经济": "9043698",
    "深海经济": "9043698",
    "光刻胶": "9018411",
    "卫星互联": "9019807",
    "卫星互联网": "9019807",
    "液冷数据中心": "9024880",
    "AI智能体Manus": "9043089",
}


def _load_gt_overrides() -> Dict[str, Dict[str, str]]:
    overrides: Dict[str, Dict[str, str]] = {}
    if not GT_OVERRIDE_PATH.exists():
        return overrides
    for line in GT_OVERRIDE_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        raw_text = (obj.get("raw_text") or "").strip()
        gt_subject_key = str(obj.get("gt_subject_key") or "").strip()
        theme_name = str(obj.get("theme_name") or "").strip()
        if not raw_text or not gt_subject_key:
            continue
        overrides[raw_text] = {
            "expected_subject_key": gt_subject_key,
            "theme_name": theme_name or "",
        }
    return overrides


def _pg_kwargs() -> Dict[str, Any]:
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        "database": os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    }


def _parse_test_cases(limit: int) -> List[Dict[str, str]]:
    text = RAW_PATH.read_text(encoding="utf-8")
    parts = re.split(r"(?=测试集\d+:题材名称:)", text)
    rows: List[Dict[str, str]] = []
    gt_overrides = _load_gt_overrides()

    for part in parts:
        part = part.strip()
        if not part:
            continue
        lines = part.splitlines()
        header = lines[0].strip()
        match = re.match(r"测试集\d+:题材名称:(.+)", header)
        if not match:
            continue
        theme_name = match.group(1).strip()
        expected_subject_key = THEME_KEY_MAP[theme_name]

        seen_raws = set()
        for line in lines[1:]:
            value = line.strip()
            if not value.startswith("- "):
                continue
            raw_text = value[2:].strip().rstrip("*").strip()
            if not raw_text or raw_text in seen_raws:
                continue
            seen_raws.add(raw_text)
            override = gt_overrides.get(raw_text)
            rows.append(
                {
                    "theme_name": (override or {}).get("theme_name") or theme_name,
                    "expected_subject_key": (override or {}).get("expected_subject_key") or expected_subject_key,
                    "raw_text": raw_text,
                }
            )

    if len(rows) < limit:
        raise RuntimeError(f"原始测试样本不足 {limit} 条，当前 {len(rows)} 条")
    return rows[:limit]


class _RedisStructuredEventBus:
    def __init__(self, redis_client: redis.Redis, structured_stream: str):
        self.redis_client = redis_client
        self.structured_stream = structured_stream

    async def publish_to_stream(self, stream_key: str, data: Dict[str, Any]):
        target = self.structured_stream if stream_key == "stream:events:structured" else stream_key
        payload = {"payload": json.dumps(data, ensure_ascii=False)}
        return await self.redis_client.xadd(target, payload, maxlen=10000)


def _build_v2_payload(raw_text: str, news_id: str, sequence: int, batch_id: str, theme_name: str) -> Dict[str, Any]:
    return {
        "_t": "news",
        "_v": 2,
        "id": news_id,
        "t": "",
        "c": raw_text,
        "s": "cls",
        "d": "2026-03-01",
        "tm": "00:00:00",
        "_b": batch_id,
        "_s": sequence,
    }


async def _wait_for_news_raw(gateway: Any, external_news_id: str, timeout_s: float = 30.0) -> Optional[Dict[str, Any]]:
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
        messages = await redis_client.xread({stream_name: "0-0"}, count=500, block=1000)
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


def _build_report(details: List[Dict[str, Any]]) -> Dict[str, Any]:
    processed = len(details)
    top1_hits = sum(1 for row in details if row.get("top1_hit"))
    by_theme: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in details:
        by_theme[row["expected_subject_key"]].append(row)

    per_theme_metrics: List[Dict[str, Any]] = []
    for subject_key, rows in by_theme.items():
        total = len(rows)
        theme_name = rows[0]["expected_theme_name"]
        top1 = sum(1 for row in rows if row["top1_hit"])
        pred_counter = Counter(row["matched_subject_key"] for row in rows if row["matched_subject_key"])
        confusion = [
            {"pred_subject_key": key, "count": count}
            for key, count in pred_counter.items()
            if key != subject_key
        ]
        per_theme_metrics.append(
            {
                "gt_subject_key": subject_key,
                "gt_theme_name": theme_name,
                "total": total,
                "top1_hit": top1,
                "top1_accuracy": round(top1 / total, 4) if total else 0.0,
                "most_common_top1_pred": pred_counter.most_common(1)[0][0] if pred_counter else None,
                "most_common_top1_pred_count": pred_counter.most_common(1)[0][1] if pred_counter else 0,
                "confusion_top1": confusion,
            }
        )
    per_theme_metrics.sort(key=lambda x: x["gt_subject_key"])

    return {
        "events": SAMPLE_SIZE,
        "processed": processed,
        "top1_hits": top1_hits,
        "top1_accuracy": round(top1_hits / processed, 4) if processed else 0.0,
        "failed": sum(1 for row in details if row.get("status") == "failed"),
        "per_theme_metrics": per_theme_metrics,
        "details": details,
    }


async def main() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")

    run_id = uuid.uuid4().hex[:8]
    batch_id = f"p2_full_chain_100_{run_id}"
    raw_stream = "stream:news:raw"
    structured_stream = "stream:events:structured"
    decision_stream = "stream:events:decision"
    dead_letter_stream = "stream:dead:letter"
    consumer_group = f"theme_processors_p2_{run_id}"
    consumer_name = f"tp_fc100_{run_id}"

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

    samples = _parse_test_cases(SAMPLE_SIZE)
    created_news_raw_ids: List[int] = []
    created_news_event_ids: List[int] = []
    seen_decision_ids: set[str] = set()
    details: List[Dict[str, Any]] = []
    conn = await asyncpg.connect(**_pg_kwargs())

    try:
        print(f"开始真实全链路 100 条 QA，样本数={SAMPLE_SIZE}", flush=True)
        await _cleanup_previous_test_data(conn)
        await news_handler.start_storage_service()
        ok = await theme_processor.initialize()
        if not ok:
            raise RuntimeError("theme_processor 初始化失败")
        await theme_processor.start()

        for idx, sample in enumerate(samples, start=1):
            external_news_id = f"{batch_id}_{idx:03d}_{uuid.uuid4().hex[:6]}"
            payload = _build_v2_payload(
                raw_text=sample["raw_text"],
                news_id=external_news_id,
                sequence=idx,
                batch_id=batch_id,
                theme_name=sample["theme_name"],
            )

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
                        "title": stored_news.get("title") or "",
                        "content": stored_news.get("content") or sample["raw_text"],
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
                details.append(
                    {
                        "index": idx,
                        "status": "failed",
                        "stage": "news_stream_processor",
                        "theme_name": sample["theme_name"],
                        "expected_theme_name": sample["theme_name"],
                        "expected_subject_key": sample["expected_subject_key"],
                        "news_id": external_news_id,
                        "news_event_id": None,
                        "decision_type": None,
                        "action": None,
                        "matched_subject_key": "",
                        "matched_theme_name": None,
                        "confidence": None,
                        "reason_code": processor_result.get("error") or "news_stream_processor_failed",
                        "top1_hit": False,
                    }
                )
                _print_progress(
                    "structuring failed",
                    idx,
                    SAMPLE_SIZE,
                    str(processor_result.get("error") or "unknown_error"),
                )
                continue

            news_event_id = processor_result.get("news_event_id")
            if not news_event_id:
                details.append(
                    {
                        "index": idx,
                        "status": "failed",
                        "stage": "news_event_persistence",
                        "theme_name": sample["theme_name"],
                        "expected_theme_name": sample["theme_name"],
                        "expected_subject_key": sample["expected_subject_key"],
                        "news_id": external_news_id,
                        "news_event_id": None,
                        "decision_type": None,
                        "action": None,
                        "matched_subject_key": "",
                        "matched_theme_name": None,
                        "confidence": None,
                        "reason_code": "news_event_not_created",
                        "top1_hit": False,
                    }
                )
                _print_progress("news_event missing", idx, SAMPLE_SIZE)
                continue
            created_news_event_ids.append(int(news_event_id))
            _print_progress("news_event persisted", idx, SAMPLE_SIZE, f"event_id={news_event_id}")

            if not processor_result.get("structured_stream_published"):
                details.append(
                    {
                        "index": idx,
                        "status": "failed",
                        "stage": "structured_stream",
                        "theme_name": sample["theme_name"],
                        "expected_theme_name": sample["theme_name"],
                        "expected_subject_key": sample["expected_subject_key"],
                        "news_id": external_news_id,
                        "news_event_id": news_event_id,
                        "decision_type": None,
                        "action": None,
                        "matched_subject_key": "",
                        "matched_theme_name": None,
                        "confidence": None,
                        "reason_code": "structured_stream_not_published",
                        "top1_hit": False,
                    }
                )
                _print_progress("structured stream missing", idx, SAMPLE_SIZE, f"event_id={news_event_id}")
                continue
            _print_progress("structured event published", idx, SAMPLE_SIZE)

            new_decisions = await _wait_for_decisions(
                redis_client,
                decision_stream,
                expected_count=1,
                seen_ids=seen_decision_ids,
                timeout_s=180.0,
            )
            if not new_decisions:
                details.append(
                    {
                        "index": idx,
                        "status": "failed",
                        "stage": "decision_stream",
                        "theme_name": sample["theme_name"],
                        "expected_theme_name": sample["theme_name"],
                        "expected_subject_key": sample["expected_subject_key"],
                        "news_id": external_news_id,
                        "news_event_id": news_event_id,
                        "decision_type": None,
                        "action": None,
                        "matched_subject_key": "",
                        "matched_theme_name": None,
                        "confidence": None,
                        "reason_code": "decision_not_received",
                        "top1_hit": False,
                    }
                )
                _print_progress("decision missing", idx, SAMPLE_SIZE, f"event_id={news_event_id}")
                continue

            decision = new_decisions[0]
            match_result = decision.get("match_result", {}) or {}
            predicted = str(match_result.get("matched_subject_key") or "")
            top1_hit = predicted == sample["expected_subject_key"]
            details.append(
                {
                    "index": idx,
                    "status": "ok",
                    "stage": "decision_stream",
                    "theme_name": sample["theme_name"],
                    "expected_theme_name": sample["theme_name"],
                    "expected_subject_key": sample["expected_subject_key"],
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
            current_hits = sum(1 for row in details if row["top1_hit"])
            _print_progress(
                "decision received",
                idx,
                SAMPLE_SIZE,
                f"{decision.get('action')} -> {predicted} | top1={current_hits/idx:.4f}",
            )

        report = _build_report(details)
        OUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            json.dumps(
                {
                    "events": report["events"],
                    "processed": report["processed"],
                    "top1_hits": report["top1_hits"],
                    "top1_accuracy": report["top1_accuracy"],
                    "preview_path": str(OUT_PATH),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

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

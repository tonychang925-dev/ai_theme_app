import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import asyncpg
import redis.asyncio as redis

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway
from database_service.streams.handlers.theme_processor import ThemeProcessor


RAW_PATH = Path("/Users/admin/Desktop/ai_theme_app/evaluate_service/data/raw/test_cases.txt")
OUT_PATH = Path("/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_theme_processor_integration_30.preview.json")
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


def _load_first_30_ai_ar_raws() -> list[str]:
    text = RAW_PATH.read_text(encoding="utf-8")
    match = re.search(r"测试集1:题材名称:AI/AR眼镜\n(.*?)(?:\n测试集2:题材名称:|\Z)", text, re.S)
    assert match, "未找到 AI/AR眼镜 测试段"
    block = match.group(1)
    rows: list[str] = []
    for line in block.splitlines():
        value = line.strip()
        if not value.startswith("- "):
            continue
        value = value[2:].strip().rstrip("*").strip()
        if value:
            rows.append(value)
    assert len(rows) >= 30, f"AI/AR眼镜 原始样本不足 30 条，当前 {len(rows)}"
    return rows[:30]


async def _wait_for_event_results(
    redis_client,
    structured_stream: str,
    decision_stream: str,
    dead_letter_stream: str,
    consumer_group: str,
    expected_event_ids: list[int],
    timeout_s: float = 600.0,
) -> tuple[list[dict], list[dict], list[int]]:
    import time

    started = time.time()
    decisions_by_event: dict[int, dict] = {}
    dead_letters_by_event: dict[int, dict] = {}
    seen_decision_ids = set()
    seen_dead_ids = set()
    expected = {int(x) for x in expected_event_ids}

    while time.time() - started < timeout_s:
        messages = await redis_client.xread({decision_stream: "0-0"}, count=500, block=1000)
        for _stream, message_list in messages:
            for message_id, payload in message_list:
                if message_id in seen_decision_ids:
                    continue
                seen_decision_ids.add(message_id)
                raw = payload.get("decision")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                obj = json.loads(raw)
                try:
                    event_id = int(obj.get("event_id"))
                except Exception:
                    continue
                if event_id in expected and event_id not in decisions_by_event:
                    decisions_by_event[event_id] = obj

        dead_messages = await redis_client.xread({dead_letter_stream: "0-0"}, count=500, block=200)
        for _stream, message_list in dead_messages:
            for message_id, payload in message_list:
                if message_id in seen_dead_ids:
                    continue
                seen_dead_ids.add(message_id)
                raw = payload.get("payload") or payload.get("decision") or payload.get("error_data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    obj = json.loads(raw)
                except Exception:
                    obj = {"raw": raw}
                try:
                    event_id = int(obj.get("event_id"))
                except Exception:
                    continue
                if event_id in expected and event_id not in dead_letters_by_event:
                    dead_letters_by_event[event_id] = obj

        resolved = set(decisions_by_event) | set(dead_letters_by_event)
        if resolved >= expected:
            break

        pending_summary = await redis_client.xpending(structured_stream, consumer_group)
        pending_count = pending_summary["pending"] if isinstance(pending_summary, dict) else pending_summary[0]
        print(
            json.dumps(
                {
                    "wait_progress": {
                        "resolved": len(resolved),
                        "expected": len(expected),
                        "decisions": len(decisions_by_event),
                        "dead_letters": len(dead_letters_by_event),
                        "pending_structured": pending_count,
                    }
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        await asyncio.sleep(1.0)

    missing = sorted(expected - (set(decisions_by_event) | set(dead_letters_by_event)))
    return list(decisions_by_event.values()), list(dead_letters_by_event.values()), missing


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
        await asyncio.sleep(2.0)

        raws = _load_first_30_ai_ar_raws()
        for idx, raw in enumerate(raws, start=1):
            external_news_id = f"tp30_{idx}_{uuid.uuid4().hex[:8]}"
            title = "AI/AR眼镜相关新闻"
            news_data = {
                "news_id": external_news_id,
                "title": title,
                "content": raw,
                "source": "pytest_p2_phase0_theme_processor_30",
                "publish_date": "2026-03-01",
                "metadata": {"source_case_index": idx, "ground_truth_theme": "AI/AR眼镜"},
            }
            await processor.gateway.create_news(news_data)
            news_row = await processor.gateway.get_news(external_news_id)
            created_news_raw_ids.append(int(news_row["id"]))

            summary = raw[:180]
            event_payload = {
                "news_id": int(news_row["id"]),
                "event_type": "行业新闻",
                "impact_industries": ["AI/AR眼镜"],
                "direction": "利好",
                "confidence": 0.95,
                "summary": summary,
                "theme_directive": {},
                "theme_directive_processed": False,
                "severity_score": 0.8,
                "source_weight": 1.0,
                "event_time": "2026-03-01 00:00:00",
                "entities": [],
                "causal_claim": [summary] if summary else [],
                "evidence_set": {"core_concepts": ["AI眼镜", "AR眼镜", "智能眼镜"]},
                "raw_event_json": {
                    "title": title,
                    "content": raw,
                    "source_case_index": idx,
                    "ground_truth_theme": "AI/AR眼镜",
                },
            }
            event_id = await processor.gateway.create_news_event(event_payload)
            created_news_event_ids.append(int(event_id))
            await redis_client.xadd(
                structured_stream,
                {"payload": json.dumps({"event_id": int(event_id)}, ensure_ascii=False)},
                maxlen=5000,
            )
            await asyncio.sleep(0.05)

        decisions, dead_letters, missing_event_ids = await _wait_for_event_results(
            redis_client,
            structured_stream=structured_stream,
            decision_stream=decision_stream,
            dead_letter_stream=dead_letter_stream,
            consumer_group=consumer_group,
            expected_event_ids=created_news_event_ids,
            timeout_s=600.0,
        )
        preview: list[dict] = []
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
        hits = sum(1 for row in preview if row["top1_hit"])
        print(
            json.dumps(
                {
                    "events": len(created_news_event_ids),
                    "resolved_events": len(decisions) + len(dead_letters),
                    "decision_events": len(decisions),
                    "dead_letter_events": len(dead_letters),
                    "missing_event_ids": missing_event_ids,
                    "top1_hits": hits,
                    "top1_accuracy": hits / len(preview) if preview else 0.0,
                    "preview_path": str(OUT_PATH),
                    "dead_letter_count": len(await redis_client.xrange(dead_letter_stream, min='-', max='+')),
                },
                ensure_ascii=False,
            )
        )

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


if __name__ == "__main__":
    asyncio.run(main())

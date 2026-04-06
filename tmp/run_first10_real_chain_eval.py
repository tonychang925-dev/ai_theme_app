import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "theme_service"))

from database_service.streams.gateway_integration import get_gateway
from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.handlers.theme_processor import ThemeProcessor


RAW_DATASET = PROJECT_ROOT / "evaluate_service/data/raw/test_cases.txt"
GT_JSONL = PROJECT_ROOT / "structured_events_with_gt.jsonl"
OUTPUT_JSON = PROJECT_ROOT / "tmp/first10_real_chain_eval.report.json"


def load_first_10_raw_cases() -> List[str]:
    text = RAW_DATASET.read_text(encoding="utf-8")
    lines = [line.strip() for line in text.splitlines()]
    cases: List[str] = []
    in_first_block = False
    for line in lines:
        if line.startswith("测试集1:"):
            in_first_block = True
            continue
        if in_first_block and line.startswith("测试集2:"):
            break
        if in_first_block and line.startswith("- "):
            cases.append(line[2:].strip().rstrip("*").strip())
        if len(cases) >= 10:
            break
    return cases


def load_first_10_gt() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    with GT_JSONL.open("r", encoding="utf-8") as f:
        for _ in range(10):
            line = f.readline()
            if not line:
                break
            rows.append(json.loads(line))
    return rows


def build_v2_raw_payload(raw_text: str, news_id: str) -> Dict[str, Any]:
    date_str = "2025-01-01"
    content = raw_text
    title = raw_text[:60]
    return {
        "_t": "news",
        "_v": 2,
        "id": news_id,
        "t": title,
        "c": content,
        "s": "cls",
        "d": date_str,
        "tm": "00:00:00",
        "_b": "p2_phase0_first10",
    }


async def fetch_stream_entry(redis_client, stream_name: str, message_id: str) -> Optional[Dict[str, Any]]:
    rows = await redis_client.xrange(stream_name, min=message_id, max=message_id, count=1)
    if not rows:
        return None
    mid, fields = rows[0]
    return {"id": mid, "data": fields}


def decode_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except Exception:
            return {}
    return {}


def unwrap_payload_dict(payload: Any) -> Dict[str, Any]:
    data = decode_payload(payload)
    if isinstance(data, dict) and isinstance(data.get("payload"), dict):
        return data["payload"]
    return data


async def find_structured_stream_message(redis_client, event_id: int) -> Optional[Dict[str, Any]]:
    rows = await redis_client.xrevrange("stream:events:structured", count=50)
    for mid, fields in rows:
        payload = unwrap_payload_dict(fields.get("payload"))
        if int(payload.get("event_id") or 0) == int(event_id):
            return {"id": mid, "data": fields}
    return None


async def find_decision_message(redis_client, event_id: int) -> Optional[Dict[str, Any]]:
    rows = await redis_client.xrevrange("stream:events:decision", count=50)
    for mid, fields in rows:
        if str(fields.get("event_id")) == str(event_id):
            decision_raw = fields.get("decision")
            decision = decode_payload(decision_raw)
            return {"id": mid, "fields": fields, "decision": decision}
    return None


async def main() -> None:
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")

    os.environ["POSTGRES_DATABASE"] = os.getenv("POSTGRES_DATABASE", "stock_data_test")

    raw_cases = load_first_10_raw_cases()
    gt_rows = load_first_10_gt()
    if len(raw_cases) != 10 or len(gt_rows) != 10:
        raise RuntimeError(f"样本或GT不足: raw={len(raw_cases)}, gt={len(gt_rows)}")

    stream_gateway = await get_gateway(enable_retry=True, retry_config={"max_retries": 2})
    base_gateway = stream_gateway.base_gateway
    redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
    await redis_client.ping()

    for stream_name in (
        "stream:news:raw",
        "stream:events:structured",
        "stream:events:decision",
        "stream:events:pending",
        "stream:dead:letter",
    ):
        await redis_client.delete(stream_name)

    handler = NewsStreamHandler(stream_gateway, base_gateway)
    processor = NewsStreamProcessor(
        stream_gateway,
        config={"database_gateway": base_gateway},
    )
    theme_processor = ThemeProcessor(enable_classification_first=False)
    await theme_processor.initialize()
    await theme_processor._create_consumer_groups()

    run_id = f"first10_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    details: List[Dict[str, Any]] = []

    for idx, (raw_text, gt_row) in enumerate(zip(raw_cases, gt_rows), start=1):
        external_news_id = f"{run_id}_{idx:03d}"
        v2_payload = build_v2_raw_payload(raw_text, external_news_id)
        raw_wrapper = {"payload": json.dumps({"payload": v2_payload}, ensure_ascii=False)}

        raw_msg_id = await redis_client.xadd("stream:news:raw", raw_wrapper, maxlen=10000)
        raw_message = await fetch_stream_entry(redis_client, "stream:news:raw", raw_msg_id)
        if not raw_message:
            raise RuntimeError(f"无法读取 raw stream 消息: {raw_msg_id}")

        storage_result = await handler._process_storage_message(raw_message)
        if not storage_result.get("storage_success"):
            raise RuntimeError(f"news_stream_handler 失败: {storage_result}")

        stored_news = await base_gateway.get_news(external_news_id)
        if not stored_news:
            raise RuntimeError(f"news_raw 不存在: {external_news_id}")

        stored_msg_data = {"payload": {"news_data": stored_news}}
        processor_result = await processor.process_stream_message(raw_msg_id, stored_msg_data)
        if not processor_result.get("success"):
            raise RuntimeError(f"news_stream_processor 失败: {processor_result}")

        news_event_id = processor_result.get("news_event_id")
        if not news_event_id:
            raise RuntimeError(f"未生成 news_event_id: {processor_result}")

        structured_message = await find_structured_stream_message(redis_client, int(news_event_id))
        if not structured_message:
            raise RuntimeError(f"未找到 structured stream 消息: event_id={news_event_id}")

        await theme_processor._process_message_structured(
            "structured",
            "stream:events:structured",
            structured_message["id"],
            structured_message["data"],
        )

        decision_message = await find_decision_message(redis_client, int(news_event_id))
        if not decision_message:
            raise RuntimeError(f"未找到 decision stream 消息: event_id={news_event_id}")

        decision = decision_message["decision"]
        match_result = decision.get("match_result", {}) or {}
        predicted = (
            match_result.get("matched_subject_key")
            or (decision.get("theme_data") or {}).get("subject_key")
            or ""
        )
        gt_subject_key = str(gt_row.get("gt_subject_key") or "")

        details.append(
            {
                "idx": idx,
                "news_id": external_news_id,
                "raw_text": raw_text,
                "news_event_id": news_event_id,
                "gt_subject_key": gt_subject_key,
                "pred_subject_key": str(predicted),
                "top1_hit": str(predicted) == gt_subject_key,
                "decision": match_result.get("decision") or decision.get("decision_type"),
                "matched_theme_name": match_result.get("matched_theme_name") or (decision.get("theme_data") or {}).get("name", ""),
                "confidence": match_result.get("confidence", decision.get("confidence")),
                "reason_code": match_result.get("reason_code", decision.get("reason")),
            }
        )

    hits = sum(1 for row in details if row["top1_hit"])
    report = {
        "run_id": run_id,
        "events": len(details),
        "processed": len(details),
        "top1_accuracy": hits / max(len(details), 1),
        "details": details,
    }
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"events": report["events"], "processed": report["processed"], "top1_accuracy": report["top1_accuracy"]}, ensure_ascii=False))
    print(str(OUTPUT_JSON))


if __name__ == "__main__":
    asyncio.run(main())

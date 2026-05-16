from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import (
        ensure_no_gold_leak,
        read_jsonl,
        strip_for_redis,
        write_json,
    )
else:
    from .common import ensure_no_gold_leak, read_jsonl, strip_for_redis, write_json


def build_stream_payload(row: dict[str, Any], *, run_id: str, trade_date: str) -> dict[str, str]:
    ensure_no_gold_leak(row, context=row.get("case_id", "news"))
    if row.get("run_id") != run_id:
        raise ValueError(f"run_id 不一致: row={row.get('run_id')} expected={run_id}")
    if str(row.get("publish_date")) != trade_date:
        raise ValueError(f"publish_date 不一致: row={row.get('publish_date')} expected={trade_date}")
    payload = {
        "news_id": row.get("news_id") or row.get("external_id"),
        "external_id": row.get("external_id"),
        "title": row.get("title"),
        "content": row.get("content"),
        "source": row.get("source", "akshare_replay"),
        "source_channel": row.get("source_channel", "akshare_replay"),
        "publish_date": row.get("publish_date"),
        "publish_time": row.get("publish_time"),
        "collected_at": row.get("collected_at"),
        "url": row.get("url"),
        "run_id": row.get("run_id"),
        "case_id": row.get("case_id"),
        "type": row.get("type", "raw_news"),
    }
    ensure_no_gold_leak(payload, context=row.get("case_id", "stream_payload"))
    return {str(key): strip_for_redis(value) for key, value in payload.items() if value is not None}


async def replay_rows(
    rows: list[dict[str, Any]],
    *,
    redis_url: str,
    stream: str,
    run_id: str,
    trade_date: str,
    limit: int | None = None,
) -> dict[str, Any]:
    import redis.asyncio as redis

    client = redis.Redis.from_url(redis_url, decode_responses=True)
    injected: list[dict[str, str]] = []
    try:
        for row in rows[:limit]:
            payload = build_stream_payload(row, run_id=run_id, trade_date=trade_date)
            stream_id = await client.xadd(stream, payload)
            injected.append(
                {
                    "case_id": payload.get("case_id", ""),
                    "external_id": payload.get("external_id", ""),
                    "stream_id": stream_id,
                }
            )
    finally:
        await client.aclose()
    return {
        "run_id": run_id,
        "trade_date": trade_date,
        "stream": stream,
        "input_count": len(rows),
        "injected_count": len(injected),
        "items": injected,
    }


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="将 input_news.jsonl 回放为 AkShare 原始新闻 Redis Stream。")
    parser.add_argument("--input", required=True)
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/0")
    parser.add_argument("--stream", default="stream:news:raw")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    input_path = Path(args.input)
    rows = read_jsonl(input_path)
    result = await replay_rows(
        rows,
        redis_url=args.redis_url,
        stream=args.stream,
        run_id=args.run_id,
        trade_date=args.trade_date,
        limit=args.limit,
    )
    write_json(input_path.parent / "injection_result.json", result)
    print(f"injected_count={result['injected_count']} stream={args.stream}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()


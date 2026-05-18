from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import require_safe_db
else:
    from .common import require_safe_db


async def run_services(args: argparse.Namespace) -> None:
    import redis.asyncio as redis

    from database_service.gateway import DatabaseGateway
    from database_service.managers.redis_stream_bus import UnifiedRedisStreamBus
    from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
    from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor

    require_safe_db(args.db_name, allow_production=args.allow_production)
    os.environ.setdefault("DB_TYPE", "postgresql")
    os.environ.setdefault("PG_DATABASE", args.db_name)
    os.environ.setdefault("DB_NAME", args.db_name)
    os.environ.setdefault("REPLAY_DB_NAME", args.db_name)

    redis_client = redis.Redis.from_url(args.redis_url, decode_responses=True)
    if not args.storage_group:
        args.storage_group = f"news_storage_handlers_e2e_{args.run_id}"
    if not args.processor_group:
        args.processor_group = f"news_business_processors_e2e_{args.run_id}"
    await _ensure_group_at_tail(redis_client, "stream:news:raw", args.storage_group)
    await _ensure_group_at_tail(redis_client, "stream:events:normal", args.processor_group)
    stream_config = SimpleNamespace(
        redis=SimpleNamespace(
            consumer_group=f"pm_e2e:{args.run_id}",
            stream_max_length=10000,
        )
    )
    stream_bus = UnifiedRedisStreamBus(redis_client, config=stream_config)
    gateway = await DatabaseGateway.initialize(auto_warm_cache=False)

    storage_handler = NewsStreamHandler(
        stream_bus=stream_bus,
        database_gateway=gateway,
        config={
            "consumer_group": args.storage_group,
            "stream_name": args.raw_stream,
            "batch_size": args.batch_size,
            "block_time": 3000,
        },
    )
    processor = NewsStreamProcessor(
        event_bus=stream_bus,
        config={
            "database_gateway": gateway,
            "processor_group": args.processor_group,
            "processor_name": f"news_processor_e2e_{args.run_id}",
            "enable_ai_analysis": True,
            "enable_local_triage": True,
            "triage_mode": "hybrid",
            "triage_block_on_skip": False,
            "triage_pass_threshold": 0.03,
            "triage_skip_threshold": -0.05,
            "batch_processing": True,
            "batch_size": args.batch_size,
            "run_id_filter": args.run_id,
        },
    )

    await storage_handler.start_storage_service()
    await processor.start_business_processing()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, signame), stop_event.set)
        except NotImplementedError:
            pass

    logging.info(
        "Raw news E2E services running: raw=%s storage_group=%s processor_group=%s",
        args.raw_stream,
        args.storage_group,
        args.processor_group,
    )
    try:
        await stop_event.wait()
    finally:
        storage_handler.running = False
        processor.running = False
        for task in [storage_handler.handler_task, processor.processor_task]:
            if task:
                task.cancel()
        await asyncio.gather(
            *[task for task in [storage_handler.handler_task, processor.processor_task] if task],
            return_exceptions=True,
        )
        await gateway.close()
        await redis_client.aclose()


async def _ensure_group_at_tail(redis_client, stream: str, group: str) -> None:
    try:
        await redis_client.xgroup_create(stream, group, id="$", mkstream=True)
        logging.info("Created consumer group at tail: %s/%s", stream, group)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
        logging.info("Consumer group already exists: %s/%s", stream, group)
        await redis_client.xgroup_setid(stream, group, "$")
        logging.info("Moved consumer group to tail: %s/%s", stream, group)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动盘前必读 E2E raw news 入库与结构化服务。")
    parser.add_argument("--db-name", default=os.getenv("PG_DATABASE") or os.getenv("DB_NAME") or "stock_data")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
    parser.add_argument("--raw-stream", default="stream:news:raw")
    parser.add_argument("--storage-group")
    parser.add_argument("--processor-group")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--allow-production", action="store_true")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run_services(build_parser().parse_args()))


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
from pathlib import Path
from urllib.parse import urlparse

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import require_safe_db
else:
    from .common import require_safe_db


async def _ensure_group_at_tail(client, stream: str, group: str) -> None:
    try:
        await client.xgroup_create(stream, group, id="$", mkstream=True)
        logging.info("Created consumer group at tail: %s/%s", stream, group)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
        logging.info("Consumer group already exists: %s/%s", stream, group)


def _redis_host_port(redis_url: str) -> tuple[str, int]:
    parsed = urlparse(redis_url)
    return parsed.hostname or "127.0.0.1", parsed.port or 6379


async def run_services(args: argparse.Namespace) -> None:
    import redis.asyncio as redis

    from database_service.streams.gateway_integration import get_gateway
    from database_service.streams.handlers.DecisionExecutor import DecisionExecutor
    from database_service.streams.handlers.theme_processor import ThemeProcessor

    require_safe_db(args.db_name, allow_production=args.allow_production)
    os.environ.setdefault("DB_TYPE", "postgresql")
    os.environ.setdefault("PG_DATABASE", args.db_name)
    os.environ.setdefault("DB_NAME", args.db_name)
    os.environ.setdefault("REPLAY_DB_NAME", args.db_name)

    host, port = _redis_host_port(args.redis_url)
    redis_client = redis.Redis.from_url(args.redis_url, decode_responses=True)

    theme_group = args.theme_consumer_group or f"theme_processors_e2e_{args.run_id}"
    await _ensure_group_at_tail(redis_client, args.structured_stream, theme_group)
    await _ensure_group_at_tail(redis_client, args.decision_stream, args.decision_consumer_group)

    gateway = await get_gateway(enable_retry=True)
    processor = ThemeProcessor(
        redis_host=host,
        redis_port=port,
        consumer_name=f"theme_processor_e2e_{args.run_id}",
        enable_clustering=False,
        enable_classification_first=True,
        config={
            "consumer_group": theme_group,
            "stream_structured": args.structured_stream,
            "stream_decision": args.decision_stream,
            "stream_pending": args.pending_stream,
            "stream_dead_letter": args.dead_letter_stream,
        },
    )
    await processor.initialize()

    executor = DecisionExecutor(
        redis_client,
        gateway,
        consumer_name=f"decision_executor_e2e_{args.run_id}",
    )
    executor.decision_stream = args.decision_stream
    executor.consumer_group = args.decision_consumer_group
    executor.dead_letter_stream = args.dead_letter_stream

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signame in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, signame), stop_event.set)
        except NotImplementedError:
            pass

    tasks = []
    tasks.extend(await processor.start())
    tasks.extend(await executor.start())
    logging.info(
        "Phase0 decision services running: structured=%s decision=%s theme_group=%s decision_group=%s",
        args.structured_stream,
        args.decision_stream,
        theme_group,
        args.decision_consumer_group,
    )

    try:
        await stop_event.wait()
    finally:
        processor.running = False
        executor.running = False
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await redis_client.aclose()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="启动盘前必读 E2E Phase0 决策闭环服务。")
    parser.add_argument("--db-name", default=os.getenv("PG_DATABASE") or os.getenv("DB_NAME") or "stock_data")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--redis-url", default=os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
    parser.add_argument("--structured-stream", default="stream:events:structured")
    parser.add_argument("--decision-stream", default="stream:events:decision")
    parser.add_argument("--pending-stream", default="stream:events:pending")
    parser.add_argument("--dead-letter-stream", default="stream:dead:letter")
    parser.add_argument("--theme-consumer-group")
    parser.add_argument("--decision-consumer-group", default="decision_executors")
    parser.add_argument("--allow-production", action="store_true")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run_services(build_parser().parse_args()))


if __name__ == "__main__":
    main()

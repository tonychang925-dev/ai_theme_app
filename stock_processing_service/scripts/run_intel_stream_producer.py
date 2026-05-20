"""P0-E: Intel Stream Producer Runtime.

Periodically polls structured_intel_event.stream_status='pending' and produces
news_event + stream:events:structured via IntelStreamProducer.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from stock_processing_service.application.services.intel_stream_producer import (
    IntelStreamProducer,
)

CN_TZ = timezone(timezone.utc)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run IntelStreamProducer periodic loop."
    )
    parser.add_argument("--poll-interval-seconds", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/0")
    parser.add_argument("--stream", default="stream:events:structured")
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--status-path", default=None)
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    import os

    db_name = args.db_name or os.environ.get("PG_DATABASE", "stock_data_test")
    os.environ.setdefault("PG_DATABASE", db_name)
    os.environ.setdefault("DB_NAME", db_name)
    os.environ.setdefault("DB_TYPE", "postgresql")

    import redis.asyncio as aioredis

    from database_service.gateway import DatabaseGateway
    from database_service.config import DatabaseConfig, DatabaseType

    redis_client = aioredis.Redis.from_url(args.redis_url, decode_responses=True)

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=db_name)
    gateway = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)

    run_id = args.run_id or os.environ.get("RUN_ID", f"intel_producer_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")

    producer = IntelStreamProducer(
        gateway=gateway,
        redis_client=redis_client,
        stream_name=args.stream,
        run_id=run_id,
    )

    status_path = Path(args.status_path) if args.status_path else None
    stats = {
        "running": True,
        "run_id": run_id,
        "produced_count": 0,
        "failed_count": 0,
        "last_produce_at": None,
        "last_error": None,
    }

    def _write_stats():
        if status_path:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    try:
        while True:
            try:
                count = await producer.produce_batch(limit=args.batch_size)
                stats["produced_count"] += count
                stats["last_produce_at"] = datetime.now(timezone.utc).isoformat()
                stats["last_error"] = None
                if count > 0:
                    logging.info("IntelStreamProducer: produced %s events", count)
            except Exception as exc:
                stats["failed_count"] += 1
                stats["last_error"] = str(exc)
                logging.exception("IntelStreamProducer loop failed")

            _write_stats()

            if args.once:
                break
            await asyncio.sleep(args.poll_interval_seconds)
    finally:
        stats["running"] = False
        _write_stats()
        await redis_client.aclose()
        close_fn = getattr(gateway, "close", None)
        if callable(close_fn):
            await close_fn()


if __name__ == "__main__":
    asyncio.run(async_main())

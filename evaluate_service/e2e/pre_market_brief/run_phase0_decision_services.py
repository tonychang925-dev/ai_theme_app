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


async def _ensure_group_at_tail(client, stream: str, group: str, *, reset_to_latest: bool = False, run_id: str = "") -> None:
    """创建或复用 consumer group，默认从上次位置继续（不再丢弃积压）。

    仅在 reset_to_latest=True 或首次创建时从 $ 开始。
    旧行为每次重启都 reset 到 $ 导致历史积压永久丢失。
    """
    start_id = "$" if reset_to_latest else "0"
    try:
        await client.xgroup_create(stream, group, id=start_id, mkstream=True)
        logging.info("Created consumer group: %s/%s start_id=%s", stream, group, start_id)
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise
        # Group already exists — DO NOT reset; continue from last position
        logging.info("Consumer group already exists: %s/%s (keeping position)", stream, group)

    # With fixed consumer names, remove all existing consumers at startup.
    # Our process will recreate the consumer naturally via XREADGROUP.
    zombie_count = 0
    orphaned_pending = 0
    try:
        consumers = await client.xinfo_consumers(stream, group)
        for c in consumers:
            orphaned_pending += int(c.get("pending", 0))
            try:
                await client.xgroup_delconsumer(stream, group, c["name"])
                zombie_count += 1
            except Exception:
                pass
        if zombie_count:
            logging.warning(
                "Cleaned %d existing consumers from %s/%s (orphaned pending=%d)",
                zombie_count, stream, group, orphaned_pending,
            )
    except Exception as e:
        logging.debug("Consumer cleanup skipped for %s/%s: %s", stream, group, e)


def _redis_host_port(redis_url: str) -> tuple[str, int]:
    parsed = urlparse(redis_url)
    return parsed.hostname or "127.0.0.1", parsed.port or 6379


async def run_services(args: argparse.Namespace) -> None:
    import redis.asyncio as redis

    # Create stop_event early so parent watchdog triggers clean shutdown
    stop_event = asyncio.Event()

    # P1-C1: parent watchdog — triggers clean shutdown (finally + self-cleanup)
    parent_pid = int(os.environ.get("REALTIME_PARENT_PID", "0"))
    if parent_pid:
        asyncio.create_task(_watch_parent(parent_pid, stop_event))

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

    # P1-C-pre: realtime 使用稳定 group 名 + clean consumer 前缀
    if args.run_id and args.run_id.startswith("realtime_"):
        theme_group = args.theme_consumer_group or "theme_processor_realtime"
        decision_group = args.decision_consumer_group or "decision_executor_realtime"
        _consumer_prefix = "realtime"
    else:
        theme_group = args.theme_consumer_group or f"theme_processors_e2e_{args.run_id}"
        decision_group = args.decision_consumer_group or f"decision_executors_e2e_{args.run_id}"
        _consumer_prefix = "e2e"
    await _ensure_group_at_tail(redis_client, args.structured_stream, theme_group, run_id=args.run_id)
    await _ensure_group_at_tail(redis_client, args.decision_stream, decision_group, run_id=args.run_id)

    gateway = await get_gateway(enable_retry=True)
    processor = ThemeProcessor(
        redis_host=host,
        redis_port=port,
        consumer_name=f"theme_processor_{_consumer_prefix}_worker",
        enable_clustering=False,
        enable_classification_first=True,
        config={
            "consumer_group": theme_group,
            "stream_structured": args.structured_stream,
            "stream_decision": args.decision_stream,
            "stream_pending": args.pending_stream,
            "stream_dead_letter": args.dead_letter_stream,
            # Phase 4F: realtime 生产不设 run_id 过滤，所有 structured 消息均需处理
            "run_id_filter": None if (args.run_id and args.run_id.startswith("realtime_")) else args.run_id,
            "require_news_id": True,
            # P0-B2: batch 间延迟(ms)，控制 CPU 占用
            "batch_delay_ms": int(os.environ.get("PHASE0_BATCH_DELAY_MS", "100")),
        },
    )
    await processor.initialize()

    executor = DecisionExecutor(
        redis_client,
        gateway,
        consumer_name=f"decision_executor_{_consumer_prefix}_worker",
    )
    executor.decision_stream = args.decision_stream
    executor.consumer_group = decision_group
    executor.dead_letter_stream = args.dead_letter_stream

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
        decision_group,
    )

    try:
        await stop_event.wait()
    finally:
        processor.running = False
        executor.running = False
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        # Phase 6A: self-cleanup — remove our consumers (prefix-matched) on exit
        for _stream, _group, _prefix in [
            (args.structured_stream, theme_group, f"theme_processor_{_consumer_prefix}_{args.run_id}"),
            (args.decision_stream, theme_group, f"theme_processor_{_consumer_prefix}_{args.run_id}"),
            (args.decision_stream, decision_group, f"decision_executor_{_consumer_prefix}_{args.run_id}"),
            (args.pending_stream, decision_group, f"decision_executor_{_consumer_prefix}_{args.run_id}"),
        ]:
            try:
                consumers = await redis_client.xinfo_consumers(_stream, _group)
                for c in consumers:
                    cname = c.get("name", "")
                    if cname.startswith(_prefix):
                        await redis_client.xgroup_delconsumer(_stream, _group, cname)
                        logging.info("Self-cleanup: removed consumer %s from %s/%s", cname, _stream, _group)
            except Exception:
                pass

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
    parser.add_argument("--decision-consumer-group")
    parser.add_argument("--allow-production", action="store_true")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run_services(build_parser().parse_args()))


async def _watch_parent(parent_pid: int, stop_event: asyncio.Event, interval: float = 5.0) -> None:
    """Phase 6A: parent 退出时通过 stop_event 触发正常清理，不再 os._exit。"""
    import os as _os
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass
        try:
            _os.kill(parent_pid, 0)
        except (ProcessLookupError, PermissionError):
            logging.warning("parent pid %d died, triggering clean shutdown", parent_pid)
            stop_event.set()
            return


if __name__ == "__main__":
    main()

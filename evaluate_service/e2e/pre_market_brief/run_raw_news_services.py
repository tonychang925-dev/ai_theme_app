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

    # Create stop_event early so parent watchdog triggers clean shutdown
    stop_event = asyncio.Event()

    # P1-C1: parent watchdog — triggers clean shutdown (finally + self-cleanup)
    parent_pid = int(os.environ.get("REALTIME_PARENT_PID", "0"))
    if parent_pid:
        asyncio.create_task(_watch_parent(parent_pid, stop_event))

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
    # P1-C-pre: realtime 使用稳定 group 名，避免 e2e 语义泄漏和 zombie group 堆积
    if args.run_id and args.run_id.startswith("realtime_"):
        if not args.storage_group:
            args.storage_group = "news_storage_realtime"
        if not args.processor_group:
            args.processor_group = "news_processor_realtime"
    else:
        if not args.storage_group:
            args.storage_group = f"news_storage_handlers_e2e_{args.run_id}"
        if not args.processor_group:
            args.processor_group = f"news_business_processors_e2e_{args.run_id}"
    await _ensure_group_clean_start(redis_client, "stream:news:raw", args.storage_group)
    await _ensure_group_clean_start(redis_client, "stream:events:normal", args.processor_group)
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
            "triage_skip_threshold": -0.02,
            "batch_processing": True,
            "batch_size": args.batch_size,
            "run_id_filter": args.run_id,
        },
    )

    await storage_handler.start_storage_service()
    await processor.start_business_processing()

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

        # Phase 6A: self-cleanup — remove our consumers from groups on exit
        for _stream, _group, _cname in [
            ("stream:news:raw", args.storage_group,
             storage_handler.consumer_config.get("consumer_name", "")),
            ("stream:events:normal", args.processor_group,
             processor.processor_config.get("processor_name", "")),
        ]:
            if _cname:
                try:
                    await redis_client.xgroup_delconsumer(_stream, _group, _cname)
                    logging.info("Self-cleanup: removed consumer %s from %s/%s", _cname, _stream, _group)
                except Exception:
                    pass

        await gateway.close()
        await redis_client.aclose()


async def _ensure_group_clean_start(redis_client, stream: str, group: str) -> None:
    """Phase 6A: 创建/复用 consumer group，live mode 从最新开始并清理僵尸。

    - live mode 默认从 "$" 创建，不再回放历史积压
    - lag > 50% 自动重置到 $
    - 僵尸清理：只 XGROUP DELCONSUMER，不 XACK pending（防止丢消息）
    """
    import os as _os
    start_mode = _os.environ.get("REALTIME_STREAM_START_MODE", "latest").lower()
    start_id = "$" if start_mode == "latest" else "0"
    try:
        await redis_client.xgroup_create(stream, group, id=start_id, mkstream=True)
        logging.info("Created consumer group %s/%s start_id=%s mode=%s", stream, group, start_id, start_mode)
        return
    except Exception as exc:
        if "BUSYGROUP" not in str(exc):
            raise

    logging.info("Consumer group already exists: %s/%s (mode=%s), checking health...", stream, group, start_mode)

    # Live mode: auto-reset if hopelessly behind
    if start_mode == "latest":
        try:
            stream_info = await redis_client.xinfo_stream(stream)
            stream_len = stream_info.get("length", 0)
            group_info_list = await redis_client.xinfo_groups(stream)
            for gi in group_info_list:
                if gi.get("name") == group:
                    lag = gi.get("lag", 0)
                    if stream_len > 0 and lag > stream_len * 0.5:
                        logging.warning(
                            "Group %s/%s lag=%d > 50%% of stream_len=%d, resetting to $",
                            stream, group, lag, stream_len,
                        )
                        await redis_client.xgroup_setid(stream, group, "$")
                        # Drop all old consumers since their pending is now orphaned
                        try:
                            consumers = await redis_client.xinfo_consumers(stream, group)
                            for c in consumers:
                                try:
                                    await redis_client.xgroup_delconsumer(stream, group, c.get("name", ""))
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        logging.info("Group %s/%s reset to $", stream, group)
                    break
        except Exception as e:
            logging.debug("Group lag check skipped: %s", e)

    # Clean up zombie consumers (idle > 60s) — never ACK pending
    zombie_count = 0
    orphaned_pending = 0
    try:
        consumers = await redis_client.xinfo_consumers(stream, group)
        for c in consumers:
            idle_ms = int(c.get("idle", 0))
            if idle_ms > 60000:
                orphaned_pending += int(c.get("pending", 0))
                try:
                    await redis_client.xgroup_delconsumer(stream, group, c["name"])
                    zombie_count += 1
                except Exception:
                    pass
        if zombie_count:
            logging.warning(
                "Cleaned %d zombie consumers from %s/%s (orphaned pending=%d, NOT acked)",
                zombie_count, stream, group, orphaned_pending,
            )
            if orphaned_pending > 1000:
                logging.warning(
                    "Large orphaned pending (%d) in %s/%s. "
                    "Suggested: scripts/repair_realtime_redis_groups.sh --stream %s --group %s --reset-to-latest",
                    orphaned_pending, stream, group, stream, group,
                )
    except Exception:
        pass


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


async def _watch_parent(parent_pid: int, stop_event: asyncio.Event, interval: float = 5.0) -> None:
    """Phase 6A: parent 退出时通过 stop_event 触发正常清理，不再 os._exit 跳过 finally。"""
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

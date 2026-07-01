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

    # P0-B1: memory watchdog — RSS 超限优雅退出
    max_memory_mb = int(os.environ.get("RAW_NEWS_MAX_MEMORY_MB", "3072"))
    asyncio.create_task(_watch_memory(stop_event, max_memory_mb))

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
    # Phase 4F: Processor 直接从 news:raw 消费，不再经过废弃的 events:normal
    await _ensure_group_clean_start(redis_client, "stream:news:raw", args.processor_group)
    stream_config = SimpleNamespace(
        redis=SimpleNamespace(
            # realtime 生产跑使用稳定 group 名，避免每次重启产生 pm_e2e 僵尸组
            consumer_group=(
                "realtime_production"
                if (args.run_id and args.run_id.startswith("realtime_"))
                else f"pm_e2e:{args.run_id}"
            ),
            stream_max_length=int(os.getenv("REALTIME_NEWS_RAW_STREAM_MAXLEN", "50000")),
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
            "block_time": args.block_time,
            "storage_concurrency": args.storage_concurrency,
        },
    )
    processor = NewsStreamProcessor(
        event_bus=stream_bus,
        config={
            "database_gateway": gateway,
            "processor_group": args.processor_group,
            "processor_name": f"news_processor_realtime_{args.run_id}",
            "enable_ai_analysis": True,
            "enable_local_triage": True,
            "triage_mode": "hybrid",
            "triage_block_on_skip": True,
            "triage_pass_threshold": 0.10,
            "triage_skip_threshold": 0.0,
            "batch_processing": True,
            "batch_size": min(args.batch_size, 5),  # 上限 5，避免单批处理超时
            "structuring_total_timeout_s": 60,      # 从默认 90s 降到 60s
            "structuring_max_retries": 1,            # 从默认 2 降到 1
            # Phase 4F: 实时生产不设 run_id 过滤，所有消息均需处理
            "run_id_filter": None if (args.run_id and args.run_id.startswith("realtime_")) else args.run_id,
        },
    )

    await storage_handler.start_storage_service()
    await processor.start_business_processing()

    # P4: consumer watchdog — monitors idle time + pending/lag and auto-reclaims
    _our_names = {
        storage_handler.consumer_config.get("consumer_name", ""),
        processor.processor_config.get("processor_name", ""),
    }
    watchdog_task = asyncio.create_task(
        _consumer_watchdog(
            redis_client,
            stream_key=args.raw_stream,
            groups=[args.storage_group, args.processor_group],
            idle_warn_seconds=300,
            stop_event=stop_event,
            our_consumer_names=_our_names,
        ),
    )

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
        for task in [storage_handler.handler_task, processor.processor_task, watchdog_task]:
            if task:
                task.cancel()
        await asyncio.gather(
            *[task for task in [storage_handler.handler_task, processor.processor_task, watchdog_task] if task],
            return_exceptions=True,
        )

        # Phase 6A: self-cleanup — remove our consumers from groups on exit
        for _stream, _group, _cname in [
            ("stream:news:raw", args.storage_group,
             storage_handler.consumer_config.get("consumer_name", "")),
            ("stream:news:raw", args.processor_group,
             processor.processor_config.get("processor_name", "")),
        ]:
            if _cname:
                try:
                    await redis_client.xgroup_delconsumer(_stream, _group, _cname)
                    logging.info("Self-cleanup: removed consumer %s from %s/%s", _cname, _stream, _group)
                except Exception:
                    pass

        # Phase 6A: destroy pm_e2e:{run_id} consumer groups on auxiliary streams
        # These are created by UnifiedRedisStreamBus/RedisEventBus and never
        # cleaned up otherwise, leaving zombie groups on every E2E run.
        e2e_group_prefix = f"pm_e2e:{args.run_id}"
        for _stream in [
            "stream:theme_events",
            "stream:relation_events",
            "stream:cache_events",
            "stream:stats_events",
        ]:
            try:
                await redis_client.xgroup_destroy(_stream, e2e_group_prefix)
                logging.info(
                    "Self-cleanup: destroyed group %s on %s", e2e_group_prefix, _stream,
                )
            except Exception:
                pass

        await gateway.close()
        await redis_client.aclose()


async def _ensure_group_clean_start(redis_client, stream: str, group: str) -> None:
    """Phase 6A: 创建/复用 consumer group，live mode 从最新开始并清理僵尸。

    - 默认从 "0" 创建，避免跳过积压
    - 仅显式 REALTIME_STREAM_START_MODE=latest 时允许从 "$" 创建
    - latest 模式下 lag > 95% 才自动重置到 $
    - 僵尸清理：只 XGROUP DELCONSUMER，不 XACK pending（防止丢消息）
    """
    import os as _os
    start_mode = _os.environ.get("REALTIME_STREAM_START_MODE", "0").lower()
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
                    if stream_len > 0 and lag > stream_len * 0.95:
                        logging.warning(
                            "Group %s/%s lag=%d > 95%% of stream_len=%d, resetting to $",
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

    # Clean up zombie consumers (idle > 60s).
    # Pending messages are NOT reclaimed here (we don't know the new consumer name
    # yet). The P4 watchdog will XCLAIM orphaned pending to live consumers later.
    zombie_count = 0
    orphaned_pending = 0
    try:
        consumers = await redis_client.xinfo_consumers(stream, group)
        for c in consumers:
            idle_ms = int(c.get("idle", 0))
            if idle_ms > 60000:
                consumer_name = c["name"]
                pending_count = int(c.get("pending", 0))
                orphaned_pending += pending_count
                try:
                    await redis_client.xgroup_delconsumer(stream, group, consumer_name)
                    zombie_count += 1
                except Exception:
                    pass
        if zombie_count:
            logging.warning(
                "Cleaned %d zombie consumers from %s/%s (orphaned pending=%d — will be reclaimed by watchdog)",
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
    parser.add_argument("--batch-size", type=int, default=int(os.getenv("REALTIME_RAW_NEWS_BATCH_SIZE", "50")))
    parser.add_argument("--block-time", type=int, default=int(os.getenv("REALTIME_RAW_NEWS_BLOCK_MS", "2000")))
    parser.add_argument("--storage-concurrency", type=int, default=int(os.getenv("REALTIME_RAW_STORAGE_CONCURRENCY", "5")))
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


async def _watch_memory(stop_event: asyncio.Event, max_mb: int, interval: float = 30.0) -> None:
    """P0-B1: RSS 内存超限时优雅退出，让 supervisor 重启。

    优先使用 ps 命令获取 RSS（macOS/Linux 通用），
    失败则回退到 resource.getrusage。
    内存单位 MB，默认上限 3072MB（3GB）。
    """
    import resource as _resource
    import subprocess as _sp

    pid = os.getpid()
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
            return
        except asyncio.TimeoutError:
            pass

        rss_mb = 0
        # 方法 1: ps 命令（macOS/Linux 通用，最准确）
        try:
            result = _sp.run(
                ["ps", "-o", "rss=", "-p", str(pid)],
                capture_output=True, text=True, timeout=5,
            )
            if result.stdout.strip():
                rss_kb = int(result.stdout.strip())
                rss_mb = rss_kb // 1024
        except Exception:
            pass

        # 方法 2: resource.getrusage（macOS 上 maxrss 单位是字节）
        if rss_mb == 0:
            try:
                usage = _resource.getrusage(_resource.RUSAGE_SELF)
                rss_mb = usage.ru_maxrss // (1024 * 1024)
            except Exception:
                pass

        if rss_mb > max_mb:
            logging.error(
                "P0-B1: RSS %sMB exceeds limit %sMB, exiting for supervisor restart",
                rss_mb, max_mb,
            )
            sys.exit(137)  # 137 = 128 + 9 (SIGKILL-like，supervisor 可识别为 OOM)

        if rss_mb > max_mb * 0.8:
            logging.warning(
                "P0-B1: RSS %sMB approaching limit %sMB (%.0f%%)",
                rss_mb, max_mb, 100 * rss_mb / max_mb,
            )


async def _consumer_watchdog(
    redis_client,
    stream_key: str,
    groups: list,
    idle_warn_seconds: int = 300,
    stop_event: asyncio.Event | None = None,
    check_interval: float = 60.0,
    our_consumer_names: set | None = None,
) -> None:
    """P4+P5: consumer watchdog — diagnostics + graceful restart on stall.

    - idle > idle_warn_seconds + pending/lag > 0 → WARNING log
    - idle > idle_warn_seconds * 2 + pending > 0 → ERROR log (stuck on a message)
    - idle > idle_warn_seconds * 2 + pending == 0 + lag > 0 AND lag increasing →
      P5 stall: consumer loop is alive but falling behind.
      Requires 2 CONSECUTIVE detections (hysteresis).
    - Only monitors and restarts for OUR consumers (our_consumer_names).
      Zombies from previous runs are logged but ignored — killing our process
      won't fix another process's dead consumer.
    """
    _stall_count: dict[tuple[str, str], int] = {}  # (stream, group) → consecutive stalls
    _prev_lag: dict[tuple[str, str], int] = {}      # track lag trend

    while stop_event is None or not stop_event.is_set():
        try:
            await asyncio.wait_for(
                stop_event.wait() if stop_event else asyncio.sleep(0),
                timeout=check_interval,
            )
            return
        except asyncio.TimeoutError:
            pass

        for group in groups:
            try:
                consumers = await redis_client.xinfo_consumers(stream_key, group)
                group_info = await redis_client.xinfo_groups(stream_key)
                group_lag = 0
                for gi in group_info:
                    if gi.get("name") == group:
                        group_lag = int(gi.get("lag", 0))
                        break

                for c in consumers:
                    idle_s = int(c.get("idle", 0)) / 1000.0
                    pending = int(c.get("pending", 0))
                    cname = c.get("name", "?")
                    stall_key = (stream_key, group)

                    # Skip consumers that don't belong to THIS process
                    if our_consumer_names and cname not in our_consumer_names:
                        if idle_s > idle_warn_seconds * 4:
                            logging.warning(
                                "👻 P4: foreign zombie consumer %s in %s/%s idle=%.0fs — "
                                "will be cleaned by next _ensure_group_clean_start",
                                cname, stream_key, group, idle_s,
                            )
                        continue

                    if idle_s > idle_warn_seconds and (pending > 0 or group_lag > 0):
                        logging.warning(
                            "⚠️ P4 watchdog: consumer %s in %s/%s idle=%.0fs pending=%d lag=%d",
                            cname, stream_key, group, idle_s, pending, group_lag,
                        )

                    # P5: pending==0 && lag>0 && idle > 2*warn => consumer loop
                    # may not be polling. But a single new message during low-volume
                    # periods (after-hours) can create lag>0 that triggers a false
                    # positive. Only count as stall if lag is INCREASING between checks.
                    prev_lag = _prev_lag.get(stall_key, 0)
                    lag_increasing = group_lag > prev_lag
                    _prev_lag[stall_key] = group_lag

                    if (
                        idle_s > idle_warn_seconds * 2
                        and pending == 0
                        and group_lag > 0
                        and lag_increasing
                        and stop_event is not None
                    ):
                        _stall_count[stall_key] = _stall_count.get(stall_key, 0) + 1
                        if _stall_count[stall_key] >= 2:
                            logging.error(
                                "🔄 P5 watchdog: consumer %s in %s/%s STALLED ×%d idle=%.0fs pending=%d lag=%d↑ — "
                                "triggering graceful shutdown for supervisor restart",
                                cname, stream_key, group, _stall_count[stall_key],
                                idle_s, pending, group_lag,
                            )
                            stop_event.set()
                            return
                        else:
                            logging.warning(
                                "⏳ P5 hysteresis: consumer %s in %s/%s stall #%d/2 idle=%.0fs lag=%d↑ prev=%d — "
                                "waiting for next check before restart",
                                cname, stream_key, group, _stall_count[stall_key],
                                idle_s, group_lag, prev_lag,
                            )
                    else:
                        # Reset stall count when conditions clear
                        _stall_count.pop(stall_key, None)
                        if idle_s <= idle_warn_seconds:
                            _prev_lag.pop(stall_key, None)  # reset trend baseline on recovery

                    if idle_s > idle_warn_seconds * 2 and (pending > 0 or group_lag > 0):
                        logging.error(
                            "🚨 P4 watchdog: consumer %s in %s/%s SEVERELY STALE idle=%.0fs pending=%d lag=%d — "
                            "DB operation may be stuck (pending>0) — cannot auto-restart",
                            cname, stream_key, group, idle_s, pending, group_lag,
                        )

            except Exception as exc:
                logging.debug("P4 watchdog check skipped for %s/%s: %s", stream_key, group, exc)


if __name__ == "__main__":
    main()

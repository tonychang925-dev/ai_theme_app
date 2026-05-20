from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from stock_processing_service.application.services.akshare_realtime_news_collector import (
    AkShareRealtimeNewsCollector,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run AkShare realtime news collector into Redis raw-news stream.")
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/0")
    parser.add_argument("--stream", default="stream:news:raw")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--poll-interval-seconds", type=int, default=60)
    parser.add_argument("--lookback-minutes", type=int, default=180)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--status-path", default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--parent-pid", type=int, default=None)
    # P1-A: prefilter
    parser.add_argument("--prefilter-enabled", type=lambda x: x.lower() in ("1","true","yes","on"), default=True)
    parser.add_argument("--prefilter-mode", default="rule", choices=["rule","prompt","embedding","off"])
    parser.add_argument("--prefilter-model-path", default="")
    parser.add_argument("--prefilter-fail-open", type=lambda x: x.lower() in ("1","true","yes","on"), default=True)
    parser.add_argument("--prefilter-skip-log", default=None)
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    collector = AkShareRealtimeNewsCollector(
        redis_url=args.redis_url,
        stream=args.stream,
        run_id=args.run_id,
        poll_interval_seconds=args.poll_interval_seconds,
        lookback_minutes=args.lookback_minutes,
        batch_size=args.batch_size,
        status_path=args.status_path,
        prefilter_enabled=args.prefilter_enabled,
        prefilter_mode=args.prefilter_mode,
        prefilter_model_path=args.prefilter_model_path,
        prefilter_fail_open=args.prefilter_fail_open,
        prefilter_skip_log_path=args.prefilter_skip_log,
    )
    if args.parent_pid:
        asyncio.create_task(_watch_parent(args.parent_pid))

    if args.once:
        result = await collector.collect_once()
        print(result)
        return

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    task = asyncio.create_task(collector.run_forever())
    await stop_event.wait()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)


async def _watch_parent(parent_pid: int, interval: float = 5.0) -> None:
    """P1-C1: 父进程不存在时主动退出。"""
    import os as _os
    while True:
        await asyncio.sleep(interval)
        try:
            _os.kill(parent_pid, 0)
        except (ProcessLookupError, PermissionError):
            logging.warning("parent pid %d died, exiting", parent_pid)
            _os._exit(0)


if __name__ == "__main__":
    asyncio.run(async_main())

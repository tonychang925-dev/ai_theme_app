"""RealTimeNewsCollector standalone launcher — collector only, no downstream handlers.

Phase 4F (2026-05-24):
  只启动 RealTimeNewsCollector 写入 stream:news:raw。
  不启动 news_storage_handler / news_stream_processor / theme_processor / decision_executor。
  由 RealtimeStackManager 作为子进程启动，也可独立运行。

用法:
  python -m database_service.streams.run_realtime_news_collector \
    --redis-url redis://localhost:6379/0 \
    --run-id realtime_20260524_xxx \
    --status-path /tmp/collector.status.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

logger = logging.getLogger("db_collector")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="RealTimeNewsCollector standalone")
    p.add_argument("--redis-url", default=os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
    p.add_argument("--db-name", default=os.environ.get("PG_DATABASE", "stock_data_test"))
    p.add_argument("--run-id", required=True)
    p.add_argument("--status-path", default=None)
    p.add_argument("--parent-pid", type=int, default=None)
    p.add_argument("--collection-interval", type=int, default=300)
    p.add_argument("--allow-production", action="store_true")
    return p


class CollectorStatus:
    def __init__(self, status_path: Path | None = None) -> None:
        self._path = status_path
        self.stats: dict[str, Any] = {
            "active_collector": "RealTimeNewsCollector",
            "collector_version": "phase4e",
            "running": False,
            "started_at": None,
            "last_collect_at": None,
            "collections": 0,
            "news_collected_total": 0,
            "news_published_total": 0,
            "news_prefilter_skipped": 0,
            "news_dedup_skipped": 0,
            "semantic_dedup_batch_count": 0,
            "semantic_dedup_recent_count": 0,
            "qwen_dedup_ready": False,
            "qwen_dedup_call_count": 0,
            "qwen_dedup_budget_exhausted": 0,
            "hard_protect_count": 0,
            "last_error": None,
        }

    def merge_collection_stats(self, result: dict[str, Any]) -> None:
        self.stats["last_collect_at"] = datetime.now(timezone.utc).isoformat()
        self.stats["collections"] += 1
        self.stats["news_collected_total"] += result.get("news_collected", 0)
        self.stats["news_published_total"] += result.get("news_published", 0)
        self.stats["news_prefilter_skipped"] += result.get("news_prefilter_skipped", 0)
        self.stats["news_dedup_skipped"] += result.get("news_dedup_skipped", 0)
        self.stats["semantic_dedup_batch_count"] += result.get("semantic_dedup_batch_count", 0)
        self.stats["semantic_dedup_recent_count"] += result.get("semantic_dedup_recent_count", 0)
        self.stats["qwen_dedup_ready"] = result.get("qwen_dedup_ready", self.stats["qwen_dedup_ready"])
        self.stats["qwen_dedup_call_count"] += result.get("qwen_dedup_call_count", 0)
        self.stats["qwen_dedup_budget_exhausted"] += result.get("qwen_dedup_budget_exhausted", 0)
        self.stats["hard_protect_count"] += result.get("hard_protect_count", 0)
        if result.get("error"):
            self.stats["last_error"] = str(result["error"])[:200]

    def write(self) -> None:
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self.stats, ensure_ascii=False, indent=2))
        except Exception:
            pass


async def _watch_parent(parent_pid: int, interval: float = 5.0) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            os.kill(parent_pid, 0)
        except (ProcessLookupError, PermissionError):
            logger.warning("parent pid %d died, exiting collector", parent_pid)
            os._exit(0)


async def async_main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )

    status_path = Path(args.status_path) if args.status_path else None
    status = CollectorStatus(status_path)
    status.stats["running"] = True
    status.stats["started_at"] = datetime.now(timezone.utc).isoformat()
    status.write()

    logger.info(
        "RealTimeNewsCollector starting: run_id=%s redis=%s db=%s interval=%ss",
        args.run_id, args.redis_url, args.db_name, args.collection_interval,
    )

    if args.parent_pid:
        asyncio.create_task(_watch_parent(args.parent_pid))

    # Import and build collector
    from database_service.streams.services.real_time_news_collector import RealTimeNewsCollector

    collector = RealTimeNewsCollector(
        stream_manager=None,  # collector will use its own redis connection
        config={
            "collection_interval": args.collection_interval,
            "default_mode": "auto",
            "enable_collector_prefilter": True,
            "collector_drop_on_skip": True,
            "enable_semantic_dedup": bool(
                os.environ.get("ENABLE_SEMANTIC_DEDUP", "true").lower() != "false"
            ),
            "semantic_dedup_mode": os.environ.get("SEMANTIC_DEDUP_MODE", "rule_prompt"),
            "semantic_dedup_model_path": os.environ.get(
                "SEMANTIC_DEDUP_MODEL_PATH",
                str(ROOT / "model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf"),
            ),
            "semantic_dedup_recent_max_size": 500,
            "semantic_dedup_recent_max_age_hours": 6,
            "semantic_dedup_audit_dir": "tmp/product_runtime_phase4e_semantic_dedupe",
            "qwen_dedup_warmup": True,
            "qwen_max_per_round": 20,
            "qwen_max_candidates_per_news": 5,
            "qwen_max_recent_comparisons": 50,
        },
    )

    # Override stream_manager with a Redis connection based collector
    import redis.asyncio as aioredis

    class SimpleStreamPublisher:
        def __init__(self, redis_url: str):
            self._url = redis_url
            self._redis: aioredis.Redis | None = None

        async def _get(self) -> aioredis.Redis:
            if self._redis is None:
                self._redis = aioredis.from_url(self._url, decode_responses=True)
            return self._redis

        async def publish(self, stream: str, data: dict) -> str | None:
            r = await self._get()
            mid = await r.xadd(stream, data, maxlen=10000)
            return mid if isinstance(mid, str) else mid.decode() if mid else None

        async def close(self) -> None:
            if self._redis:
                await self._redis.aclose()
                self._redis = None

    publisher = SimpleStreamPublisher(args.redis_url)
    collector.stream_manager = publisher

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass

    # start collection loop
    await collector.start_collection_loop()

    # periodic status write
    async def status_writer():
        while not stop_event.is_set():
            await asyncio.sleep(30)
            try:
                cs = await collector.get_collection_stats()
                status.stats.update({
                    "news_collected_total": cs.get("news_collected_total", status.stats["news_collected_total"]),
                    "news_published_total": cs.get("news_published_total", status.stats["news_published_total"]),
                    "news_prefilter_skipped": cs.get("news_prefilter_skipped", status.stats["news_prefilter_skipped"]),
                    "news_dedup_skipped": cs.get("news_dedup_skipped", status.stats["news_dedup_skipped"]),
                    "semantic_dedup_batch_count": cs.get("semantic_dedup_batch_count", 0),
                    "semantic_dedup_recent_count": cs.get("semantic_dedup_recent_count", 0),
                    "qwen_dedup_ready": cs.get("qwen_dedup_ready", False),
                    "qwen_dedup_call_count": cs.get("qwen_dedup_call_count", 0),
                    "qwen_dedup_budget_exhausted": cs.get("qwen_dedup_budget_exhausted", 0),
                    "hard_protect_count": cs.get("hard_protect_count", 0),
                })
                status.write()
            except Exception:
                pass

    status_task = asyncio.create_task(status_writer())

    await stop_event.wait()
    await collector.stop_collection_loop()
    status_task.cancel()
    try:
        await status_task
    except asyncio.CancelledError:
        pass

    await publisher.close()
    status.stats["running"] = False
    status.write()
    logger.info("RealTimeNewsCollector stopped")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()

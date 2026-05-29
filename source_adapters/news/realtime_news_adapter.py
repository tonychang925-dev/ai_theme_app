"""P3-1: RealtimeNewsAdapter — 新闻采集源适配器 facade。

包装现有 RealTimeNewsCollector，不改采集逻辑。
在 publish 层注入 envelope，输出到 stream:intel.raw.news（alias → stream:news:raw）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from source_adapters.base import SourceAdapter
from core.contracts.envelope import ensure_envelope
from core.contracts.streams import resolve

logger = logging.getLogger(__name__)


class RealtimeNewsAdapter(SourceAdapter):
    """新闻采集源适配器 — facade 包装 RealTimeNewsCollector。

    不重写任何采集/去重/预筛选逻辑，仅：
    1. 注入 envelope 包装层
    2. 输出到新 stream 名（stream:intel.raw.news）
    """

    name = "RealtimeNewsAdapter"
    source_type = "news"

    def __init__(
        self,
        stream_manager=None,
        crawler_service_client=None,
        news_producer=None,
        config: Optional[Dict] = None,
        redis_url: Optional[str] = None,
    ):
        self._config = config or {}
        self._redis_url = redis_url
        self._target_stream = "stream:intel.raw.news"  # 新命名，alias → stream:news:raw
        self._stream_manager = stream_manager
        self._crawler_client = crawler_service_client
        self._news_producer = news_producer

        self._collector = None
        self._started = False

    # ---- 生命周期 ----

    async def start(self) -> None:
        """启动采集循环（委托给 RealTimeNewsCollector）。"""
        if self._started:
            return

        from database_service.streams.services.real_time_news_collector import (
            RealTimeNewsCollector,
        )

        sm = self._stream_manager
        # 如果没有传入 stream_manager，用 redis_url 构造 SimpleStreamPublisher
        if sm is None and self._redis_url:
            import redis.asyncio as aioredis

            class _SimpleStreamPublisher:
                def __init__(self, redis_url: str):
                    self._url = redis_url
                    self._redis: Optional[aioredis.Redis] = None

                async def _get(self) -> aioredis.Redis:
                    if self._redis is None:
                        self._redis = aioredis.from_url(self._url, decode_responses=True)
                    return self._redis

                async def publish(self, stream: str, data: dict) -> Optional[str]:
                    r = await self._get()
                    mid = await r.xadd(stream, data, maxlen=10000)
                    return mid if isinstance(mid, str) else mid.decode() if mid else None

                async def close(self) -> None:
                    if self._redis:
                        await self._redis.aclose()
                        self._redis = None

            sm = _SimpleStreamPublisher(self._redis_url)

        # 注入 envelope 包装层
        wrapped_sm = _EnvelopeStreamManager(sm, self._target_stream, self._adapter_meta())

        self._collector = RealTimeNewsCollector(
            stream_manager=wrapped_sm,
            crawler_service_client=self._crawler_client,
            news_producer=self._news_producer,
            config=self._config,
        )
        await self._collector.start_collection_loop()
        self._started = True
        logger.info("RealtimeNewsAdapter started, target=%s resolved=%s",
                     self._target_stream, resolve(self._target_stream))

    async def stop(self) -> None:
        """停止采集循环。"""
        if self._collector and self._started:
            await self._collector.stop_collection_loop()
            self._started = False
            logger.info("RealtimeNewsAdapter stopped")

    async def health(self) -> dict:
        """返回适配器健康状态。"""
        base = await super().health()
        if self._collector:
            try:
                stats = await self._collector.get_collection_stats()
                base.update({
                    "status": "running" if self._started else "stopped",
                    "is_running": stats.get("is_running", False),
                    "total_collections": stats.get("total_collections", 0),
                    "news_published": stats.get("news_published", 0),
                    "last_collection_time": stats.get("last_collection_time"),
                    "collector_version": stats.get("collector_version", ""),
                    "target_stream": self._target_stream,
                    "resolved_stream": resolve(self._target_stream),
                })
            except Exception:
                base["status"] = "error"
        else:
            base["status"] = "not_initialized"
        return base

    # ---- 三步接口（供新调用方使用，不经过 prefilter/dedup 完整管线） ----

    async def fetch(self) -> List[Dict]:
        """采集原始新闻（仅爬取，不做过滤/去重）。"""
        if self._collector:
            return await self._collector._collect_news(self._collector.default_mode)
        return []

    def normalize_minimal(self, raw_items: List[Dict]) -> List[Dict]:
        """最小标准化：补齐 source_type / collector_name 等元数据。"""
        if self._collector:
            return self._collector._normalize_news_batch(raw_items)
        # 退路：如果 collector 未初始化，手动补齐最小字段
        for item in raw_items:
            item.setdefault("source_type", "news")
            item.setdefault("collector_name", self.name)
            item.setdefault("collector_version", "p3-1")
        return raw_items

    async def publish(self, items: List[Dict]) -> int:
        """逐条包装 envelope 后写入 stream:intel.raw.news。"""
        if not items:
            return 0

        resolved_stream = resolve(self._target_stream)
        sm = self._collector.stream_manager if self._collector else self._stream_manager
        if sm is None:
            logger.warning("RealtimeNewsAdapter.publish: no stream_manager available")
            return 0

        # 解开 envelope wrapper，直接发到底层 stream
        inner_sm = sm._inner if isinstance(sm, _EnvelopeStreamManager) else sm

        published = 0
        for item in items:
            try:
                env = ensure_envelope(dict(item), default_schema_type="NewsRawEvent")
                env.setdefault("source_type", "news")
                mid = await inner_sm.publish(resolved_stream, env)
                if mid:
                    published += 1
            except Exception:
                logger.exception("RealtimeNewsAdapter.publish: failed for %s",
                                 item.get("news_id", item.get("title", "?")[:60]))
        return published

    # ---- 辅助 ----

    @property
    def target_stream(self) -> str:
        return self._target_stream

    @property
    def resolved_stream(self) -> str:
        return resolve(self._target_stream)


class _EnvelopeStreamManager:
    """stream_manager 包装器：在 publish 时自动添加 envelope。

    对 collector 透明 — collector 调用 self.stream_manager.publish(stream, data)
    时，自动被包装成 envelope 消息，输出到目标 stream。
    """

    def __init__(self, inner, target_stream: str, adapter_meta: dict):
        self._inner = inner
        self._target = target_stream
        self._meta = adapter_meta

    async def publish(self, stream: str, data: dict) -> Optional[str]:
        """拦截 publish：用 envelope 包装后写入 resolved stream。"""
        env = ensure_envelope(dict(data), default_schema_type="NewsRawEvent")
        resolved = resolve(self._target)
        return await self._inner.publish(resolved, env)

    def __getattr__(self, name: str):
        """代理其他属性访问到内部 stream_manager。"""
        return getattr(self._inner, name)

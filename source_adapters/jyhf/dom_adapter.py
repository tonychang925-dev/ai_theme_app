"""P3-2: JyhfDomAdapter — JYHF CDP DOM 采集源适配器 facade。

包装现有 JyhfCdpCollectorService，不改 CDP 采集逻辑。
在 publish 层注入 envelope，输出到 stream:intel.raw.dom（alias → stream:event:feed）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from source_adapters.base import SourceAdapter
from core.contracts.envelope import ensure_envelope
from core.contracts.streams import resolve

logger = logging.getLogger(__name__)


class JyhfDomAdapter(SourceAdapter):
    """JYHF CDP DOM 采集源适配器 — facade 包装 JyhfCdpCollectorService。

    不重写任何 CDP 采集/提取/标准化逻辑，仅：
    1. 注入 envelope 包装层
    2. 输出到新 stream 名（stream:intel.raw.dom）
    """

    name = "JyhfDomAdapter"
    source_type = "dom"

    def __init__(
        self,
        stream_manager=None,
        config: Optional[Dict] = None,
        redis_url: Optional[str] = None,
        collector_service=None,
    ):
        self._config = config or {}
        self._redis_url = redis_url
        self._target_stream = "stream:intel.raw.dom"  # 新命名，alias → stream:event:feed
        self._stream_manager = stream_manager
        self._collector_service = collector_service

        self._started = False

    # ---- 生命周期 ----

    async def start(self) -> None:
        """启动 JYHF DOM 采集循环（委托给 JyhfCdpCollectorService）。"""
        if self._started:
            return

        if self._collector_service is not None:
            await self._collector_service.start()
            self._started = True
            logger.info("JyhfDomAdapter started via collector_service, target=%s resolved=%s",
                         self._target_stream, resolve(self._target_stream))
        else:
            logger.warning("JyhfDomAdapter.start: no collector_service provided, "
                           "start is a no-op. Provide a JyhfCdpCollectorService instance "
                           "or use the existing CDP service on port 8095.")

    async def stop(self) -> None:
        """停止 JYHF DOM 采集循环。"""
        if self._collector_service and self._started:
            await self._collector_service.stop()
            self._started = False
            logger.info("JyhfDomAdapter stopped")

    async def health(self) -> dict:
        """返回适配器健康状态。"""
        base = await super().health()
        if self._collector_service:
            try:
                info = await self._collector_service.get_info()
                base.update({
                    "status": "running" if self._started else "stopped",
                    "collector_running": info.get("collector_running", False),
                    "last_capture_at": info.get("last_capture_at"),
                    "last_event_at": info.get("last_event_at"),
                    "new_event_count": info.get("new_event_count_total", 0),
                    "pushed_to_stream_count": info.get("pushed_to_stream_count_total", 0),
                    "target_stream": self._target_stream,
                    "resolved_stream": resolve(self._target_stream),
                })
            except Exception:
                base["status"] = "error"
        else:
            base["status"] = "not_initialized"
        return base

    # ---- 三步接口 ----

    async def fetch(self) -> List[Dict]:
        """采集 JYHF DOM 原始事件（委托给 collector service 的单次采集）。"""
        if self._collector_service:
            try:
                result = await self._collector_service._capture_once_locked()
                events = result.get("new_events", []) if isinstance(result, dict) else []
                return [e.dict() if hasattr(e, "dict") else dict(e) for e in events]
            except Exception:
                logger.exception("JyhfDomAdapter.fetch: capture failed")
                return []
        return []

    def normalize_minimal(self, raw_items: List[Dict]) -> List[Dict]:
        """最小标准化：补齐 source_type=dom / source_name=jyhf 等元数据。"""
        for item in raw_items:
            item.setdefault("source_type", "dom")
            item.setdefault("source_name", "jyhf")
            item.setdefault("source_channel", item.get("source_channel", "jyhf_cdp"))
            item.setdefault("collector_name", self.name)
            item.setdefault("collector_version", "p3-2")
        return raw_items

    async def publish(self, items: List[Dict]) -> int:
        """逐条包装 envelope 后写入 stream:intel.raw.dom。"""
        if not items:
            return 0

        resolved_stream = resolve(self._target_stream)
        sm = self._stream_manager
        if sm is None and self._redis_url:
            import redis.asyncio as aioredis

            class _SimpleRedisPublisher:
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

            sm = _SimpleRedisPublisher(self._redis_url)

        if sm is None:
            logger.warning("JyhfDomAdapter.publish: no stream_manager or redis_url available")
            return 0

        # 解开 envelope wrapper（如果已包装）
        inner_sm = sm._inner if hasattr(sm, "_inner") and not isinstance(sm, _SimpleRedisPublisher) else sm

        published = 0
        for item in items:
            try:
                env = ensure_envelope(dict(item), default_schema_type="DomRawEvent")
                env.setdefault("source_type", "dom")
                mid = await inner_sm.publish(resolved_stream, env)
                if mid:
                    published += 1
            except Exception:
                logger.exception("JyhfDomAdapter.publish: failed for event %s",
                                 item.get("event_id", item.get("dedup_key", "?")[:60]))
        return published

    # ---- 辅助 ----

    @property
    def target_stream(self) -> str:
        return self._target_stream

    @property
    def resolved_stream(self) -> str:
        return resolve(self._target_stream)

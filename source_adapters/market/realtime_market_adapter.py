"""P3-3: RealtimeMarketAdapter — 行情数据源适配器 facade。

包装现有 JyhfMarketCollector / TdxMarketCollector，不改行情采集逻辑。
在 publish 层注入 envelope，输出到 stream:intel.raw.market（无 alias，独立 raw stream）。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from source_adapters.base import SourceAdapter
from core.contracts.envelope import ensure_envelope
from core.contracts.streams import resolve

logger = logging.getLogger(__name__)


class RealtimeMarketAdapter(SourceAdapter):
    """行情数据源适配器 — facade 包装 JyhfMarketCollector / TdxMarketCollector。

    不重写任何行情采集/计算逻辑，仅：
    1. 注入 envelope 包装层
    2. 输出到新 stream 名（stream:intel.raw.market，独立 raw stream，不 alias 到 feed）

    source_name 由调用方指定 (jyhf / tdx)，决定数据源身份。
    """

    name = "RealtimeMarketAdapter"
    source_type = "market"

    def __init__(
        self,
        stream_manager=None,
        config: Optional[Dict] = None,
        redis_url: Optional[str] = None,
        collector_service=None,
        source_name: str = "market",
    ):
        self._config = config or {}
        self._redis_url = redis_url
        # stream:intel.raw.market intentionally has no alias;
        # consumers must opt in explicitly to avoid mixing raw market data into UI feed.
        self._target_stream = "stream:intel.raw.market"
        self._source_name = source_name
        self._stream_manager = stream_manager
        self._collector_service = collector_service

        self._started = False

    # ---- 生命周期 ----

    async def start(self) -> None:
        """启动行情采集循环（委托给 collector service）。"""
        if self._started:
            return

        if self._collector_service is not None:
            await self._collector_service.start()
            self._started = True
            logger.info("RealtimeMarketAdapter started via collector_service, "
                         "source=%s target=%s",
                         self._source_name, self._target_stream)
        else:
            logger.warning("RealtimeMarketAdapter.start: no collector_service provided, "
                           "start is a no-op. Provide a JyhfMarketCollector / TdxMarketCollector "
                           "instance to enable real-time market collection.")

    async def stop(self) -> None:
        """停止行情采集循环。"""
        if self._collector_service and self._started:
            await self._collector_service.stop()
            self._started = False
            logger.info("RealtimeMarketAdapter stopped (source=%s)", self._source_name)

    async def health(self) -> dict:
        """返回适配器健康状态。"""
        base = await super().health()
        base["source_name"] = self._source_name
        if self._collector_service:
            try:
                info = await self._collector_service.get_info()
                base.update({
                    "status": "running" if self._started else "stopped",
                    "collector_running": info.get("collector_running", False),
                    "last_collect_at": info.get("last_collect_at"),
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
        """行情单次 fetch 暂不直接调用 collector 私有采集方法。

        行情采集由现有 JyhfMarketCollector / TdxMarketCollector 生命周期负责。
        新调用方如需发布，可通过 normalize_minimal() + publish() 处理外部传入的行情 items。
        """
        logger.warning(
            "RealtimeMarketAdapter.fetch: no-op in facade mode; "
            "use existing collector service or pass items to publish()"
        )
        return []

    def normalize_minimal(self, raw_items: List[Dict]) -> List[Dict]:
        """最小标准化：补齐 source_type=market / source_name 等元数据。"""
        for item in raw_items:
            item.setdefault("source_type", "market")
            item.setdefault("source_name", self._source_name)
            item.setdefault("source_channel", item.get("source_channel", self._source_name))
            item.setdefault("collector_name", self.name)
            item.setdefault("collector_version", "p3-3")
        return raw_items

    async def publish(self, items: List[Dict]) -> int:
        """逐条包装 envelope 后写入 stream:intel.raw.market。"""
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
            logger.warning(
                "RealtimeMarketAdapter.publish: no stream_manager or redis_url available"
            )
            return 0

        # 解开可能存在的 envelope wrapper，拿到底层 publisher
        inner_sm = getattr(sm, "_inner", sm)

        published = 0
        for item in items:
            try:
                env = ensure_envelope(dict(item), default_schema_type="MarketTickEvent")
                env["source_type"] = "market"
                env["source_name"] = self._source_name
                mid = await inner_sm.publish(resolved_stream, env)
                if mid:
                    published += 1
            except Exception:
                logger.exception("RealtimeMarketAdapter.publish: failed for item %s",
                                 item.get("stock_code", item.get("symbol", "?")[:20]))
        return published

    # ---- 辅助 ----

    @property
    def target_stream(self) -> str:
        return self._target_stream

    @property
    def resolved_stream(self) -> str:
        return resolve(self._target_stream)

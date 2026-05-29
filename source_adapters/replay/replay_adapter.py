"""P3-4: ReplaySourceAdapter — 回放数据源适配器。

从 JSONL / list[dict] / Redis Stream 历史读取已采集的事件，
以统一 envelope 格式回放到指定目标 stream，用于测试、复盘、回放和策略验证。

不接管真实采集器，不改 Runtime，不改业务 scorer。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from source_adapters.base import SourceAdapter
from core.contracts.envelope import ensure_envelope
from core.contracts.streams import resolve

logger = logging.getLogger(__name__)

# 支持的 schema_type 集合
VALID_SCHEMA_TYPES = frozenset({
    "NewsRawEvent",
    "DomRawEvent",
    "MarketTickEvent",
    "SignalDecision",
})


class ReplaySourceAdapter(SourceAdapter):
    """回放数据源适配器。

    从静态数据源读取历史事件，以 envelope 格式回放到目标 stream。
    schema_type 和 target_stream 均可配置，适配不同回放场景。

    用法:
        # 从内存列表回放
        adapter = ReplaySourceAdapter(
            items=[...],
            schema_type="NewsRawEvent",
            target_stream="stream:intel.raw.news",
        )

        # 从 JSONL 文件回放
        adapter = ReplaySourceAdapter(
            source_path="path/to/events.jsonl",
            schema_type="MarketTickEvent",
            target_stream="stream:intel.raw.market",
        )
    """

    name = "ReplaySourceAdapter"
    source_type = "replay"

    def __init__(
        self,
        items: Optional[List[Dict]] = None,
        source_path: Optional[str] = None,
        schema_type: str = "NewsRawEvent",
        target_stream: str = "stream:intel.raw.news",
        stream_manager=None,
        redis_url: Optional[str] = None,
        source_name: str = "replay",
    ):
        self._items = items
        self._source_path = Path(source_path) if source_path else None
        self._schema_type = schema_type
        self._target_stream = target_stream
        self._source_name = source_name
        self._stream_manager = stream_manager
        self._redis_url = redis_url

    # ---- 生命周期 ----

    async def start(self) -> None:
        """回放适配器无需后台循环。"""
        logger.info("ReplaySourceAdapter ready: schema_type=%s target=%s source_path=%s",
                     self._schema_type, self._target_stream, self._source_path)

    async def stop(self) -> None:
        """回放适配器无需清理。"""
        pass

    async def health(self) -> dict:
        """返回适配器状态。"""
        base = await super().health()
        base.update({
            "status": "ready",
            "schema_type": self._schema_type,
            "target_stream": self._target_stream,
            "resolved_stream": resolve(self._target_stream),
            "source_path": str(self._source_path) if self._source_path else None,
            "items_count": len(self._items) if self._items else 0,
        })
        return base

    # ---- 三步接口 ----

    async def fetch(self) -> List[Dict]:
        """从配置的数据源读取历史事件。

        优先级：items > source_path (JSONL)
        """
        if self._items:
            return list(self._items)

        if self._source_path:
            return self._read_jsonl(self._source_path)

        logger.warning("ReplaySourceAdapter.fetch: no items or source_path configured")
        return []

    def normalize_minimal(self, raw_items: List[Dict]) -> List[Dict]:
        """最小标准化：补齐 source_type=replay 及回放元数据。

        保留原始 source_type / source_name 在 original_source_type / original_source_name 字段中，
        以便下游追溯事件原始来源。
        """
        for item in raw_items:
            # 保存原始来源信息
            if "source_type" in item and item.get("source_type") != "replay":
                item.setdefault("original_source_type", item["source_type"])
            if "source_name" in item and item.get("source_name") != "replay":
                item.setdefault("original_source_name", item["source_name"])

            item["source_type"] = "replay"
            item["source_name"] = self._source_name
            item.setdefault("source_channel", "replay")
            item.setdefault("collector_name", self.name)
            item.setdefault("collector_version", "p3-4")
        return raw_items

    async def publish(self, items: List[Dict]) -> int:
        """逐条包装 envelope 后写入目标 stream。"""
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
                "ReplaySourceAdapter.publish: no stream_manager or redis_url available"
            )
            return 0

        inner_sm = getattr(sm, "_inner", sm)

        published = 0
        for item in items:
            try:
                env = ensure_envelope(dict(item), default_schema_type=self._schema_type)
                env["source_type"] = "replay"
                mid = await inner_sm.publish(resolved_stream, env)
                if mid:
                    published += 1
            except Exception:
                logger.exception("ReplaySourceAdapter.publish: failed for item %s",
                                 item.get("event_id", item.get("news_id", "?")[:60]))
        logger.info("ReplaySourceAdapter published %d/%d items to %s (schema_type=%s)",
                     published, len(items), resolved_stream, self._schema_type)
        return published

    # ---- 内部 ----

    def _read_jsonl(self, path: Path) -> List[Dict]:
        """从 JSONL 文件读取事件列表。"""
        if not path.exists():
            logger.warning("ReplaySourceAdapter: source_path not found: %s", path)
            return []

        items = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        items.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("ReplaySourceAdapter: skip malformed JSONL line in %s", path)
            logger.info("ReplaySourceAdapter: read %d items from %s", len(items), path)
        except Exception:
            logger.exception("ReplaySourceAdapter: failed to read %s", path)
        return items

    # ---- 辅助 ----

    @property
    def target_stream(self) -> str:
        return self._target_stream

    @property
    def resolved_stream(self) -> str:
        return resolve(self._target_stream)

    @property
    def schema_type(self) -> str:
        return self._schema_type

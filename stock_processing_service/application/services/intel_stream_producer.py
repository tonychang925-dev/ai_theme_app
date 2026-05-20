# ai_theme_app/stock_processing_service/application/services/intel_stream_producer.py
"""
Phase 6A: 一手信息事件投递器

将 structured_intel_event 转换为 news_event 行 + stream:events:structured envelope，
复用现有 ThemeProcessor / DecisionExecutor / PreMarketBriefBuilder 后半段链路。

MVP 策略:
  structured_intel_event
  → news_event (source_category='intel', source_trace_id 贯穿)
  → xadd stream:events:structured (envelope 与 ThemeProcessor 兼容)
  → UPDATE stream_status = 'produced'

不改 ThemeProcessor。
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# UTC+8
TZ_CN = timezone(timedelta(hours=8))


class IntelStreamProducer:
    """一手信息事件投递器。

    用法:
        producer = IntelStreamProducer(gateway)
        events_produced = await producer.produce_batch(limit=50)
    """

    def __init__(
        self,
        gateway: Any,
        *,
        redis_client: Any = None,
        stream_name: str = "stream:events:structured",
        maxlen: int = 10000,
        run_id: Optional[str] = None,
    ) -> None:
        self._gateway = gateway
        self._redis = redis_client
        self._stream_name = stream_name
        self._maxlen = maxlen
        self._run_id = run_id or os.getenv("RUN_ID", "")

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def produce(self, intel_event_id: int) -> str:
        """投递单条 structured_intel_event。

        Returns:
            Redis stream message_id。
        """
        getter = getattr(self._gateway, "get_intel_event_for_stream", None)
        if not callable(getter):
            raise RuntimeError("gateway 不支持 get_intel_event_for_stream")
        target = await getter(intel_event_id)
        if not target:
            raise ValueError(
                f"structured_intel_event id={intel_event_id} 不存在"
            )
        stream_status = str(target.get("stream_status") or "").lower()
        if stream_status == "produced":
            return str(target.get("stream_message_id") or "")
        if stream_status != "pending":
            raise ValueError(
                f"structured_intel_event id={intel_event_id} stream_status={stream_status} 不可投递"
            )

        return await self._produce_one(target)

    async def produce_batch(self, limit: int = 50) -> int:
        """批量投递 stream_status='pending' 的事件。

        Returns:
            成功投递数量。
        """
        events = await self._gateway.get_pending_intel_events_for_stream(limit=limit)
        if not events:
            logger.info("IntelStreamProducer: 无待投递事件")
            return 0

        count = 0
        for ev in events:
            try:
                await self._produce_one(ev)
                count += 1
            except Exception:
                logger.exception(
                    "IntelStreamProducer: 投递失败 sie_id=%s stock=%s",
                    ev["id"],
                    ev.get("stock_code"),
                )
                raise  # 不允许静默跳过

        logger.info("IntelStreamProducer: 批量投递完成 %s/%s", count, len(events))
        return count

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _produce_one(self, intel_event: Dict[str, Any]) -> str:
        """投递单条事件的完整流程。"""
        sie_id = int(intel_event["id"])
        raw_doc_id = int(intel_event.get("raw_doc_id", 0))

        # 构建全链路 source_trace_id
        source_trace_id = self._build_source_trace_id(
            raw_doc_id=raw_doc_id,
            sie_id=sie_id,
        )

        # 1. 写入 news_event（source_category='intel'）
        ne_row = await self._gateway.create_news_event_with_intel(
            self._build_news_event_payload(intel_event, source_trace_id)
        )
        ne_id = int(ne_row["id"])
        logger.debug("IntelStreamProducer: news_event created id=%s sie_id=%s", ne_id, sie_id)

        # 2. 构建 envelope 并投递到 stream:events:structured
        envelope = self._build_envelope(intel_event, ne_id, source_trace_id)
        message_id = await self._xadd(envelope)

        # 3. 更新 stream_status
        await self._update_stream_status(sie_id, "produced", message_id)

        logger.info(
            "IntelStreamProducer: 投递成功 sie_id=%s ne_id=%s stream_msg=%s stock=%s title=%s",
            sie_id,
            ne_id,
            message_id,
            intel_event.get("stock_code"),
            str(intel_event.get("title", ""))[:50],
        )
        return message_id

    async def _update_stream_status(self, sie_id: int, status: str, message_id: str | None = None) -> None:
        try:
            await self._gateway.update_intel_event_stream_status(
                sie_id,
                status,
                stream_message_id=message_id,
            )
        except TypeError:
            await self._gateway.update_intel_event_stream_status(sie_id, status)

    def _build_source_trace_id(self, *, raw_doc_id: int, sie_id: int) -> str:
        """贯穿全链路的追踪 ID。"""
        run = self._run_id or "intel"
        return f"{run}:rid_{raw_doc_id}:sie_{sie_id}"

    def _build_news_event_payload(
        self,
        intel_event: Dict[str, Any],
        source_trace_id: str,
    ) -> Dict[str, Any]:
        """构建 news_event 写入 payload。"""
        entities = intel_event.get("entities", {})
        if isinstance(entities, str):
            try:
                entities = json.loads(entities)
            except Exception:
                entities = {}

        return {
            "news_id": None,  # intel 事件无 news_raw 关联
            "event_type": f"intel_{intel_event.get('event_type', 'other')}",
            "impact_industries": [],
            "direction": "中性",
            "confidence": intel_event.get("confidence"),
            "summary": intel_event.get("summary") or intel_event.get("title", ""),
            "theme_directive": {},
            "theme_directive_processed": False,
            "severity_score": intel_event.get("impact_score"),
            "source_weight": 0.8,  # 一手公告权重高于新闻
            "event_time": intel_event.get("publish_time"),
            "entities": entities,
            "causal_claim": {},
            "evidence_set": intel_event.get("evidence_json") or {},
            "raw_event_json": {
                "source_system": intel_event.get("source_system", "cninfo"),
                "source_type": intel_event.get("source_type", "announcement"),
                "intel_event_type": intel_event.get("event_type"),
                "intel_event_level": intel_event.get("event_level"),
            },
            "source_category": "intel",
            "raw_intel_doc_id": int(intel_event.get("raw_doc_id", 0)),
            "structured_intel_event_id": int(intel_event["id"]),
            "source_trace_id": source_trace_id,
        }

    def _build_envelope(
        self,
        intel_event: Dict[str, Any],
        news_event_id: int,
        source_trace_id: str,
    ) -> Dict[str, Any]:
        """构建与 ThemeProcessor._extract_structured_payload 兼容的 envelope。

        ThemeProcessor 会从 payload 中提取 event_id，然后通过
        gateway.get_news_event_for_match(event_id) 获取 news_event 行。
        """
        return {
            "payload": {
                "event_id": news_event_id,
                "source_category": "intel",
                "source_type": intel_event.get("source_type", "announcement"),
                "event_type": f"intel_{intel_event.get('event_type', 'other')}",
                "title": intel_event.get("title", ""),
                "summary": intel_event.get("summary", ""),
                "content": intel_event.get("summary") or intel_event.get("title", ""),
                "run_id": self._run_id,
                "source_trace_id": source_trace_id,
                "raw_intel_doc_id": int(intel_event.get("raw_doc_id", 0)),
                "structured_intel_event_id": int(intel_event["id"]),
                "stock_code": intel_event.get("stock_code"),
                "stock_name": intel_event.get("stock_name"),
                "evidence_json": intel_event.get("evidence_json") or {},
                "publish_time": str(intel_event.get("publish_time") or ""),
            }
        }

    async def _xadd(self, envelope: Dict[str, Any]) -> str:
        """投递消息到 stream:events:structured。"""
        redis = await self._get_redis()
        fields: Dict[str, str] = {}
        for key, value in envelope.items():
            if isinstance(value, dict):
                fields[key] = json.dumps(value, ensure_ascii=False)
            else:
                fields[key] = str(value)
        # 使用 timed-field 时间戳字段（兼容 Redis Stream 消息格式）
        fields.setdefault("timestamp", datetime.now(TZ_CN).isoformat())
        message_id = await redis.xadd(
            self._stream_name,
            fields,
            maxlen=self._maxlen,
        )
        if isinstance(message_id, bytes):
            message_id = message_id.decode()
        return str(message_id)

    async def _get_redis(self) -> Any:
        """懒加载 Redis 客户端。"""
        if self._redis is None:
            import redis.asyncio as aioredis

            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            db = int(os.getenv("REDIS_DB", "0"))
            password = os.getenv("REDIS_PASSWORD") or None

            self._redis = aioredis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
            )
        return self._redis

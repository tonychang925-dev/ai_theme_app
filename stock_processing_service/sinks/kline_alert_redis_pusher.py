"""P1-G: K线支撑告警 Redis Stream 推送器。

Stream: stream:kline:alerts
去重: 同一 stock_id + support_type + alert_type, 60s 冷却。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

import redis.asyncio as aioredis

from stock_processing_service.domain.services.kline_break_detector import SupportAlert

logger = logging.getLogger("sps.kline_alert.redis_pusher")
TZ_CN = timezone(timedelta(hours=8))

STREAM_NAME = "stream:kline:alerts"
STREAM_MAXLEN = 5000


class KlineAlertRedisPusher:
    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 stream_name: str = STREAM_NAME, maxlen: int = STREAM_MAXLEN):
        self._url = redis_url
        self._stream = stream_name
        self._maxlen = maxlen
        self._redis: aioredis.Redis | None = None
        self._pushed: int = 0

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(self._url, decode_responses=True)
                # 探活
                await self._redis.ping()
            except Exception as exc:
                logger.warning("Redis connect failed: %s (push disabled)", exc)
                self._redis = None
        return self._redis

    async def push_alerts(self, alerts: list[SupportAlert]) -> int:
        """批量推送告警到 Redis Stream。返回成功推送数。"""
        if not alerts:
            return 0

        r = await self._get_redis()
        if r is None:
            return 0

        pushed = 0
        for alert in alerts:
            try:
                data = {
                    "item_type": "kline_support_alert",
                    "item_id": f"klsup:{alert.stock_id}:{alert.alert_type.value}:{datetime.now(TZ_CN).strftime('%H%M%S')}",
                    "source_channel": "kline_break_detector",
                    "stock_id": alert.stock_id,
                    "stock_name": alert.stock_name,
                    "support_type": alert.support_type,
                    "support_level": str(round(alert.support_level, 3)),
                    "support_strength": str(round(alert.support_strength, 2)),
                    "current": str(round(alert.current, 3)),
                    "distance_pct": str(alert.distance_pct),
                    "alert_type": alert.alert_type.value,
                    "severity": alert.severity,
                    "quote_ts": alert.quote_ts,
                    "generated_at": alert.generated_at,
                    "pct_chg": str(alert.extra.get("pct_chg", "")),
                }
                await r.xadd(self._stream, data, maxlen=self._maxlen)
                pushed += 1
            except Exception as exc:
                logger.warning("Redis xadd failed for %s: %s", alert.stock_id, exc)

        self._pushed += pushed
        if pushed:
            logger.info("Pushed %d/%d alerts to %s", pushed, len(alerts), self._stream)
        return pushed

    @property
    def pushed_count(self) -> int:
        return self._pushed

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

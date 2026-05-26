"""P1-I-1: 弱转强竞价确认告警 Redis Stream 推送器。

Stream: stream:w2s:alerts
去重: w2s_alert_state:{trade_date}:{candidate_id}:auction_confirm
TTL: 8 hours (到收盘后)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

import redis.asyncio as aioredis

from stock_processing_service.domain.services.w2s_alert_service import W2SAuctionAlert

logger = logging.getLogger("sps.w2s_alert.redis_pusher")
TZ_CN = timezone(timedelta(hours=8))

STREAM_NAME = "stream:w2s:alerts"
STREAM_MAXLEN = 1000
STATE_KEY_PREFIX = "w2s_alert_state"
STATE_TTL = 8 * 3600  # 8 hours


class W2SAlertRedisPusher:
    def __init__(self, redis_url: str = "redis://localhost:6379/0",
                 stream_name: str = STREAM_NAME, maxlen: int = STREAM_MAXLEN):
        self._url = redis_url
        self._stream = stream_name
        self._maxlen = maxlen
        self._redis: aioredis.Redis | None = None
        self._pushed: int = 0

    async def _get_redis(self) -> aioredis.Redis | None:
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(self._url, decode_responses=True)
                await self._redis.ping()
            except Exception as exc:
                logger.warning("Redis unavailable for W2S: %s", exc)
                self._redis = None
        return self._redis

    def _state_key(self, trade_date: str, candidate_id: int) -> str:
        return f"{STATE_KEY_PREFIX}:{trade_date}:{candidate_id}:auction_confirm"

    async def is_duplicate(self, trade_date: str, candidate_id: int) -> bool:
        r = await self._get_redis()
        if r is None:
            return False
        try:
            exists = await r.exists(self._state_key(trade_date, candidate_id))
            return bool(exists)
        except Exception:
            return False

    async def mark_pushed(self, trade_date: str, candidate_id: int) -> None:
        r = await self._get_redis()
        if r is None:
            return
        try:
            await r.setex(self._state_key(trade_date, candidate_id), STATE_TTL, "1")
        except Exception:
            pass

    async def push_alerts(self, alerts: list[W2SAuctionAlert]) -> int:
        if not alerts:
            return 0

        r = await self._get_redis()
        if r is None:
            return 0

        pushed = 0
        for alert in alerts:
            if await self.is_duplicate(alert.trade_date, alert.candidate_id):
                continue

            try:
                data = {
                    "item_type": "w2s_auction_alert" if alert.severity == "important" else "w2s_auction_observe",
                    "alert_stage": "auction_confirm",
                    "trade_date": alert.trade_date,
                    "candidate_trade_date": alert.candidate_trade_date,
                    "candidate_id": str(alert.candidate_id),
                    "stock_id": alert.stock_id,
                    "stock_name": alert.stock_name,
                    "theme_name": alert.theme_name,
                    "candidate_type": alert.candidate_type,
                    "weak_type": alert.weak_type,
                    "confirm_level": alert.confirm_level,
                    "confirm_score": str(alert.confirm_score),
                    "auction_open_pct": str(alert.auction_open_pct),
                    "carry_ratio": str(alert.carry_ratio),
                    "last_minute_ratio": str(alert.last_minute_ratio),
                    "price_path_stability_score": str(alert.price_path_stability_score),
                    "shape_features": json.dumps(alert.shape_features, ensure_ascii=False),
                    "evidence_rules": json.dumps(alert.evidence_rules, ensure_ascii=False),
                    "reject_reason_code": alert.reject_reason_code,
                    "data_status": alert.data_status,
                    "source": alert.source,
                    "severity": alert.severity,
                    "generated_at": alert.generated_at,
                }
                await r.xadd(self._stream, data, maxlen=self._maxlen)
                await self.mark_pushed(alert.trade_date, alert.candidate_id)
                pushed += 1
            except Exception as exc:
                logger.warning("W2S push failed for %s: %s", alert.stock_id, exc)

        self._pushed += pushed
        if pushed:
            logger.warning("W2S_ALERTS: %d pushed to %s", pushed, self._stream)
        return pushed

    @property
    def pushed_count(self) -> int:
        return self._pushed

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

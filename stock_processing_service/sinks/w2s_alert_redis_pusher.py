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
from stock_processing_service.domain.services.w2s_intraday_alert_service import W2SIntradayAlert
from stock_processing_service.domain.services.w2s_support_alert_service import W2SSupportAlert

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

    async def push_support_alerts(self, alerts: list[W2SSupportAlert]) -> int:
        """推送支撑承接观察告警。"""
        if not alerts:
            return 0
        r = await self._get_redis()
        if r is None:
            return 0
        pushed = 0
        for a in alerts:
            dedup_key = f"{STATE_KEY_PREFIX}:{a.trade_date}:{a.candidate_id}:support_observe"
            if await r.exists(dedup_key):
                continue
            try:
                data = {
                    "item_type": a.alert_type,
                    "trade_date": a.trade_date,
                    "candidate_trade_date": a.candidate_trade_date,
                    "candidate_id": str(a.candidate_id),
                    "stock_id": a.stock_id,
                    "stock_name": a.stock_name,
                    "theme_name": a.theme_name,
                    "subject_key": a.subject_key,
                    "pool_entry_type": a.pool_entry_type,
                    "candidate_type": a.candidate_type,
                    "weak_type": a.weak_type,
                    "confirm_level": a.confirm_level,
                    "confirm_score": str(a.confirm_score),
                    "support_type": a.support_type,
                    "support_level": str(round(a.support_level, 3)),
                    "support_strength": str(round(a.support_strength, 2)),
                    "support_source": a.support_source,
                    "support_level_age_days": str(a.support_level_age_days),
                    "current": str(round(a.current, 3)),
                    "distance_pct": str(a.distance_pct),
                    "support_state": a.support_state,
                    "previous_support_state": a.previous_support_state,
                    "severity": a.severity,
                    "confidence": str(a.confidence),
                    "position_label": a.position_label,
                    "pattern_labels": json.dumps(a.pattern_labels, ensure_ascii=False),
                    "evidence_rules": json.dumps(a.evidence_rules, ensure_ascii=False),
                    "d2_evidence_rules": json.dumps(a.d2_evidence_rules, ensure_ascii=False),
                    "d2_source": a.d2_source,
                    "generated_at": a.generated_at,
                }
                await r.xadd(self._stream, data, maxlen=self._maxlen)
                await r.setex(dedup_key, STATE_TTL, "1")
                pushed += 1
            except Exception as exc:
                logger.warning("W2S support push failed for %s: %s", a.stock_id, exc)
        self._pushed += pushed
        if pushed:
            logger.warning("W2S_SUPPORT_ALERTS: %d pushed", pushed)
        return pushed

    async def push_intraday_alerts(self, alerts: list[W2SIntradayAlert]) -> int:
        """推送盘中弱转强观察告警。支持 C→B→A 升级再次推送。"""
        if not alerts:
            return 0
        r = await self._get_redis()
        if r is None:
            return 0
        pushed = 0
        for a in alerts:
            dedup_key = f"{STATE_KEY_PREFIX}:{a.trade_date}:{a.candidate_id}:intraday_turn_strong"
            try:
                prev_raw = await r.get(dedup_key)
                if prev_raw:
                    prev = json.loads(prev_raw)
                    prev_level = prev.get("last_alert_level", "")
                    # 仅允许升级推送 (C→B, B→A, C→A)
                    level_order = {"C": 1, "B": 2, "A": 3}
                    if level_order.get(a.alert_level, 0) <= level_order.get(prev_level, 0):
                        continue
            except Exception:
                pass

            try:
                data = {
                    "item_type": "w2s_intraday_turn_strong_alert" if a.severity == "important" else "w2s_intraday_turn_strong_observe",
                    "alert_stage": "intraday_turn_strong",
                    "trade_date": a.trade_date,
                    "candidate_trade_date": a.candidate_trade_date,
                    "candidate_id": str(a.candidate_id),
                    "stock_id": a.stock_id,
                    "stock_name": a.stock_name,
                    "theme_name": a.theme_name,
                    "candidate_type": a.candidate_type,
                    "weak_type": a.weak_type,
                    "confirm_level": a.confirm_level,
                    "confirm_score": str(a.confirm_score),
                    "current": str(round(a.current, 3)),
                    "vwap": str(round(a.vwap, 4)),
                    "above_vwap_ratio_5m": str(a.above_vwap_ratio_5m),
                    "relative_strength_vs_index": str(round(a.relative_strength_vs_index, 4)),
                    "relative_strength_turn_positive": str(a.relative_strength_turn_positive).lower(),
                    "break_platform_30m": str(a.break_platform_30m).lower(),
                    "platform_high_30m": str(round(a.platform_high_30m, 4)),
                    "amount_acceleration": str(a.amount_acceleration).lower(),
                    "support_state": a.support_state,
                    "position_label": a.position_label,
                    "pattern_labels": json.dumps(a.pattern_labels, ensure_ascii=False),
                    "intraday_score": str(a.intraday_score),
                    "alert_level": a.alert_level,
                    "severity": a.severity,
                    "evidence_rules": json.dumps(a.evidence_rules, ensure_ascii=False),
                    "generated_at": a.generated_at,
                }
                await r.xadd(self._stream, data, maxlen=self._maxlen)
                await r.setex(dedup_key, STATE_TTL, json.dumps({
                    "last_alert_level": a.alert_level,
                    "last_score": a.intraday_score,
                    "last_alert_at": a.generated_at,
                }))
                pushed += 1
            except Exception as exc:
                logger.warning("W2S intraday push failed for %s: %s", a.stock_id, exc)

        self._pushed += pushed
        if pushed:
            logger.warning("W2S_INTRA_ALERTS: %d pushed", pushed)
        return pushed

    @property
    def pushed_count(self) -> int:
        return self._pushed

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

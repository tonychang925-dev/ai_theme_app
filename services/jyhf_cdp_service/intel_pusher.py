from __future__ import annotations

import json
import re
from logging import Logger
from typing import Any

import redis

from services.jyhf_cdp_service.config import JyhfCdpServiceConfig
from services.jyhf_cdp_service.schemas import RawJyhfCdpEvent


class IntelPusher:
    """Converts RawJyhfCdpEvent to intel feed items and publishes to Redis Stream."""

    def __init__(self, config: JyhfCdpServiceConfig, logger: Logger) -> None:
        self._config = config
        self._logger = logger
        self._client: redis.Redis | None = None
        self._stream = config.redis_stream_feed
        self._max_len = 10000

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.Redis(
                host=self._config.redis_host,
                port=self._config.redis_port,
                db=self._config.redis_db,
                socket_connect_timeout=5,
                socket_timeout=5,
                decode_responses=False,
            )
            self._client.ping()
            self._logger.info(
                "intel_pusher connected to Redis %s:%s stream=%s",
                self._config.redis_host,
                self._config.redis_port,
                self._stream,
            )
        return self._client

    def push(self, event: RawJyhfCdpEvent) -> bool:
        """Convert a JYHF CDP event to a feed item and publish to the Redis Stream."""
        try:
            feed_item = self._build_feed_item(event)
            payload = json.dumps(feed_item, ensure_ascii=False)
            self.client.xadd(self._stream, {"payload": payload}, maxlen=self._max_len, approximate=True)
            self._logger.debug("intel_pusher pushed event_id=%s", event.event_id)
            return True
        except Exception:
            self._logger.exception("intel_pusher push failed for event_id=%s", event.event_id)
            return False

    def close(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    # ── private ──────────────────────────────────────────────

    @staticmethod
    def _build_feed_item(event: RawJyhfCdpEvent) -> dict[str, Any]:
        subject_key = IntelPusher._derive_subject_key(event.subject_name)
        occurred_at = IntelPusher._format_occurred_at(event.trade_date, event.event_time)
        confidence = _extraction_confidence(event)
        return {
            "item_id": f"jyhf_cdp:{event.event_id}",
            "event_type": "event",
            "occurred_at": occurred_at,
            "title": event.subject_name,
            "summary": event.driver_title or event.subject_name,
            "theme_names": [event.subject_name] if event.subject_name else [],
            "theme_subject_keys": [subject_key] if subject_key else [],
            "confidence": confidence,
            "impact_score": _pct_to_impact(event.pct_chg),
            "source_type": "jyhf_cdp_dom",
            "source_channel": "jyhf_cdp",
            "pct_chg": event.pct_chg,
            "driver_title": event.driver_title,
            "driver_desc": event.driver_desc,
            "news_source": event.news_source,
            "review_required": _needs_review(event, subject_key, confidence),
        }

    @staticmethod
    def _derive_subject_key(subject_name: str) -> str:
        """Derive a subject_key from the Chinese subject name."""
        key = subject_name.strip()
        key = re.sub(r"[（）()\s]+", "_", key)
        key = re.sub(r"[^\w\u4e00-\u9fff_-]", "", key)
        return key or subject_name.strip()

    @staticmethod
    def _format_occurred_at(trade_date: str, event_time: str) -> str:
        if trade_date and event_time:
            return f"{trade_date}T{event_time}:00+08:00"
        if trade_date:
            return f"{trade_date}T00:00:00+08:00"
        return event_time or ""


def _extraction_confidence(event: RawJyhfCdpEvent) -> float:
    """Score extraction completeness: 0.8 = full, 0.5 = partial, 0.3 = minimal."""
    score = 0.0
    if event.subject_name and event.subject_name.strip():
        score += 0.3
    if event.driver_title and event.driver_title.strip():
        score += 0.3
    if event.trade_date:
        score += 0.1
    if event.event_time:
        score += 0.1
    # clamp to known key points (use round to avoid fp precision issues)
    score = round(score, 1)
    if score >= 0.8:
        return 0.8
    if score >= 0.5:
        return 0.5
    return 0.3


def _needs_review(event: RawJyhfCdpEvent, subject_key: str, confidence: float) -> bool:
    """Determine if an event needs human review.

    Rules:
    - subject_key empty        → review required (unknown theme)
    - confidence < 0.7         → review required (low quality extraction)
    - subject_key + confidence ≥ 0.7 → no review (quality + known theme)
    """
    if not subject_key:
        return True
    if confidence < 0.7:
        return True
    return False


def _pct_to_impact(pct_chg: float | None) -> int:
    if pct_chg is None:
        return 50
    abs_pct = abs(pct_chg)
    if abs_pct >= 9:
        return 90
    if abs_pct >= 5:
        return 75
    if abs_pct >= 2:
        return 60
    if abs_pct >= 0.5:
        return 50
    return 40

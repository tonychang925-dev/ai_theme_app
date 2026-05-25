"""P1-D Redis 双源校验告警推送."""
from __future__ import annotations

import logging

import redis.asyncio as redis

logger = logging.getLogger("sps.crosscheck.publisher")


class CrosscheckPublisher:
    def __init__(self, redis_url: str, stream_name: str = "stream:market:crosscheck", maxlen: int = 5000):
        self._redis_url = redis_url
        self._stream = stream_name
        self._maxlen = maxlen
        self._client: redis.Redis | None = None
        self._pushed: int = 0

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=False)
        return self._client

    async def publish(self, result: dict) -> None:
        """推送校验结果。OK 不推，只推 WARN/CRITICAL/MISSING/STALE."""
        status = result.get("crosscheck_status", "")
        if status == "OK":
            return

        item_type = "market_crosscheck_warning" if status in ("CRITICAL", "WARN") else "market_quote_crosscheck"
        cl = await self._get_client()

        payload = {
            "item_type": item_type,
            "source_channel": "market_crosscheck",
            "trade_date": str(result.get("trade_date", "")),
            "occurred_at": str(result.get("ts", "")),
            "stock_id": str(result.get("stock_id", "")),
            "jyhf_price": str(result.get("jyhf_price") or ""),
            "tdx_price": str(result.get("tdx_price") or ""),
            "price_diff_pct": str(result.get("price_diff_pct") or ""),
            "crosscheck_status": status,
            "severity": result.get("severity", "info"),
            "reason": str(result.get("reason", ""))[:200],
        }
        await cl.xadd(self._stream, payload, maxlen=self._maxlen, approximate=True)
        self._pushed += 1

    @property
    def pushed_count(self) -> int:
        return self._pushed

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None

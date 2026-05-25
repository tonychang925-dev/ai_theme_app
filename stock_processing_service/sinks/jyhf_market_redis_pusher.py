"""Redis Stream 推送器."""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta

import redis.asyncio as aioredis

logger = logging.getLogger("sps.jyhf_market.redis_pusher")
TZ_CN = timezone(timedelta(hours=8))


class JyhfMarketRedisPusher:
    def __init__(self, redis_url: str, stream_name: str, maxlen: int = 10000):
        self._url = redis_url
        self._stream = stream_name
        self._maxlen = maxlen
        self._redis: aioredis.Redis | None = None
        self._pushed: int = 0

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._url, decode_responses=True)
        return self._redis

    async def push_quote(self, quote) -> str | None:
        return await self._push({
            "item_type": "stock_quote", "source_channel": "jyhf_market_api",
            "trade_date": quote.trade_date, "occurred_at": quote.ts,
            "stock_id": quote.stock_id, "stock_name": quote.stock_name or "",
            "current": str(quote.current) if quote.current is not None else "",
            "pct_chg": str(quote.pct_chg) if quote.pct_chg is not None else "",
            "amount": str(quote.amount) if quote.amount is not None else "",
        })

    async def push_index(self, quote) -> str | None:
        return await self._push({
            "item_type": "index_quote", "source_channel": "jyhf_market_api",
            "trade_date": quote.trade_date, "occurred_at": quote.ts,
            "index_code": quote.index_code, "index_name": quote.index_name,
            "current": str(quote.current) if quote.current is not None else "",
            "pct_chg": str(quote.pct_chg) if quote.pct_chg is not None else "",
        })

    async def push_subject_stock(self, quote) -> str | None:
        return await self._push({
            "item_type": "subject_stock_quote", "source_channel": "jyhf_market_api",
            "trade_date": quote.trade_date, "occurred_at": quote.ts,
            "subject_id": quote.subject_id, "stock_id": quote.stock_id,
            "stock_name": quote.stock_name or "",
            "current": str(quote.current) if quote.current is not None else "",
            "pct_chg": str(quote.pct_chg) if quote.pct_chg is not None else "",
            "rank_no": str(quote.rank_no) if quote.rank_no else "",
        })

    async def _push(self, data: dict) -> str | None:
        try:
            r = await self._get_redis()
            data["item_id"] = f"jyhf_{data['item_type']}:{data['trade_date']}:{data.get('stock_id', data.get('index_code',''))}:{datetime.now(TZ_CN).strftime('%H%M%S')}"
            mid = await r.xadd(self._stream, data, maxlen=self._maxlen)
            self._pushed += 1
            return mid
        except Exception as exc:
            logger.warning("Redis push failed: %s", exc)
            return None

    @property
    def pushed_count(self) -> int:
        return self._pushed

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._redis = None

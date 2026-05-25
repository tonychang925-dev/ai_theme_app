"""Redis Stream TDX 行情推送."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta

import redis.asyncio as redis

from stock_processing_service.integrations.tdx_market.schemas import (
    TdxStockQuote, TdxMinuteBar, TdxDailyBar,
)

logger = logging.getLogger("sps.tdx_market.redis_pusher")
TZ_CN = timezone(timedelta(hours=8))


class TdxMarketRedisPusher:
    def __init__(self, redis_url: str, stream_name: str, maxlen: int = 10000):
        self._redis_url = redis_url
        self._stream = stream_name
        self._maxlen = maxlen
        self._client: redis.Redis | None = None
        self._pushed: int = 0

    async def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=False)
        return self._client

    async def push_quote(self, quote: TdxStockQuote) -> None:
        cl = await self._get_client()
        payload = {
            "source": "tdx_mootdx",
            "type": "quote",
            "stock_id": quote.stock_id,
            "system_stock_id": quote.system_stock_id,
            "price": str(quote.price) if quote.price is not None else "",
            "open": str(quote.open) if quote.open is not None else "",
            "high": str(quote.high) if quote.high is not None else "",
            "low": str(quote.low) if quote.low is not None else "",
            "last_close": str(quote.last_close) if quote.last_close is not None else "",
            "amount": str(quote.amount) if quote.amount is not None else "",
            "vol": str(quote.vol) if quote.vol is not None else "",
            "ts": quote.ts,
        }
        await cl.xadd(self._stream, payload, maxlen=self._maxlen, approximate=True)
        self._pushed += 1

    async def push_minute_bars(self, bars: list[TdxMinuteBar]) -> None:
        if not bars:
            return
        cl = await self._get_client()
        # 推送摘要而非每条 bar，避免刷爆 stream
        payload = {
            "source": "tdx_mootdx",
            "type": "minute",
            "stock_id": bars[0].stock_id,
            "system_stock_id": bars[0].system_stock_id,
            "count": str(len(bars)),
            "first_price": str(bars[0].price) if bars[0].price is not None else "",
            "last_price": str(bars[-1].price) if bars[-1].price is not None else "",
            "ts": bars[0].ts,
        }
        await cl.xadd(self._stream, payload, maxlen=self._maxlen, approximate=True)
        self._pushed += 1

    async def push_daily_bars(self, bars: list[TdxDailyBar]) -> None:
        if not bars:
            return
        cl = await self._get_client()
        latest = bars[-1]
        payload = {
            "source": "tdx_mootdx",
            "type": "daily_bar",
            "stock_id": latest.stock_id,
            "system_stock_id": latest.system_stock_id,
            "bar_time": latest.bar_time or "",
            "open": str(latest.open) if latest.open is not None else "",
            "close": str(latest.close) if latest.close is not None else "",
            "bars_count": str(len(bars)),
            "ts": latest.ts,
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

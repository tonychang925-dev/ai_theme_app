"""PostgreSQL TDX 行情入库."""
from __future__ import annotations

import json
import logging
from datetime import date as date_type, datetime

import asyncpg

from stock_processing_service.integrations.tdx_market.schemas import (
    TdxStockQuote, TdxMinuteBar, TdxDailyBar,
)

logger = logging.getLogger("sps.tdx_market.db_sink")


def _to_date(value: str) -> date_type:
    return date_type.fromisoformat(value)


def _to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


class TdxMarketDbSink:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._writes: int = 0

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── quote ──

    async def write_stock_quote(self, quote: TdxStockQuote) -> int:
        pool = await self._get_pool()
        trade_date = _to_date(quote.trade_date)
        ts = _to_dt(quote.ts)
        row = await pool.fetchrow(
            """INSERT INTO tdx_stock_quote_snapshot
               (trade_date, ts, stock_id, system_stock_id, price, open, high, low,
                last_close, amount, vol, servertime,
                bid1, ask1, bid_vol1, ask_vol1,
                bid2, ask2, bid_vol2, ask_vol2,
                bid3, ask3, bid_vol3, ask_vol3,
                bid4, ask4, bid_vol4, ask_vol4,
                bid5, ask5, bid_vol5, ask_vol5,
                raw_json)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,
                       $13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33::jsonb)
               ON CONFLICT (trade_date, stock_id, ts) DO NOTHING RETURNING id""",
            trade_date, ts, quote.stock_id, quote.system_stock_id,
            str(quote.price) if quote.price is not None else None,
            str(quote.open) if quote.open is not None else None,
            str(quote.high) if quote.high is not None else None,
            str(quote.low) if quote.low is not None else None,
            str(quote.last_close) if quote.last_close is not None else None,
            str(quote.amount) if quote.amount is not None else None,
            str(quote.vol) if quote.vol is not None else None,
            quote.servertime,
            str(quote.bid1) if quote.bid1 is not None else None,
            str(quote.ask1) if quote.ask1 is not None else None,
            quote.bid_vol1, quote.ask_vol1,
            str(quote.bid2) if quote.bid2 is not None else None,
            str(quote.ask2) if quote.ask2 is not None else None,
            quote.bid_vol2, quote.ask_vol2,
            str(quote.bid3) if quote.bid3 is not None else None,
            str(quote.ask3) if quote.ask3 is not None else None,
            quote.bid_vol3, quote.ask_vol3,
            str(quote.bid4) if quote.bid4 is not None else None,
            str(quote.ask4) if quote.ask4 is not None else None,
            quote.bid_vol4, quote.ask_vol4,
            str(quote.bid5) if quote.bid5 is not None else None,
            str(quote.ask5) if quote.ask5 is not None else None,
            quote.bid_vol5, quote.ask_vol5,
            json.dumps(quote.raw_json, ensure_ascii=False),
        )
        if row:
            self._writes += 1
            return row["id"]
        return 0

    # ── minute ──

    async def write_minute_bars(self, stock_id: str, bars: list[TdxMinuteBar]) -> int:
        if not bars:
            return 0
        pool = await self._get_pool()
        count = 0
        for b in bars:
            trade_date = _to_date(b.trade_date)
            ts = _to_dt(b.ts)
            row = await pool.fetchrow(
                """INSERT INTO tdx_stock_minute_bar
                   (trade_date, ts, stock_id, system_stock_id, minute_index,
                    price, vol, volume, raw_json)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb)
                   ON CONFLICT (trade_date, stock_id, minute_index, ts) DO NOTHING RETURNING id""",
                trade_date, ts, b.stock_id or stock_id, b.system_stock_id,
                b.minute_index,
                str(b.price) if b.price is not None else None,
                str(b.vol) if b.vol is not None else None,
                str(b.volume) if b.volume is not None else None,
                json.dumps(b.raw_json, ensure_ascii=False),
            )
            if row:
                count += 1
                self._writes += 1
        return count

    # ── daily bars ──

    async def write_daily_bars(self, stock_id: str, bars: list[TdxDailyBar]) -> int:
        if not bars:
            return 0
        pool = await self._get_pool()
        count = 0
        for b in bars:
            trade_date = _to_date(b.trade_date)
            ts = _to_dt(b.ts)
            bar_time = _to_dt(b.bar_time) if b.bar_time else None
            row = await pool.fetchrow(
                """INSERT INTO tdx_stock_daily_bar
                   (trade_date, ts, stock_id, system_stock_id, bar_time,
                    open, high, low, close, vol, amount, frequency, raw_json)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
                   ON CONFLICT (stock_id, bar_time, frequency) DO NOTHING RETURNING id""",
                trade_date, ts, b.stock_id or stock_id, b.system_stock_id, bar_time,
                str(b.open) if b.open is not None else None,
                str(b.high) if b.high is not None else None,
                str(b.low) if b.low is not None else None,
                str(b.close) if b.close is not None else None,
                str(b.vol) if b.vol is not None else None,
                str(b.amount) if b.amount is not None else None,
                b.frequency,
                json.dumps(b.raw_json, ensure_ascii=False),
            )
            if row:
                count += 1
                self._writes += 1
        return count

    @property
    def write_count(self) -> int:
        return self._writes

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

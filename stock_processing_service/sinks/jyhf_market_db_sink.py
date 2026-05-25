"""PostgreSQL 行情入库."""
from __future__ import annotations

import json
import logging
import hashlib

import asyncpg

from stock_processing_service.integrations.jyhf_market.schemas import (
    JyhfIndexQuote, JyhfStockQuote, JyhfSubjectStockQuote,
)

logger = logging.getLogger("sps.jyhf_market.db_sink")


class JyhfMarketDbSink:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._writes: int = 0

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    async def write_raw_capture(self, endpoint_key: str, endpoint: str, raw: dict, params: dict | None = None) -> int:
        pool = await self._get_pool()
        raw_str = json.dumps(raw, ensure_ascii=False)
        resp_hash = hashlib.sha256(raw_str.encode()).hexdigest()[:16]
        row = await pool.fetchrow(
            """INSERT INTO jyhf_market_raw_capture
               (endpoint_key, endpoint, method, request_params, response_hash, raw_json, parse_status)
               VALUES ($1,$2,$3,$4,$5,$6::jsonb,'ok')
               ON CONFLICT DO NOTHING RETURNING id""",
            endpoint_key, endpoint, "GET", json.dumps(params or {}), resp_hash, raw_str,
        )
        if row:
            self._writes += 1
            return row["id"]
        return 0

    async def write_stock_quote(self, quote: JyhfStockQuote) -> int:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """INSERT INTO jyhf_stock_quote_snapshot
               (trade_date, ts, stock_id, stock_name, current, open, high, low, close,
                pct_chg, amount, vol, pe, market_value, limit_up, limit_down,
                source_endpoint, raw_json)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18::jsonb)
               ON CONFLICT (trade_date, stock_id, ts) DO NOTHING RETURNING id""",
            quote.trade_date, quote.ts, quote.stock_id, quote.stock_name,
            str(quote.current) if quote.current is not None else None,
            str(quote.open) if quote.open is not None else None,
            str(quote.high) if quote.high is not None else None,
            str(quote.low) if quote.low is not None else None,
            str(quote.close) if quote.close is not None else None,
            str(quote.pct_chg) if quote.pct_chg is not None else None,
            str(quote.amount) if quote.amount is not None else None,
            str(quote.vol) if quote.vol is not None else None,
            str(quote.pe) if quote.pe is not None else None,
            str(quote.market_value) if quote.market_value is not None else None,
            str(quote.limit_up) if quote.limit_up is not None else None,
            str(quote.limit_down) if quote.limit_down is not None else None,
            quote.source_endpoint,
            json.dumps(quote.raw_json, ensure_ascii=False),
        )
        if row:
            self._writes += 1
            return row["id"]
        return 0

    async def write_index_quote(self, quote: JyhfIndexQuote) -> int:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """INSERT INTO jyhf_index_quote_snapshot
               (trade_date, ts, index_code, index_name, current, open, high, low, close,
                pct_chg, amount, vol, raw_json)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb)
               ON CONFLICT (trade_date, index_code, ts) DO NOTHING RETURNING id""",
            quote.trade_date, quote.ts, quote.index_code, quote.index_name,
            str(quote.current) if quote.current is not None else None,
            str(quote.open) if quote.open is not None else None,
            str(quote.high) if quote.high is not None else None,
            str(quote.low) if quote.low is not None else None,
            str(quote.close) if quote.close is not None else None,
            str(quote.pct_chg) if quote.pct_chg is not None else None,
            str(quote.amount) if quote.amount is not None else None,
            str(quote.vol) if quote.vol is not None else None,
            json.dumps(quote.raw_json, ensure_ascii=False),
        )
        if row:
            self._writes += 1
            return row["id"]
        return 0

    async def write_subject_stock_quote(self, quote: JyhfSubjectStockQuote) -> int:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """INSERT INTO jyhf_subject_stock_quote_snapshot
               (trade_date, ts, subject_id, subject_name, stock_id, stock_name,
                current, pct_chg, amount, vol, rank_no, raw_json)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
               ON CONFLICT (trade_date, subject_id, stock_id, ts) DO NOTHING RETURNING id""",
            quote.trade_date, quote.ts, quote.subject_id, quote.subject_name or "",
            quote.stock_id, quote.stock_name,
            str(quote.current) if quote.current is not None else None,
            str(quote.pct_chg) if quote.pct_chg is not None else None,
            str(quote.amount) if quote.amount is not None else None,
            str(quote.vol) if quote.vol is not None else None,
            str(quote.rank_no) if quote.rank_no is not None else None,
            json.dumps(quote.raw_json, ensure_ascii=False),
        )
        if row:
            self._writes += 1
            return row["id"]
        return 0

    @property
    def write_count(self) -> int:
        return self._writes

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

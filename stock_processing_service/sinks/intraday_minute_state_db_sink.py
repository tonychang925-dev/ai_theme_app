"""P1-I-3: 分钟状态 DB 写入器。"""
from __future__ import annotations

import json
import logging
from datetime import date as date_type, datetime, timezone, timedelta

import asyncpg

from stock_processing_service.domain.services.intraday_minute_state_builder import MinuteBar

logger = logging.getLogger("sps.intraday_minute_state.sink")
TZ_CN = timezone(timedelta(hours=8))


def _to_date(v: str) -> date_type:
    return datetime.strptime(v[:10], "%Y-%m-%d").date()


def _to_dt(v: str) -> datetime:
    """将 ISO 字符串转为 datetime (asyncpg timestamptz 要求)。"""
    s = str(v).strip()
    # 处理各种 ISO 格式
    for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S+00:00", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S+00:00"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return datetime.fromisoformat(s)


class IntradayMinuteStateDbSink:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    async def write_stock_bars(self, bars: list[MinuteBar]) -> int:
        if not bars:
            return 0
        pool = await self._get_pool()
        written = 0
        for b in bars:
            try:
                td = _to_date(b.trade_date)
                ts_dt = _to_dt(b.minute_ts)
                row = await pool.fetchrow(
                    """INSERT INTO intraday_stock_minute_state AS t
                       (trade_date, minute_ts, stock_id, stock_name,
                        open, high, low, close, current, pct_chg,
                        amount, vol, amount_delta, vol_delta,
                        vwap, above_vwap, minute_return, day_return,
                        index_code, index_pct_chg, relative_strength_vs_index,
                        platform_high_30m, platform_low_30m, break_platform_30m,
                        source_quote_count, raw_json)
                       VALUES ($1::date, $2, $3, $4,
                               $5::numeric, $6::numeric, $7::numeric, $8::numeric, $9::numeric, $10::numeric,
                               $11::numeric, $12::numeric, $13::numeric, $14::numeric,
                               $15::numeric, $16::boolean, $17::numeric, $18::numeric,
                               $19, $20::numeric, $21::numeric,
                               $22::numeric, $23::numeric, $24::boolean,
                               $25, $26::jsonb)
                       ON CONFLICT (trade_date, minute_ts, stock_id) DO UPDATE SET
                        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                        close=EXCLUDED.close, current=EXCLUDED.current, pct_chg=EXCLUDED.pct_chg,
                        amount=EXCLUDED.amount, vol=EXCLUDED.vol,
                        amount_delta=EXCLUDED.amount_delta, vol_delta=EXCLUDED.vol_delta,
                        vwap=EXCLUDED.vwap, above_vwap=EXCLUDED.above_vwap,
                        minute_return=EXCLUDED.minute_return, day_return=EXCLUDED.day_return,
                        relative_strength_vs_index=EXCLUDED.relative_strength_vs_index,
                        platform_high_30m=EXCLUDED.platform_high_30m,
                        platform_low_30m=EXCLUDED.platform_low_30m,
                        break_platform_30m=EXCLUDED.break_platform_30m,
                        source_quote_count=EXCLUDED.source_quote_count,
                        raw_json=EXCLUDED.raw_json,
                        updated_at=NOW()
                       RETURNING id""",
                    td, ts_dt, b.stock_id, b.stock_name,
                    str(b.open), str(b.high), str(b.low), str(b.close), str(b.current), str(b.pct_chg),
                    str(b.amount), str(b.vol), str(b.amount_delta), str(b.vol_delta),
                    str(b.vwap), b.above_vwap, str(b.minute_return), str(b.day_return),
                    b.index_code, str(b.index_pct_chg), str(b.relative_strength_vs_index),
                    str(b.platform_high_30m), str(b.platform_low_30m), b.break_platform_30m,
                    b.source_quote_count,
                    json.dumps(b.raw_json, ensure_ascii=False),
                )
                if row:
                    written += 1
            except Exception as exc:
                logger.warning("Write minute bar failed for %s at %s: %s", b.stock_id, b.minute_ts, exc)

        logger.info("Wrote %d/%d stock minute bars", written, len(bars))
        return written

    async def write_index_minutes(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        pool = await self._get_pool()
        written = 0
        for r in rows:
            ts_str = str(r.get("minute_ts") or "")
            try:
                td = _to_date(ts_str)
            except Exception:
                continue
            try:
                ts_dt = _to_dt(ts_str)
                row = await pool.fetchrow(
                    """INSERT INTO intraday_index_minute_state AS t
                       (trade_date, minute_ts, index_code, index_name,
                        open, high, low, close, current, pct_chg,
                        amount, vol, source_quote_count, raw_json)
                       VALUES ($1::date, $2, $3, $4,
                               $5::numeric, $6::numeric, $7::numeric, $8::numeric, $9::numeric, $10::numeric,
                               $11::numeric, $12::numeric, $13, $14::jsonb)
                       ON CONFLICT (trade_date, minute_ts, index_code) DO UPDATE SET
                        open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                        close=EXCLUDED.close, current=EXCLUDED.current, pct_chg=EXCLUDED.pct_chg,
                        amount=EXCLUDED.amount, vol=EXCLUDED.vol,
                        source_quote_count=EXCLUDED.source_quote_count,
                        raw_json=EXCLUDED.raw_json,
                        updated_at=NOW()
                       RETURNING id""",
                    td, ts_dt, str(r.get("index_code") or ""), str(r.get("index_name") or ""),
                    str(r.get("open_val") or 0), str(r.get("high_val") or 0),
                    str(r.get("low_val") or 0), str(r.get("close_val") or 0),
                    str(r.get("current_val") or 0), str(r.get("pct_chg_val") or 0),
                    str(r.get("amount_val") or 0), str(r.get("vol_val") or 0),
                    int(r.get("quote_count") or 0),
                    json.dumps({"source": "jyhf_index_quote_snapshot"}, ensure_ascii=False),
                )
                if row:
                    written += 1
            except Exception as exc:
                logger.warning("Write index minute failed: %s", exc)

        logger.info("Wrote %d/%d index minute rows", written, len(rows))
        return written

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

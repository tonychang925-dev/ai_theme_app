"""P1-D DB 读写 — 双源最新行情查询 + 校验结果写入."""
from __future__ import annotations

import json
import logging
from datetime import date as date_type, datetime

import asyncpg

logger = logging.getLogger("sps.crosscheck.repository")


class CrosscheckRepository:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 读取 ──

    async def fetch_latest_jyhf_quotes(
        self, max_age_seconds: float = 60.0,
    ) -> dict[str, dict]:
        """返回 {stock_id: {ts, price, pct_chg, amount, vol}} 最近 max_age_seconds 内."""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT DISTINCT ON (stock_id)
                 stock_id, ts, current as price, pct_chg, amount, vol
               FROM jyhf_stock_quote_snapshot
               WHERE ts >= NOW() - ($1::text || ' seconds')::INTERVAL
               ORDER BY stock_id, ts DESC""",
            str(int(max_age_seconds)),
        )
        return {row["stock_id"]: dict(row) for row in rows}

    async def fetch_latest_tdx_quotes(
        self, max_age_seconds: float = 60.0,
    ) -> dict[str, dict]:
        """返回 {stock_id: {ts, price, pct_chg, amount, vol}} 最近 max_age_seconds 内.

        TDX 没有 pct_chg，用 (price - last_close) / last_close 推算。
        """
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT DISTINCT ON (stock_id)
                 stock_id, ts, price, last_close, amount, vol
               FROM tdx_stock_quote_snapshot
               WHERE ts >= NOW() - ($1::text || ' seconds')::INTERVAL
               ORDER BY stock_id, ts DESC""",
            str(int(max_age_seconds)),
        )
        result = {}
        for row in rows:
            d = dict(row)
            # 推算 pct_chg
            price = d.get("price")
            last_close = d.get("last_close")
            if price is not None and last_close is not None and last_close != 0:
                d["pct_chg"] = float((price - last_close) / last_close * 100)
            else:
                d["pct_chg"] = None
            result[row["stock_id"]] = d
        return result

    # ── 写入 ──

    async def insert_crosscheck(self, result: dict) -> int | None:
        pool = await self._get_pool()
        row = await pool.fetchrow(
            """INSERT INTO market_quote_crosscheck
               (trade_date, ts, stock_id,
                jyhf_ts, tdx_ts,
                jyhf_price, tdx_price, price_diff, price_diff_pct,
                jyhf_pct_chg, tdx_pct_chg, pct_chg_diff,
                jyhf_amount, tdx_amount, amount_diff_pct,
                jyhf_vol, tdx_vol, vol_diff_pct,
                jyhf_delay_seconds, tdx_delay_seconds,
                crosscheck_status, severity, reason, raw_json)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24::jsonb)
               ON CONFLICT (trade_date, stock_id, ts) DO NOTHING RETURNING id""",
            _to_date(result.get("trade_date")),
            _to_dt(result.get("ts")),
            result.get("stock_id"),
            _to_dt(result.get("jyhf_ts")),
            _to_dt(result.get("tdx_ts")),
            _to_str(result.get("jyhf_price")),
            _to_str(result.get("tdx_price")),
            _to_str(result.get("price_diff")),
            _to_str(result.get("price_diff_pct")),
            _to_str(result.get("jyhf_pct_chg")),
            _to_str(result.get("tdx_pct_chg")),
            _to_str(result.get("pct_chg_diff")),
            _to_str(result.get("jyhf_amount")),
            _to_str(result.get("tdx_amount")),
            _to_str(result.get("amount_diff_pct")),
            _to_str(result.get("jyhf_vol")),
            _to_str(result.get("tdx_vol")),
            _to_str(result.get("vol_diff_pct")),
            _to_str(result.get("jyhf_delay_seconds")),
            _to_str(result.get("tdx_delay_seconds")),
            result.get("crosscheck_status"),
            result.get("severity"),
            str(result.get("reason", ""))[:500],
            json.dumps(result.get("raw", {}), ensure_ascii=False),
        )
        return row["id"] if row else None

    async def get_status_summary(self, max_age_seconds: float = 120.0) -> dict:
        """返回最近的校验汇总."""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT crosscheck_status, severity, COUNT(*) as cnt
               FROM market_quote_crosscheck
               WHERE ts >= NOW() - ($1::text || ' seconds')::INTERVAL
               GROUP BY crosscheck_status, severity
               ORDER BY crosscheck_status""",
            str(int(max_age_seconds)),
        )
        return {
            "window_seconds": max_age_seconds,
            "breakdown": [{"status": r["crosscheck_status"], "severity": r["severity"], "count": r["cnt"]} for r in rows],
        }

    async def get_stock_ids_with_data(self, max_age_seconds: float = 30.0) -> set[str]:
        """返回两边最近都有数据的 stock_id 集合."""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT j.stock_id
               FROM (
                 SELECT DISTINCT ON (stock_id) stock_id
                 FROM jyhf_stock_quote_snapshot
                 WHERE ts >= NOW() - ($1::text || ' seconds')::INTERVAL
               ) j
               INNER JOIN (
                 SELECT DISTINCT ON (stock_id) stock_id
                 FROM tdx_stock_quote_snapshot
                 WHERE ts >= NOW() - ($1::text || ' seconds')::INTERVAL
               ) t ON j.stock_id = t.stock_id""",
            str(int(max_age_seconds)),
        )
        return {row["stock_id"] for row in rows}

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


def _to_dt(value) -> datetime | None:
    if value is None:
        return None
    try:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _to_date(value: str | None) -> date_type | None:
    if value is None:
        return None
    try:
        return date_type.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _to_str(value) -> str | None:
    if value is None:
        return None
    return str(value)

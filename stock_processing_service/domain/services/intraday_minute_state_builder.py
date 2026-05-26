"""P1-I-3: 盘中分钟状态构建器。

从 jyhf_stock_quote_snapshot / jyhf_index_quote_snapshot
聚合分钟级 OHLC + VWAP + 相对大盘 + 30m 平台。

仅处理候选池 + 强势股范围，不做全市场。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import asyncpg

logger = logging.getLogger("sps.intraday_minute_state")

TZ_CN = timezone(timedelta(hours=8))


@dataclass
class MinuteBar:
    trade_date: str
    minute_ts: str
    stock_id: str
    stock_name: str
    open: float
    high: float
    low: float
    close: float
    current: float
    pct_chg: float
    amount: float
    vol: float
    amount_delta: float
    vol_delta: float
    vwap: float
    above_vwap: bool
    minute_return: float
    day_return: float
    index_code: str
    index_pct_chg: float
    relative_strength_vs_index: float
    platform_high_30m: float
    platform_low_30m: float
    break_platform_30m: bool
    source_quote_count: int
    raw_json: dict = field(default_factory=dict)


@dataclass
class BuildResult:
    universe_count: int
    stock_minute_rows: int
    index_minute_rows: int
    missing_quote_count: int
    latest_minute_ts: str


class IntradayMinuteStateBuilder:
    """分钟状态构建器。"""

    LOOKBACK_MINUTES = 5  # 聚合窗口 (分钟)

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── universe ──

    async def load_universe(self, trade_date: str) -> list[str]:
        """加载候选池 + 强势股范围 stock_id 列表。"""
        pool = await self._get_pool()
        ids: set[str] = set()
        td = date.fromisoformat(trade_date)

        # D1 候选 (next_trade_date = today)
        rows = await pool.fetch(
            "SELECT DISTINCT stock_id FROM weak_to_strong_candidate_pool WHERE next_trade_date = $1", td)
        for r in rows:
            ids.add(str(r["stock_id"]))

        # 强势股
        rows = await pool.fetch(
            """SELECT DISTINCT stock_id FROM strong_stock_watch_pool
               WHERE COALESCE(watch_status,'') != 'removed'""")
        for r in rows:
            ids.add(str(r["stock_id"]))

        return sorted(ids)

    # ── 聚合 ──

    async def build_index_minutes(self, trade_date: str) -> list[dict]:
        """聚合指数分钟状态。"""
        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        rows = await pool.fetch(
            """SELECT
                 date_trunc('minute', ts) AS minute_ts,
                 index_code,
                 MAX(index_name) AS index_name,
                 (array_agg(open ORDER BY ts))[1] AS open_val,
                 MAX(high) AS high_val,
                 MIN(low) AS low_val,
                 (array_agg(close ORDER BY ts DESC))[1] AS close_val,
                 (array_agg(current ORDER BY ts DESC))[1] AS current_val,
                 (array_agg(pct_chg ORDER BY ts DESC))[1] AS pct_chg_val,
                 (array_agg(amount ORDER BY ts DESC))[1] AS amount_val,
                 (array_agg(vol ORDER BY ts DESC))[1] AS vol_val,
                 COUNT(*) AS quote_count
               FROM jyhf_index_quote_snapshot
               WHERE trade_date = $1
               GROUP BY date_trunc('minute', ts), index_code
               ORDER BY minute_ts""",
            td,
        )
        return [dict(r) for r in rows]

    async def build_stock_minutes(self, trade_date: str, stock_ids: list[str]) -> list[MinuteBar]:
        """聚合股票分钟状态（仅指定 universe）。"""
        if not stock_ids:
            return []

        pool = await self._get_pool()
        td = date.fromisoformat(trade_date)
        codes = [sid.replace(".SZ", "").replace(".SH", "").replace(".BJ", "") for sid in stock_ids]
        code_to_sid = {c: s for c, s in zip(codes, stock_ids)}

        # 聚合分钟 OHLC
        rows = await pool.fetch(
            """SELECT
                 split_part(stock_id, '.', 1) AS code,
                 date_trunc('minute', ts) AS minute_ts,
                 (array_agg(open ORDER BY ts))[1] AS open_val,
                 MAX(high) AS high_val,
                 MIN(low) AS low_val,
                 (array_agg(close ORDER BY ts DESC))[1] AS close_val,
                 (array_agg(current ORDER BY ts DESC))[1] AS current_val,
                 (array_agg(pct_chg ORDER BY ts DESC))[1] AS pct_chg_val,
                 (array_agg(amount ORDER BY ts DESC))[1] AS amount_val,
                 (array_agg(vol ORDER BY ts DESC))[1] AS vol_val,
                 (array_agg(stock_name ORDER BY ts DESC))[1] AS stock_name_val,
                 COUNT(*) AS quote_count
               FROM jyhf_stock_quote_snapshot
               WHERE trade_date = $1
                 AND split_part(stock_id, '.', 1) = ANY($2::text[])
                 AND current IS NOT NULL
               GROUP BY split_part(stock_id, '.', 1), date_trunc('minute', ts)
               ORDER BY minute_ts""",
            td, codes,
        )

        # 计算 delta / vwap / 30m platform
        prev_by_stock: dict[str, dict] = {}
        bars: list[MinuteBar] = []

        for r in rows:
            code = str(r["code"])
            sid = code_to_sid.get(code, code)
            minute_ts = str(r["minute_ts"])
            current = float(r["current_val"] or 0)
            pct = float(r["pct_chg_val"] or 0)
            amt = float(r["amount_val"] or 0)
            vol = float(r["vol_val"] or 0)
            hi = float(r["high_val"] or 0)
            lo = float(r["low_val"] or 0)
            op = float(r["open_val"] or 0)
            cl = float(r["close_val"] or 0)
            name = str(r["stock_name_val"] or "")

            prev = prev_by_stock.get(sid, {})
            amt_delta = max(0, amt - prev.get("amount", amt))
            vol_delta = max(0, vol - prev.get("vol", vol))

            # VWAP (raw — 单位待确认)
            vwap_val = amt_delta / vol_delta if vol_delta > 0 else current

            # minute_return = 当前分钟涨跌
            prev_close = prev.get("close", op)
            min_ret = (cl - prev_close) / prev_close if prev_close > 0 else 0

            # day_return = 当日涨跌
            day_ret = pct / 100 if pct else 0

            above_vwap = current > vwap_val

            # 30m platform (滑动窗口内 hi/lo)
            platform_hi = hi
            platform_lo = lo
            break_platform = False
            recent = [b for b in bars if b.stock_id == sid][-30:]
            if recent:
                platform_hi = max(b.high for b in recent)
                platform_lo = min(b.low for b in recent)
                break_platform = current > platform_hi

            prev_by_stock[sid] = {"amount": amt, "vol": vol, "close": cl}

            bars.append(MinuteBar(
                trade_date=trade_date, minute_ts=minute_ts,
                stock_id=sid, stock_name=name,
                open=op, high=hi, low=lo, close=cl, current=current, pct_chg=pct,
                amount=amt, vol=vol, amount_delta=amt_delta, vol_delta=vol_delta,
                vwap=round(vwap_val, 4), above_vwap=above_vwap,
                minute_return=round(min_ret, 6), day_return=round(day_ret, 6),
                index_code="", index_pct_chg=0, relative_strength_vs_index=0,
                platform_high_30m=round(platform_hi, 4),
                platform_low_30m=round(platform_lo, 4),
                break_platform_30m=break_platform,
                source_quote_count=int(r["quote_count"]),
                raw_json={
                    "raw_amount": amt, "raw_vol": vol,
                    "amount_delta": amt_delta, "vol_delta": vol_delta,
                    "vwap_unit_checked": False,
                },
            ))

        logger.info("Built %d minute bars for %d stocks", len(bars), len(prev_by_stock))
        return bars

    async def apply_index_relative(self, bars: list[MinuteBar],
                                   index_minutes: list[dict]) -> list[MinuteBar]:
        """将指数分钟状态应用到股票分钟 bar。"""
        # 取第一个指数 (上证) 作为大盘基准
        primary_index = "000001"  # 上证指数
        idx_by_minute: dict[str, dict] = {}
        for im in index_minutes:
            code = str(im.get("index_code") or "")
            # JYHF index_code 可能是纯数字或带名称
            ts = str(im.get("minute_ts") or "")
            key = ts[:19] if len(ts) >= 19 else ts
            if code not in ("000001", "1", "1A0001", "999999"):
                # 也接受其他指数，优先上证
                if key not in idx_by_minute:
                    idx_by_minute[key] = {}
            idx_by_minute.setdefault(key, {})[code] = {
                "pct_chg": float(im.get("pct_chg_val") or 0),
                "code": code,
            }

        for b in bars:
            mt = b.minute_ts[:19] if len(b.minute_ts) >= 19 else b.minute_ts
            idx_entry = idx_by_minute.get(mt, {})
            # 优先上证，否则取第一个
            primary = idx_entry.get("000001") or idx_entry.get("1") or next(iter(idx_entry.values()), None) if idx_entry else None
            if primary:
                b.index_code = primary.get("code", "")
                b.index_pct_chg = round(primary.get("pct_chg", 0), 4)
                b.relative_strength_vs_index = round(b.pct_chg - b.index_pct_chg, 4)

        return bars

    # ── 主流程 ──

    async def build(self, trade_date: str) -> BuildResult:
        """构建分钟状态层。"""
        universe = await self.load_universe(trade_date)
        if not universe:
            return BuildResult(0, 0, 0, 0, "")

        stock_bars = await self.build_stock_minutes(trade_date, universe)
        index_minutes = await self.build_index_minutes(trade_date)

        # 应用指数相对强度
        stock_bars = await self.apply_index_relative(stock_bars, index_minutes)

        latest = max((b.minute_ts for b in stock_bars), default="")

        with_quotes = len({b.stock_id for b in stock_bars})
        missing = len(universe) - with_quotes

        return BuildResult(
            universe_count=len(universe),
            stock_minute_rows=len(stock_bars),
            index_minute_rows=len(index_minutes),
            missing_quote_count=max(0, missing),
            latest_minute_ts=latest,
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

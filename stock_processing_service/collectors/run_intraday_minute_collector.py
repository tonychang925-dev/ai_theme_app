"""P1-I-3: 盘中分钟状态采集器。

从 jyhf_stock_quote_snapshot 读取实时快照 → 聚合分钟 OHLC → 写入 intraday_stock_minute_state。

后台循环运行，间隔 30s。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import time as _time
from datetime import date, datetime as dt, timezone, timedelta
from pathlib import Path

import asyncpg

logger = logging.getLogger("intraday_minute_collector")

TZ_CN = timezone(timedelta(hours=8))

DB_DSN = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/stock_data_test")


async def get_pool():
    return await asyncpg.create_pool(DB_DSN, min_size=1, max_size=3)


async def get_watch_stock_ids(pool, trade_date: date) -> list[str]:
    """获取今日监控池股票列表：候选池 + strong_watch pool。"""
    rows = await pool.fetch(
        """SELECT DISTINCT stock_id FROM weak_to_strong_candidate_pool
           WHERE trade_date = (SELECT MAX(trade_date) FROM weak_to_strong_candidate_pool)
           UNION
           SELECT DISTINCT stock_id FROM strong_watch_pool_daily_rebuild
           WHERE trade_date = $1
           LIMIT 150""",
        trade_date,
    )
    return [r["stock_id"] for r in rows]


async def build_minute_bars(
    pool, stock_ids: list[str], trade_date: date, last_minute: str | None
) -> tuple[list[dict], str | None]:
    """从 jyhf_stock_quote_snapshot 聚合当前分钟的 OHLC 数据。"""
    rows = await pool.fetch(
        """SELECT stock_id,
                  date_trunc('minute', ts) AS minute_bucket,
                  MAX(current) AS high, MIN(current) AS low,
                  (array_agg(current ORDER BY ts))[1] AS open,
                  (array_agg(current ORDER BY ts DESC))[1] AS close,
                  MAX(vol) - MIN(vol) AS vol_delta,
                  MAX(amount) - MIN(amount) AS amount_delta,
                  MIN(ts) AS first_ts, MAX(ts) AS last_ts,
                  COUNT(*) AS tick_count,
                  MIN(pct_chg) AS min_pct, MAX(pct_chg) AS max_pct
           FROM jyhf_stock_quote_snapshot
           WHERE trade_date = $1::date
             AND stock_id = ANY($2::text[])
             AND ts >= $1::date + time '09:15'
           GROUP BY stock_id, date_trunc('minute', ts)""",
        trade_date, stock_ids,
    )
    bars = []
    for r in rows:
        if r["open"] is None or r["close"] is None:
            continue
        minute_key = r["last_ts"].strftime("%Y-%m-%d %H:%M")
        # VWAP
        vol_d = float(r["vol_delta"] or 0)
        amt_d = float(r["amount_delta"] or 0)
        close = float(r["close"] or 0)
        vwap = amt_d / (vol_d * 100) if vol_d > 0 and amt_d > 0 else close

        bars.append({
            "trade_date": trade_date.isoformat(),
            "stock_id": r["stock_id"],
            "minute_ts": r["last_ts"].isoformat(),
            "open": float(r["open"]),
            "high": float(r["high"] or 0),
            "low": float(r["low"] or 0),
            "close": close,
            "vol_delta": vol_d,
            "amount_delta": amt_d,
            "vwap": round(vwap, 2),
            "tick_count": int(r["tick_count"] or 0),
            "minute_key": minute_key,
        })
    return bars, last_minute


async def upsert_minute_bars(pool, bars: list[dict]) -> int:
    """批量 upsert 到 intraday_stock_minute_state。"""
    if not bars:
        return 0
    written = 0
    async with pool.acquire() as conn:
        for b in bars:
            try:
                td = date.fromisoformat(b["trade_date"])
                mts = dt.fromisoformat(b["minute_ts"])
                await conn.execute(
                    """INSERT INTO intraday_stock_minute_state
                       (trade_date, stock_id, minute_ts, open, high, low, close,
                        current, vol_delta, amount_delta, vwap, source_quote_count)
                       VALUES ($1::date, $2, $3::timestamptz, $4, $5, $6, $7, $7, $8, $9, $10, 1)
                       ON CONFLICT (trade_date, minute_ts, stock_id) DO UPDATE SET
                         high = GREATEST(intraday_stock_minute_state.high, EXCLUDED.high),
                         low = LEAST(intraday_stock_minute_state.low, EXCLUDED.low),
                         close = EXCLUDED.close,
                         current = EXCLUDED.current,
                         vol_delta = EXCLUDED.vol_delta,
                         amount_delta = EXCLUDED.amount_delta,
                         vwap = EXCLUDED.vwap,
                         source_quote_count = intraday_stock_minute_state.source_quote_count + 1""",
                    td, b["stock_id"], mts,
                    b["open"], b["high"], b["low"], b["close"],
                    b["vol_delta"], b["amount_delta"], b["vwap"],
                )
                written += 1
            except Exception as exc:
                logger.warning("Upsert failed for %s: %s", b.get("stock_id"), exc)
    return written


async def ensure_table(pool):
    """确保目标表存在。"""
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS intraday_stock_minute_state (
            trade_date date NOT NULL,
            stock_id text NOT NULL,
            minute_ts timestamptz NOT NULL,
            open double precision,
            high double precision,
            low double precision,
            close double precision,
            vol_delta double precision DEFAULT 0,
            amount_delta double precision DEFAULT 0,
            vwap double precision DEFAULT 0,
            tick_count int DEFAULT 0,
            created_at timestamptz DEFAULT now(),
            PRIMARY KEY (trade_date, stock_id, minute_ts)
        )
    """)


async def main_loop():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Intraday minute collector starting dsn=%s", DB_DSN.replace("postgresql://postgres:", "postgresql://***:"))

    pool = await asyncpg.create_pool(DB_DSN, min_size=2, max_size=5)
    await ensure_table(pool)

    interval = int(os.getenv("INTRADAY_MINUTE_INTERVAL_SECONDS", "30"))
    last_minute: str | None = None

    # ── 确保指数分钟表存在 ──
    await pool.execute("""
        CREATE TABLE IF NOT EXISTS intraday_index_minute_state (
            trade_date date NOT NULL,
            index_code text NOT NULL,
            minute_ts timestamptz NOT NULL,
            pct_chg double precision DEFAULT 0,
            PRIMARY KEY (trade_date, index_code, minute_ts)
        )
    """)

    async def collect_index_bars(trade_date: date) -> int:
        """从 jyhf_index_quote_snapshot 聚合指数分钟数据。"""
        rows = await pool.fetch(
            """SELECT index_code, minute_ts,
                      MAX(pct_chg) AS high_pct, MIN(pct_chg) AS low_pct,
                      (array_agg(pct_chg ORDER BY ts))[1] AS open_pct,
                      (array_agg(pct_chg ORDER BY ts DESC))[1] AS close_pct,
                      COUNT(*) AS tick_count
               FROM (
                 SELECT index_code,
                        date_trunc('minute', ts) AS minute_ts,
                        pct_chg, ts
                 FROM jyhf_index_quote_snapshot
                 WHERE trade_date = $1::date
                   AND ts >= $1::date + time '09:15'
               ) sub
               GROUP BY index_code, minute_ts""",
            trade_date,
        )
        written = 0
        async with pool.acquire() as conn:
            for r in rows:
                try:
                    await conn.execute(
                        """INSERT INTO intraday_index_minute_state
                           (trade_date, index_code, minute_ts, pct_chg)
                           VALUES ($1::date, $2, $3::timestamptz, $4)
                           ON CONFLICT (trade_date, index_code, minute_ts) DO UPDATE SET
                             pct_chg = EXCLUDED.pct_chg""",
                        trade_date, r["index_code"], r["minute_ts"], r["close_pct"],
                    )
                    written += 1
                except Exception:
                    pass
        return written

    while True:
        try:
            now = dt.now(TZ_CN)
            trade_date = now.date()

            if now.weekday() >= 5:
                logger.debug("Weekend, sleeping 60s")
                await asyncio.sleep(60)
                continue

            # 只在交易时段运行
            hhmm = now.hour * 100 + now.minute
            if hhmm < 915 or hhmm > 1505:
                idle_s = 60 if hhmm < 900 else 120
                logger.debug("Outside trading hours (%s), sleeping %ds", now.strftime("%H:%M"), idle_s)
                await asyncio.sleep(idle_s)
                continue

            t0 = _time.time()
            stock_ids = await get_watch_stock_ids(pool, trade_date)
            if not stock_ids:
                logger.warning("No watch stocks for %s", trade_date)
                await asyncio.sleep(interval)
                continue

            # 指数分钟数据
            idx_written = await collect_index_bars(trade_date)

            bars, last_minute = await build_minute_bars(pool, stock_ids, trade_date, last_minute)
            if bars:
                written = await upsert_minute_bars(pool, bars)
                elapsed_ms = int((_time.time() - t0) * 1000)
                logger.info(
                    "Minute bars: stocks=%d bars=%d written=%d index=%d elapsed=%dms",
                    len(stock_ids), len(bars), written, idx_written, elapsed_ms,
                )
            else:
                logger.debug("No bars to write (stocks=%d)", len(stock_ids))

        except Exception as exc:
            logger.exception("Minute collector error: %s", exc)

        await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main_loop())

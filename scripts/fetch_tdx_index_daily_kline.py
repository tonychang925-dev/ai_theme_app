"""PR-11: Fetch TDX index daily K-line and store to DB.

Usage: python scripts/fetch_tdx_index_daily_kline.py \
         [--index-codes 000001,399001,399006,000300,000905,000852,000688] \
         [--db-dsn postgresql://localhost/stock_data_test]

Updates existing rows (ON CONFLICT), so safe to run daily as cron.
"""
import argparse, asyncio, logging, sys
from datetime import date

import asyncpg
import akshare as ak

logger = logging.getLogger(__name__)

INDEX_CONFIG = {
    "000001": {"name": "上证指数", "market": "1"},
    "399001": {"name": "深证成指", "market": "0"},
    "399006": {"name": "创业板指", "market": "0"},
    "000300": {"name": "沪深300", "market": "1"},
    "000905": {"name": "中证500", "market": "1"},
    "000852": {"name": "中证1000", "market": "1"},
    "000688": {"name": "科创50", "market": "1"},
}


async def fetch_and_store(dsn: str, index_codes: list[str]) -> dict:
    conn = await asyncpg.connect(dsn)
    results = {}
    for code in index_codes:
        cfg = INDEX_CONFIG.get(code, {"name": code, "market": "1"})
        try:
            df = await asyncio.to_thread(ak.stock_zh_index_daily, symbol=f"sh{code}" if cfg["market"] == "1" else f"sz{code}")
            if df is None or df.empty:
                results[code] = "empty"
                continue
            rows = 0
            for _, row in df.iterrows():
                await conn.execute(
                    """INSERT INTO index_daily_kline (index_code, market, trade_date, open, high, low, close, volume, amount)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
                       ON CONFLICT (index_code, market, trade_date) DO UPDATE SET
                         open=$4, high=$5, low=$6, close=$7, volume=$8, amount=$9, updated_at=now()""",
                    code, cfg["market"], row["date"], row["open"], row["high"],
                    row["low"], row["close"], row.get("volume", 0), 0,
                )
                rows += 1
            results[code] = f"ok:{rows}"
            logger.info("%s %s: %d rows", code, cfg["name"], rows)
        except Exception as exc:
            results[code] = f"error:{exc}"
            logger.error("%s failed: %s", code, exc)
    await conn.close()
    return results


def main():
    p = argparse.ArgumentParser(description="TDX index K-line fetcher")
    p.add_argument("--index-codes", default="000001,399001,399006,000300,000905,000852,000688")
    p.add_argument("--db-dsn", default="postgresql://localhost/stock_data_test")
    args = p.parse_args()
    codes = [c.strip() for c in args.index_codes.split(",")]

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    results = asyncio.run(fetch_and_store(args.db_dsn, codes))
    for code, status in results.items():
        print(f"  {code}: {status}")


if __name__ == "__main__":
    main()

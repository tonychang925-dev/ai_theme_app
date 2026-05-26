"""P1-F-2: 强势股日K线批量采集 Job.

从 strong_stock_watch_pool 读取 active 股票列表，
批量调用 JYHF one-stock-daily API → normalize → 写入 jyhf_stock_daily_bar.

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app python -m \
    stock_processing_service.application.jobs.build_jyhf_stock_daily_bar_job \
    --trade-date 2026-05-26 --days 120 --limit 5
"""
from __future__ import annotations

import asyncio
import json
import logging
import time as _time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import asyncpg

from stock_processing_service.integrations.jyhf_market.api_client import JyhfMarketApiClient
from stock_processing_service.integrations.jyhf_market.normalizers import normalize_stock_daily_bars
from stock_processing_service.sinks.jyhf_market_db_sink import JyhfMarketDbSink

logger = logging.getLogger("sps.jobs.jyhf_stock_daily_bar")
TZ_CN = timezone(timedelta(hours=8))

DEFAULT_DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"
TOKEN_PATH = "/tmp/jyhf_auth_token.json"
API_BASE = "https://app.txcfgl.com"


@dataclass
class DailyBarJobResult:
    total_stocks: int = 0
    success_count: int = 0
    fail_count: int = 0
    written_rows: int = 0
    latest_trade_date: str = ""
    failed_samples: list[dict[str, str]] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class BuildJyhfStockDailyBarJob:
    """强势股日K线批量采集。"""

    def __init__(self, dsn: str = DEFAULT_DSN):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── strong_watch 股票列表 ──

    async def load_stock_list(self, limit: int = 0) -> list[dict[str, str]]:
        """从 strong_stock_watch_pool 读取 active 股票列表。"""
        pool = await self._get_pool()
        query = """SELECT DISTINCT ON (stock_id) stock_id, stock_name
                   FROM strong_stock_watch_pool
                   WHERE watch_status != 'removed'
                   ORDER BY stock_id, watch_score DESC"""
        if limit > 0:
            rows = await pool.fetch(query + " LIMIT $1", limit)
        else:
            rows = await pool.fetch(query)
        return [
            {"stock_id": r["stock_id"], "stock_name": r["stock_name"] or ""}
            for r in rows
        ]

    # ── 单股采集 ──

    async def _collect_one(
        self, api: JyhfMarketApiClient, sink: JyhfMarketDbSink,
        stock_id: str, stock_name: str, days: int, captured_at: str,
    ) -> int:
        """采集单只股票的日K线，返回写入行数。"""
        api_sid = _to_api_stock_id(stock_id)
        raw = await api.get_stock_daily(api_sid, days=days)
        bars = normalize_stock_daily_bars(raw, stock_id=stock_id, api_stock_id=api_sid, days=days)

        # 标记 today bar 为 partial（盘中采集时当前交易日K线尚未收盘）
        today_str = str(date.today())
        for b in bars:
            if b.trade_date == today_str:
                b.raw_json = {
                    **b.raw_json,
                    "bar_status": "partial",
                    "captured_at": captured_at,
                    "capture_session": "intraday",
                }

        return await sink.write_stock_daily_bars(bars)

    # ── 主流程 ──

    async def execute(
        self, trade_date: str, days: int = 120, limit: int = 0,
    ) -> DailyBarJobResult:
        result = DailyBarJobResult()
        t0 = _time.time()
        captured_at = datetime.now(TZ_CN).isoformat()

        # 加载 token（跳过网络校验）
        token = _load_token_direct()
        api = JyhfMarketApiClient(_StaticToken(token), API_BASE, timeout=15.0, max_retries=1)
        sink = JyhfMarketDbSink(self._dsn)

        stocks = await self.load_stock_list(limit=limit)
        result.total_stocks = len(stocks)
        logger.info("Loaded %d stocks from strong_stock_watch_pool (limit=%d)", len(stocks), limit)

        sem = asyncio.Semaphore(5)  # 并发上限 5

        async def _collect(stock: dict) -> int:
            sid = stock["stock_id"]
            sname = stock["stock_name"]
            async with sem:
                try:
                    n = await self._collect_one(api, sink, sid, sname, days, captured_at)
                    if n > 0:
                        logger.info("  ✅ %s %s: %d bars written", sid, sname, n)
                    else:
                        logger.warning("  ⚠ %s %s: 0 bars written", sid, sname)
                    return n
                except Exception as exc:
                    logger.warning("  ❌ %s %s: %s", sid, sname, exc)
                    result.failed_samples.append({"stock_id": sid, "stock_name": sname, "error": str(exc)[:200]})
                    return 0

        tasks = [_collect(s) for s in stocks]
        counts = await asyncio.gather(*tasks)

        for n in counts:
            if n > 0:
                result.success_count += 1
                result.written_rows += n
            else:
                # 检查是否在 failed_samples 中（有 exception）
                pass
        result.fail_count = result.total_stocks - result.success_count

        # 查询最新 trade_date
        pool = await self._get_pool()
        latest = await pool.fetchval(
            "SELECT MAX(trade_date) FROM jyhf_stock_daily_bar"
        )
        result.latest_trade_date = str(latest) if latest else ""

        await sink.close()
        result.elapsed_seconds = round(_time.time() - t0, 1)

        logger.info(
            "Done: %d stocks, %d success, %d fail, %d rows, latest=%s, elapsed=%.1fs",
            result.total_stocks, result.success_count, result.fail_count,
            result.written_rows, result.latest_trade_date, result.elapsed_seconds,
        )
        return result


# ── helpers ──


def _to_api_stock_id(stock_id: str) -> str:
    """002795.SZ → 002795."""
    return stock_id.replace(".SZ", "").replace(".SH", "").replace(".BJ", "").replace(".sz", "").replace(".sh", "")


def _load_token_direct() -> str:
    """直接从 CDP token 文件加载，跳过网络校验。"""
    data = json.loads(Path(TOKEN_PATH).read_text())
    return data["token"]


class _StaticToken:
    """Minimal token provider — no validation, no refresh."""
    def __init__(self, token: str):
        self._token = token
    def get_token(self) -> str:
        return self._token
    def is_token_valid(self) -> bool:
        return True
    def force_refresh(self) -> bool:
        return True


# ── CLI ──


async def _main():
    import argparse
    p = argparse.ArgumentParser(description="JYHF Stock Daily Bar Collector")
    p.add_argument("--trade-date", default=str(date.today()), help="YYYY-MM-DD (for record only)")
    p.add_argument("--days", type=int, default=120, help="日K历史天数")
    p.add_argument("--limit", type=int, default=0, help="限制采集股票数，0=全部")
    p.add_argument("--dsn", default=DEFAULT_DSN)
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    job = BuildJyhfStockDailyBarJob(dsn=args.dsn)
    result = await job.execute(trade_date=args.trade_date, days=args.days, limit=args.limit)

    print(json.dumps({
        "total_stocks": result.total_stocks,
        "success_count": result.success_count,
        "fail_count": result.fail_count,
        "written_rows": result.written_rows,
        "latest_trade_date": result.latest_trade_date,
        "elapsed_seconds": result.elapsed_seconds,
        "failed_samples": result.failed_samples[:10],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())

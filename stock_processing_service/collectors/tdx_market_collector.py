"""TDX 行情异步采集器."""
from __future__ import annotations

import asyncio
import logging
import time as time_mod
from datetime import date, datetime, timezone, timedelta

from stock_processing_service.integrations.tdx_market.config import TdxMarketConfig, load_config
from stock_processing_service.integrations.tdx_market.agent_client import TdxMarketAgentClient
from stock_processing_service.integrations.tdx_market.normalizers import (
    normalize_quote, normalize_minute, normalize_bars,
)
from stock_processing_service.universe.tdx_market_universe import TdxMarketUniverse

logger = logging.getLogger("sps.tdx_market.collector")
TZ_CN = timezone(timedelta(hours=8))


class TdxMarketCollector:
    """TDX 行情采集器 — quote → minute → bars."""

    def __init__(self, config: TdxMarketConfig | None = None, db_sink=None, redis_pusher=None):
        self.config = config or load_config()
        self.db = db_sink
        self.redis = redis_pusher

        self._api = TdxMarketAgentClient(
            self.config.agent_base_url, self.config.agent_timeout_seconds,
        )
        self._universe = TdxMarketUniverse(self.config.watchlist_path)

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._run_id: int = 0
        self._lock = asyncio.Lock()
        self._bars_collected_today: set[str] = set()

        self.stats = {
            "enabled": self.config.enabled,
            "running": False,
            "started_at": None,
            "last_collect_at": None,
            "collections": 0,
            "last_cycle_duration_ms": 0,
            "quotes": 0,
            "last_quote_success_count": 0,
            "last_quote_fail_count": 0,
            "minutes": 0,
            "bars": 0,
            "agent_base_url": self.config.agent_base_url,
            "agent_connected": False,
            "watch_stock_count": 0,
            "last_error": None,
        }

    # ── public ──

    def status(self) -> dict:
        return dict(self.stats)

    async def start(self) -> None:
        async with self._lock:
            if self.stats["running"]:
                return
            self._run_id += 1
            self._stop.clear()
            self.stats["running"] = True
            self.stats["started_at"] = datetime.now(TZ_CN).isoformat()
            self._universe.load()
            self.stats["watch_stock_count"] = len(self._universe.get_stocks())
            self.stats["agent_connected"] = await self._api.check_connection()
            await self._init_bars_dedup()
            self._task = asyncio.create_task(self._loop(self._run_id))
            logger.info("TDX collector started (run_id=%s) agent=%s stocks=%d",
                        self._run_id, self.stats["agent_connected"], self.stats["watch_stock_count"])

    async def stop(self) -> None:
        async with self._lock:
            self._run_id += 1
            self._stop.set()
            if self._task:
                try:
                    await asyncio.wait_for(self._task, timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                self._task = None
            self.stats["running"] = False
            logger.info("TDX collector stopped")

    # ── bars 去重：启动时查 DB ──

    async def _init_bars_dedup(self) -> None:
        """启动时从 DB 加载今天已采集过日线的 stock_id."""
        if self.db is None:
            return
        try:
            today_str = str(date.today())
            pool = await self.db._get_pool() if hasattr(self.db, '_get_pool') else None
            if pool is None:
                return
            rows = await pool.fetch(
                "SELECT DISTINCT stock_id FROM tdx_stock_daily_bar WHERE bar_time >= $1::timestamptz",
                today_str,
            )
            for row in rows:
                self._bars_collected_today.add(row["stock_id"])
            if self._bars_collected_today:
                logger.info("bars dedup: %d stocks already collected today", len(self._bars_collected_today))
        except Exception as exc:
            logger.debug("bars dedup init skipped: %s", exc)

    # ── loop ──

    async def _loop(self, run_id: int) -> None:
        while not self._stop.is_set() and self._run_id == run_id:
            cycle_start = time_mod.monotonic()
            try:
                await self._collect_once()
                self.stats["collections"] += 1
                self.stats["last_collect_at"] = datetime.now(TZ_CN).isoformat()
                self.stats["last_error"] = None
            except Exception as exc:
                logger.exception("TDX collection error: %s", exc)
                self.stats["last_error"] = str(exc)[:200]
                self.stats["agent_connected"] = await self._api.check_connection()
            self.stats["last_cycle_duration_ms"] = int((time_mod.monotonic() - cycle_start) * 1000)

            await self._sleep(self.config.interval_quote_seconds)

    async def _collect_once(self) -> None:
        stocks = self._universe.get_stocks()
        if not stocks:
            return

        api_stock_ids = self._universe.get_api_stock_ids()
        stock_map = dict(zip(stocks, api_stock_ids))  # system → api

        quote_ok = 0
        quote_fail = 0

        for system_id in stocks:
            if self._stop.is_set():
                return

            api_id = stock_map[system_id]

            # 1. quote
            try:
                raw = await self._api.get_quote(api_id)
                quote = normalize_quote(raw)
                if quote:
                    if self.db:
                        await self.db.write_stock_quote(quote)
                    if self.redis:
                        await self.redis.push_quote(quote)
                    self.stats["quotes"] += 1
                    quote_ok += 1
            except Exception as exc:
                logger.warning("TDX quote(%s): %s", system_id, exc)
                quote_fail += 1

            # 2. minute
            try:
                raw = await self._api.get_minute(api_id)
                bars = normalize_minute(raw)
                if self.db:
                    await self.db.write_minute_bars(bars)
                if self.redis and bars:
                    await self.redis.push_minute_bars(bars)
                self.stats["minutes"] += len(bars)
            except Exception as exc:
                logger.warning("TDX minute(%s): %s", system_id, exc)

            # 3. bars — DB-based 去重，避免重复请求
            if system_id not in self._bars_collected_today:
                try:
                    raw = await self._api.get_bars(api_id)
                    daily_bars = normalize_bars(raw)
                    if self.db:
                        await self.db.write_daily_bars(daily_bars)
                    if self.redis and daily_bars:
                        await self.redis.push_daily_bars(daily_bars)
                    self.stats["bars"] += len(daily_bars)
                    self._bars_collected_today.add(system_id)
                except Exception as exc:
                    logger.warning("TDX bars(%s): %s", system_id, exc)

        self.stats["last_quote_success_count"] = quote_ok
        self.stats["last_quote_fail_count"] = quote_fail

    async def _sleep(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass

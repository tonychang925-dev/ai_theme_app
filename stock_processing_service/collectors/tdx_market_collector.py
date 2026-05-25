"""TDX 行情异步采集器."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta

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
            "running": False, "started_at": None, "last_collect_at": None,
            "collections": 0, "quotes": 0, "minutes": 0, "bars": 0,
            "agent_connected": False, "last_error": None,
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
            self.stats["agent_connected"] = await self._api.check_connection()
            self._task = asyncio.create_task(self._loop(self._run_id))
            logger.info("TDX collector started (run_id=%s), agent=%s",
                        self._run_id, self.stats["agent_connected"])

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

    # ── loop ──

    async def _loop(self, run_id: int) -> None:
        while not self._stop.is_set() and self._run_id == run_id:
            try:
                await self._collect_once()
                self.stats["collections"] += 1
                self.stats["last_collect_at"] = datetime.now(TZ_CN).isoformat()
                self.stats["last_error"] = None
            except Exception as exc:
                logger.exception("TDX collection error: %s", exc)
                self.stats["last_error"] = str(exc)[:200]
                # 连接断开后尝试重连
                self.stats["agent_connected"] = await self._api.check_connection()

            await self._sleep(self.config.interval_quote_seconds)

    async def _collect_once(self) -> None:
        stocks = self._universe.get_stocks()
        if not stocks:
            return

        for stock_id in stocks:
            if self._stop.is_set():
                return

            # 1. quote
            try:
                raw = await self._api.get_quote(stock_id)
                quote = normalize_quote(raw)
                if quote:
                    if self.db:
                        await self.db.write_stock_quote(quote)
                    if self.redis:
                        await self.redis.push_quote(quote)
                    self.stats["quotes"] += 1
            except Exception as exc:
                logger.warning("TDX quote(%s): %s", stock_id, exc)

            # 2. minute
            try:
                raw = await self._api.get_minute(stock_id)
                bars = normalize_minute(raw)
                if self.db:
                    await self.db.write_minute_bars(stock_id, bars)
                if self.redis and bars:
                    await self.redis.push_minute_bars(bars)
                self.stats["minutes"] += len(bars)
            except Exception as exc:
                logger.warning("TDX minute(%s): %s", stock_id, exc)

            # 3. bars — 每天只采集一次（日线不会变）
            if stock_id not in self._bars_collected_today:
                try:
                    raw = await self._api.get_bars(stock_id)
                    daily_bars = normalize_bars(raw)
                    if self.db:
                        await self.db.write_daily_bars(stock_id, daily_bars)
                    if self.redis and daily_bars:
                        await self.redis.push_daily_bars(daily_bars)
                    self.stats["bars"] += len(daily_bars)
                    self._bars_collected_today.add(stock_id)
                except Exception as exc:
                    logger.warning("TDX bars(%s): %s", stock_id, exc)

    async def _sleep(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass

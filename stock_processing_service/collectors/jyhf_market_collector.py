"""P1-A 行情采集器 — 采集循环与调度."""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta

from stock_processing_service.integrations.jyhf_market.config import JyhfMarketConfig, load_config
from stock_processing_service.integrations.jyhf_market.token_provider import JyhfTokenProvider
from stock_processing_service.integrations.jyhf_market.api_client import JyhfMarketApiClient
from stock_processing_service.integrations.jyhf_market.normalizers import (
    normalize_stock_quote, normalize_index_quotes, normalize_subject_stock_quotes,
)
from stock_processing_service.universe.jyhf_market_universe import JyhfMarketUniverse

logger = logging.getLogger("sps.jyhf_market.collector")
TZ_CN = timezone(timedelta(hours=8))


class JyhfMarketCollector:
    """行情采集器 — 指数 → 题材股票池 → 个股。"""

    def __init__(self, config: JyhfMarketConfig | None = None, db_sink=None, redis_pusher=None):
        self.config = config or load_config()
        self.db = db_sink
        self.redis = redis_pusher

        self._token = JyhfTokenProvider(
            self.config.token_path, self.config.token_validation_endpoint,
            self.config.api_base_url, self.config.api_timeout_seconds,
        )
        self._api = JyhfMarketApiClient(
            self._token, self.config.api_base_url,
            self.config.api_timeout_seconds, self.config.api_max_retries,
        )
        self._universe = JyhfMarketUniverse(self.config.watchlist_path)

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._run_id: int = 0
        self._lock = asyncio.Lock()

        self.stats = {
            "running": False, "started_at": None, "last_collect_at": None,
            "collections": 0, "quotes": 0, "indexes": 0, "subject_stocks": 0,
            "db_writes": 0, "redis_pushes": 0, "last_error": None,
            "token_valid": False,
        }

    # ── public ──

    def status(self) -> dict:
        s = dict(self.stats)
        s["token_valid"] = self._token.is_token_valid()
        return s

    async def start(self) -> None:
        async with self._lock:
            if self.stats["running"]:
                return
            self._run_id += 1
            self._stop.clear()
            self.stats["running"] = True
            self.stats["started_at"] = datetime.now(TZ_CN).isoformat()
            self._universe.load()
            self._task = asyncio.create_task(self._loop(self._run_id))
            logger.info("Market collector started (run_id=%s)", self._run_id)

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
            logger.info("Market collector stopped")

    # ── loop ──

    async def _loop(self, run_id: int) -> None:
        while not self._stop.is_set() and self._run_id == run_id:
            try:
                await self._collect_once()
                self.stats["collections"] += 1
                self.stats["last_collect_at"] = datetime.now(TZ_CN).isoformat()
                self.stats["last_error"] = None
            except Exception as exc:
                logger.exception("Collection error: %s", exc)
                self.stats["last_error"] = str(exc)[:200]

            await self._sleep(self.config.interval_quote_seconds)

    async def _collect_once(self) -> None:
        # 1. 指数
        try:
            raw = await self._api.get_index_realtime()
            if self.db:
                await self.db.write_raw_capture("realtime/index", "/api/app/realtime/index", raw)
            for q in normalize_index_quotes(raw):
                if self.db:
                    await self.db.write_index_quote(q)
                if self.redis:
                    await self.redis.push_index(q)
                self.stats["indexes"] += 1
        except Exception as exc:
            logger.warning("Index: %s", exc)

        # 2. 题材股票池
        for sid in self._universe.get_subjects():
            try:
                raw = await self._api.get_subject_stocks_realtime(sid, start=0, end=50)
                if self.db:
                    await self.db.write_raw_capture("realtime-by-subject", f"/api/app/stock/realtime-by-subject/v2?subjectId={sid}", raw)
                for q in normalize_subject_stock_quotes(raw, sid):
                    if self.db:
                        await self.db.write_subject_stock_quote(q)
                    if self.redis:
                        await self.redis.push_subject_stock(q)
                    self.stats["subject_stocks"] += 1
            except Exception as exc:
                logger.warning("Subject %s: %s", sid, exc)

        # 3. 个股
        for sid in self._universe.get_stocks():
            try:
                raw = await self._api.get_stock_realtime(sid)
                if self.db:
                    await self.db.write_raw_capture("stock/realtime", f"/api/app/stock/realtime/{sid}", raw)
                quote = normalize_stock_quote(raw, sid)
                if quote:
                    if self.db:
                        await self.db.write_stock_quote(quote)
                    if self.redis:
                        await self.redis.push_quote(quote)
                    self.stats["quotes"] += 1
            except Exception as exc:
                logger.warning("Stock %s: %s", sid, exc)

        if self.db:
            self.stats["db_writes"] = self.db.write_count
        if self.redis:
            self.stats["redis_pushes"] = self.redis.pushed_count

    async def _sleep(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass

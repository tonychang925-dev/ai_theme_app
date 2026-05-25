"""P1-D 双源校验采集器 — 定期执行双源行情比对."""
from __future__ import annotations

import asyncio
import logging
import time as time_mod
from datetime import datetime, timezone, timedelta

from stock_processing_service.market_quality.quote_crosscheck import QuoteCrosscheckService
from stock_processing_service.market_quality.crosscheck_repository import CrosscheckRepository
from stock_processing_service.market_quality.crosscheck_publisher import CrosscheckPublisher
from stock_processing_service.market_quality.crosscheck_rules import _MAX_STALE_SECONDS

logger = logging.getLogger("sps.crosscheck.collector")
TZ_CN = timezone(timedelta(hours=8))


class MarketCrosscheckCollector:
    """双源行情校验采集器."""

    def __init__(
        self,
        pg_dsn: str,
        redis_url: str,
        interval_seconds: float = 10.0,
        max_age_seconds: float = 30.0,
        redis_stream: str = "stream:market:crosscheck",
    ):
        self._interval = interval_seconds
        self._max_age = max_age_seconds
        self._repo = CrosscheckRepository(pg_dsn)
        self._pub = CrosscheckPublisher(redis_url, redis_stream)
        self._service = QuoteCrosscheckService(self._repo, self._pub)

        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._run_id: int = 0
        self._lock = asyncio.Lock()

    # ── public ──

    def status(self) -> dict:
        return self._service.status()

    async def start(self) -> None:
        async with self._lock:
            if self._task is not None and not self._task.done():
                return
            self._run_id += 1
            self._stop.clear()
            self._task = asyncio.create_task(self._loop(self._run_id))
            logger.info("crosscheck collector started (run_id=%s)", self._run_id)

    async def stop(self) -> None:
        async with self._lock:
            self._stop.set()
            if self._task:
                try:
                    await asyncio.wait_for(self._task, timeout=3.0)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    pass
                self._task = None
            await self._repo.close()
            await self._pub.close()
            logger.info("crosscheck collector stopped")

    async def get_db_summary(self) -> dict:
        return await self._service.get_db_summary(120.0)

    # ── loop ──

    async def _loop(self, run_id: int) -> None:
        while not self._stop.is_set() and self._run_id == run_id:
            cycle_start = time_mod.monotonic()
            try:
                summary = await self._service.run_once(max_age_seconds=self._max_age)
                elapsed_ms = int((time_mod.monotonic() - cycle_start) * 1000)
                logger.info(
                    "crosscheck: %d stocks, OK=%d WARN=%d CRIT=%d MISS=%d STALE=%d (%dms)",
                    summary["total"], summary["ok"], summary["warn"],
                    summary["critical"], summary["missing_source"],
                    summary["stale_source"], elapsed_ms,
                )
            except Exception as exc:
                logger.exception("crosscheck error: %s", exc)
                self._service.stats["last_error"] = str(exc)[:200]

            await self._sleep(self._interval)

    async def _sleep(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass

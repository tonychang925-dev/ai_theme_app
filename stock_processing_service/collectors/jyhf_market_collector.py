"""P1-B+ 行情采集器 — 拆方法 + 多来源候选池."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time as _time
from datetime import datetime, timezone, timedelta

import httpx

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
    """行情采集器 — 指数 / 题材股票池 / 个股 独立调度。"""

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

        # 独立采集时间戳
        self._last_index_at: float = 0
        self._last_subject_at: float = 0
        self._last_quote_at: float = 0

        # 每轮耗时
        self._last_cycle_start: float = 0
        self._last_cycle_duration_ms: int = 0

        self.stats = {
            "running": False, "started_at": None, "last_collect_at": None,
            "collections": 0, "quotes": 0, "indexes": 0, "subject_stocks": 0,
            "db_writes": 0, "redis_pushes": 0, "last_error": None,
            "token_valid": False,
            "watch_stock_count": 0, "watch_subject_count": 0,
            "source_breakdown": {},
            "last_cycle_duration_ms": 0,
            "last_quote_success": 0, "last_quote_fail": 0,
            "last_subject_success": 0, "last_index_success": 0,
            "current_session": "normal",
            "last_snapshot_at": None,
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
            await self._refresh_universe()
            self._last_index_at = 0
            self._last_subject_at = 0
            self._last_quote_at = 0
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

    # ── loop ──

    async def _loop(self, run_id: int) -> None:
        cycle_count = 0
        while not self._stop.is_set() and self._run_id == run_id:
            self._last_cycle_start = _time.time()
            try:
                if cycle_count % 30 == 0:
                    await self._refresh_universe()

                # P1-C: 根据时段选择采集频率
                now_ts = _time.time()
                quote_int, idx_int, subj_int = self._session_intervals()
                self.stats["current_session"] = self._current_session_label()

                if now_ts - self._last_index_at >= idx_int:
                    await self._collect_index()
                    self._last_index_at = now_ts

                if now_ts - self._last_subject_at >= subj_int:
                    await self._collect_subject_stocks()
                    self._last_subject_at = now_ts

                if now_ts - self._last_quote_at >= quote_int:
                    await self._collect_stock_quotes()
                    self._last_quote_at = now_ts

                # 尾盘快照
                await self._maybe_tail_snapshot()

                self.stats["collections"] += 1
                self.stats["last_cycle_duration_ms"] = int((_time.time() - self._last_cycle_start) * 1000)
                self.stats["last_collect_at"] = datetime.now(TZ_CN).isoformat()
                self.stats["last_error"] = None

            except Exception as exc:
                logger.exception("Collection error: %s", exc)
                self.stats["last_error"] = str(exc)[:200]

            cycle_count += 1
            await self._sleep(self.config.loop_tick_seconds)

    # ── 独立采集方法 ──

    async def _collect_index(self) -> None:
        ok = 0
        try:
            raw = await self._api.get_index_realtime()
            if self.db and self.config.raw_capture_enabled:
                await self.db.write_raw_capture("realtime/index", "/api/app/realtime/index", raw)
            for q in normalize_index_quotes(raw):
                if self.db:
                    await self.db.write_index_quote(q)
                if self.redis:
                    await self.redis.push_index(q)
                self.stats["indexes"] += 1
                ok += 1
        except Exception as exc:
            logger.warning("Index: %s", exc)
        self.stats["last_index_success"] = ok

    async def _collect_subject_stocks(self) -> None:
        ok = 0
        for sid in self._universe.get_subjects():
            try:
                raw = await self._api.get_subject_stocks_realtime(sid, start=0, end=50)
                if self.db and self.config.raw_capture_enabled:
                    await self.db.write_raw_capture("realtime-by-subject",
                        f"/api/app/stock/realtime-by-subject/v2?subjectId={sid}", raw)
                for q in normalize_subject_stock_quotes(raw, sid):
                    if self.db:
                        await self.db.write_subject_stock_quote(q)
                    if self.redis:
                        await self.redis.push_subject_stock(q)
                    self.stats["subject_stocks"] += 1
                    ok += 1
            except Exception as exc:
                logger.warning("Subject %s: %s", sid, exc)
        self.stats["last_subject_success"] = ok

    async def _collect_stock_quotes(self) -> None:
        ok = 0
        fail = 0
        for item in self._universe.get_stock_items():
            try:
                raw = await self._api.get_stock_realtime(item["api_stock_id"])
                if self.db and self.config.raw_capture_enabled:
                    await self.db.write_raw_capture("stock/realtime",
                        f"/api/app/stock/realtime/{item['api_stock_id']}", raw)
                quote = normalize_stock_quote(raw, stock_id=item["stock_id"], api_stock_id=item["api_stock_id"])
                if quote:
                    if self.db:
                        await self.db.write_stock_quote(quote)
                    if self.redis:
                        await self.redis.push_quote(quote)
                    self.stats["quotes"] += 1
                    ok += 1
                else:
                    fail += 1
            except Exception as exc:
                logger.warning("Stock %s: %s", item["api_stock_id"], exc)
                fail += 1
        self.stats["last_quote_success"] = ok
        self.stats["last_quote_fail"] = fail
        if self.db:
            self.stats["db_writes"] = self.db.write_count
        if self.redis:
            self.stats["redis_pushes"] = self.redis.pushed_count

    # ── 候选池刷新 ──

    async def _refresh_universe(self) -> None:
        self._universe.load_manual()
        sw = await self._fetch_strong_watch()
        universe = self._universe.merge(strong_watch_stocks=sw)
        self.stats["watch_stock_count"] = len(universe["watch_stocks"])
        self.stats["watch_subject_count"] = len(universe["watch_subjects"])
        self.stats["source_breakdown"] = universe["source_breakdown"]
        logger.info("Universe: %d stocks (breakdown=%s)",
                     self.stats["watch_stock_count"], self.stats["source_breakdown"])

    async def _fetch_strong_watch(self) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                r = await client.get(
                    f"{self.config.sps_base_url}/api/v1/strong_watch",
                    params={"trade_date": str(datetime.now(TZ_CN).date()), "window_days": 7, "limit": 2000},
                )
                r.raise_for_status()
                data = r.json()
                stocks = data.get("stocks", [])
                logger.info("Strong_watch: %d stocks", len(stocks))
                return [{
                    "stock_id": s.get("stock_id", ""),
                    "stock_name": s.get("stock_name", ""),
                    "subject_id": s.get("subject_key") or s.get("subject_id"),
                    "theme_name": s.get("theme_name"),
                } for s in stocks]
        except Exception as exc:
            logger.warning("Strong_watch fetch failed: %s", exc)
            return []

    # ── P1-C: 时段感知调度 ──

    def _session_intervals(self) -> tuple[float, float, float]:
        """返回 (quote_interval, index_interval, subject_interval)。"""
        cfg = self.config
        now = datetime.now(TZ_CN)
        h, m = now.hour, now.minute

        # 竞价窗口
        if (h == cfg.auction_start_hour and m >= cfg.auction_start_minute) or \
           (h == cfg.auction_end_hour and m <= cfg.auction_end_minute):
            return (cfg.auction_quote_seconds, cfg.interval_index_seconds, cfg.interval_subject_seconds)

        # 尾盘窗口
        if (h == cfg.tail_start_hour and m >= cfg.tail_start_minute) or \
           (h == cfg.tail_end_hour and m <= cfg.tail_end_minute):
            return (cfg.tail_quote_seconds, cfg.tail_index_seconds, cfg.tail_subject_seconds)

        return (cfg.interval_quote_seconds, cfg.interval_index_seconds, cfg.interval_subject_seconds)

    def _current_session_label(self) -> str:
        now = datetime.now(TZ_CN)
        h, m = now.hour, now.minute
        cfg = self.config
        if (h == cfg.auction_start_hour and m >= cfg.auction_start_minute) or \
           (h == cfg.auction_end_hour and m <= cfg.auction_end_minute):
            return "auction"
        if (h == cfg.tail_start_hour and m >= cfg.tail_start_minute) or \
           (h == cfg.tail_end_hour and m <= cfg.tail_end_minute):
            return "tail"
        return "normal"

    async def _maybe_tail_snapshot(self) -> None:
        """尾盘快照：14:45, 14:55, 14:59 时间点输出 snapshot 标记。"""
        now = datetime.now(TZ_CN)
        if not (now.hour == self.config.tail_start_hour and now.minute >= self.config.tail_start_minute):
            return
        if now.hour > self.config.tail_end_hour:
            return

        current_time = f"{now.hour:02d}{now.minute:02d}"
        snapshot_times = [t.strip() for t in self.config.tail_snapshot_times.split(",") if t.strip()]
        if current_time not in snapshot_times:
            return

        # 防止同一分钟重复快照
        last_snap = self.stats.get("last_snapshot_at", "")
        if last_snap == current_time:
            return
        self.stats["last_snapshot_at"] = current_time

        # 推送 snapshot 标记到 Redis
        if self.redis:
            try:
                await self.redis._push({
                    "item_type": "tail_session_snapshot",
                    "source_channel": "jyhf_market_api",
                    "trade_date": str(now.date()),
                    "occurred_at": now.isoformat(),
                    "snapshot_time": current_time,
                    "watch_stock_count": str(self.stats.get("watch_stock_count", 0)),
                    "session": "tail",
                })
            except Exception:
                pass
        logger.info("Tail snapshot: %s (stocks=%d)", current_time, self.stats.get("watch_stock_count", 0))

    async def _sleep(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass

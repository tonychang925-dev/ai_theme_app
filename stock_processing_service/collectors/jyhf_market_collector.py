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

        # 尾盘快照去重 + 最近行情缓存
        self._emitted_snapshots: dict[str, set] = {}
        self._last_quote_cache: dict[str, dict] = {}

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
            "current_session": "closed",
            "quote_interval_seconds": 0.0,
            "index_interval_seconds": 0.0,
            "subject_interval_seconds": 0.0,
            "cycle_overrun": False,
            "last_snapshot_at": None,
            "emitted_tail_snapshots": [],
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

                # P1-C+: 时段感知 + 间隔可见
                now_ts = _time.time()
                session = self._current_session_label()
                quote_int, idx_int, subj_int = self._session_intervals()
                self.stats["current_session"] = session
                self.stats["quote_interval_seconds"] = quote_int
                self.stats["index_interval_seconds"] = idx_int
                self.stats["subject_interval_seconds"] = subj_int

                # 非交易时段跳过采集
                if session == "closed":
                    cycle_count += 1
                    await self._sleep(self.config.loop_tick_seconds * 60)
                    continue

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
                dur_ms = int((_time.time() - self._last_cycle_start) * 1000)
                self.stats["last_cycle_duration_ms"] = dur_ms
                self.stats["cycle_overrun"] = dur_ms > (quote_int * 1000)
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
        items = self._universe.get_stock_items()
        if not items:
            return

        sem = asyncio.Semaphore(self.config.max_quote_concurrency)

        async def _fetch_one(item: dict) -> tuple[dict | None, str]:
            async with sem:
                try:
                    raw = await self._api.get_stock_realtime(item["api_stock_id"])
                    quote = normalize_stock_quote(raw, stock_id=item["stock_id"], api_stock_id=item["api_stock_id"])
                    return (quote, item["api_stock_id"])
                except Exception as exc:
                    logger.warning("Stock %s: %s", item["api_stock_id"], exc)
                    return (None, item["api_stock_id"])

        results = await asyncio.gather(*[_fetch_one(it) for it in items])

        ok = 0
        fail = 0
        for quote, api_sid in results:
            if quote:
                if self.db:
                    await self.db.write_stock_quote(quote)
                if self.redis:
                    await self.redis.push_quote(quote)
                self.stats["quotes"] += 1
                self._last_quote_cache[quote.stock_id] = {
                    "pct_chg": quote.pct_chg,
                    "amount": quote.amount,
                    "current": quote.current,
                    "ts": quote.ts,
                }
                ok += 1
            else:
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

    # ── P1-C+: 时段感知 + 非交易时间保护 ──

    @staticmethod
    def _is_weekend(dt: datetime) -> bool:
        return dt.weekday() >= 5  # 周六=5, 周日=6

    def _is_lunch_break(self, h: int, m: int) -> bool:
        return h == 11 and m >= 30 or h == 12

    def _session_intervals(self) -> tuple[float, float, float]:
        """返回 (quote_interval, index_interval, subject_interval)。"""
        cfg = self.config
        now = datetime.now(TZ_CN)
        h, m = now.hour, now.minute

        # 竞价窗口
        if h == 9 and m >= cfg.auction_start_minute and not self._is_lunch_break(h, m):
            return (cfg.auction_quote_seconds, cfg.interval_index_seconds, cfg.interval_subject_seconds)

        # 尾盘窗口
        if h == cfg.tail_start_hour and m >= cfg.tail_start_minute and not self._is_lunch_break(h, m):
            return (cfg.tail_quote_seconds, cfg.tail_index_seconds, cfg.tail_subject_seconds)

        return (cfg.interval_quote_seconds, cfg.interval_index_seconds, cfg.interval_subject_seconds)

    def _current_session_label(self) -> str:
        now = datetime.now(TZ_CN)
        h, m = now.hour, now.minute

        if self._is_weekend(now):
            return "closed"
        if self._is_lunch_break(h, m):
            return "lunch_break"
        if h < 9 or (h == 9 and m < 15):
            return "pre_market"
        if h >= 15 and m >= 5:
            return "closed"
        if h == 9 and m >= 15 and m <= 25:
            return "auction"
        if h == 14 and m >= 30:
            return "tail"
        if 9 <= h <= 14:
            return "normal"
        return "closed"

    async def _maybe_tail_snapshot(self) -> None:
        """P1-C+: 尾盘快照，去重 + 增强内容 + DB入库。"""
        now = datetime.now(TZ_CN)
        td = str(now.date())

        if self._current_session_label() != "tail":
            return

        current_time = f"{now.hour:02d}{now.minute:02d}"
        snapshot_times = [t.strip() for t in self.config.tail_snapshot_times.split(",") if t.strip()]
        if current_time not in snapshot_times:
            return

        # 去重：同一交易日同一时间点只发一次
        if td not in self._emitted_snapshots:
            self._emitted_snapshots = {td: set()}
        if current_time in self._emitted_snapshots.get(td, set()):
            return
        self._emitted_snapshots.setdefault(td, set()).add(current_time)
        self.stats["last_snapshot_at"] = current_time
        self.stats["emitted_tail_snapshots"] = sorted(self._emitted_snapshots.get(td, set()))

        # 构建增强快照
        stock_items = self._universe.get_stock_items()
        cache = self._last_quote_cache

        def _get_pct(sid):
            q = cache.get(sid, {})
            return q.get("pct_chg") or 0
        def _get_amt(sid):
            q = cache.get(sid, {})
            return q.get("amount") or 0

        top_pct = sorted(stock_items, key=lambda x: -_get_pct(x["stock_id"]))[:5]
        top_amt = sorted(stock_items, key=lambda x: -_get_amt(x["stock_id"]))[:5]

        payload = {
            "item_type": "tail_session_snapshot",
            "source_channel": "jyhf_market_api",
            "trade_date": td,
            "snapshot_time": current_time,
            "occurred_at": now.isoformat(),
            "watch_stock_count": len(stock_items),
            "session": "tail",
            "top_pct_chg": [
                {"stock_id": s["stock_id"], "stock_name": s["stock_name"]} for s in top_pct
            ],
            "top_amount": [
                {"stock_id": s["stock_id"], "stock_name": s["stock_name"]} for s in top_amt
            ],
            "source_breakdown": self.stats.get("source_breakdown", {}),
        }

        # Redis
        if self.redis:
            try:
                payload["item_id"] = f"jyhf_tail_snapshot:{td}:{current_time}"
                await self.redis._push(payload)
            except Exception as exc:
                logger.warning("Tail snapshot Redis push failed: %s", exc)

        # PostgreSQL
        if self.db:
            try:
                import json as _json
                await self.db._get_pool()
                await self.db._pool.fetchval(
                    """INSERT INTO jyhf_tail_session_snapshot
                       (trade_date, snapshot_time, captured_at, watch_stock_count, payload)
                       VALUES ($1::date, $2, $3::timestamptz, $4, $5::jsonb)
                       ON CONFLICT (trade_date, snapshot_time) DO NOTHING""",
                    td, current_time, now.isoformat(), len(stock_items),
                    _json.dumps(payload, ensure_ascii=False),
                )
            except Exception as exc:
                logger.warning("Tail snapshot DB write failed: %s", exc)

        logger.info("Tail snapshot: %s (stocks=%d pct_top=%s amt_top=%s)",
                     current_time, len(stock_items),
                     [s["stock_id"] for s in top_pct],
                     [s["stock_id"] for s in top_amt])

    async def _sleep(self, sec: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=sec)
        except asyncio.TimeoutError:
            pass

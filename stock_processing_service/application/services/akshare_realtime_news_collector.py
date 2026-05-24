"""
Deprecated since Phase 4E (2026-05-24).

本采集器的能力已迁移至:
  - database_service.streams.services.news_prefilter_adapter.NewsPreFilterAdapter
  - database_service.streams.services.semantic_event_deduper.SemanticEventDeduper
  - database_service.streams.services.news_payload_normalizer.normalize_news_payload
  - database_service.streams.services.real_time_news_collector.RealTimeNewsCollector

本类仅保留用于回归对比（ENABLE_LEGACY_AKSHARE_COLLECTOR=true）。
Legacy 模式强制写入 stream:news:raw:legacy，绝不写正式 raw stream。
生产入口: RealTimeNewsCollector (database_service/streams/)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CN_TZ = timezone(timedelta(hours=8))
logger = logging.getLogger(__name__)


@dataclass
class AkShareCollectorStats:
    run_id: str
    stream: str
    running: bool = False
    started_at: str | None = None
    last_fetch_at: str | None = None
    last_success_at: str | None = None
    fetched_count: int = 0
    pushed_count: int = 0
    duplicate_count: int = 0
    filtered_count: int = 0
    filter_pass_count: int = 0
    cross_dedup_count: int = 0
    filter_error_count: int = 0
    filter_mode: str = "off"
    last_filter_reason: str | None = None
    error_count: int = 0
    last_error: str | None = None


class AkShareRealtimeNewsCollector:
    """Fetch real-time AkShare/news-crawler news and publish raw-news events."""

    def __init__(
        self,
        *,
        redis_url: str,
        stream: str,
        run_id: str,
        poll_interval_seconds: int = 60,
        lookback_minutes: int = 180,
        status_path: str | Path | None = None,
        batch_size: int = 20,
        prefilter_enabled: bool = True,
        prefilter_mode: str = "rule",
        prefilter_model_path: str = "",
        prefilter_fail_open: bool = True,
        prefilter_skip_log_path: str | Path | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.stream = stream
        self.run_id = run_id
        self.poll_interval_seconds = max(5, int(poll_interval_seconds))
        self.lookback_minutes = max(1, int(lookback_minutes))
        self.batch_size = max(1, int(batch_size))
        self.status_path = Path(status_path) if status_path else None
        self._prefilter_skip_log = Path(prefilter_skip_log_path) if prefilter_skip_log_path else None
        if self._prefilter_skip_log:
            self._prefilter_skip_log.parent.mkdir(parents=True, exist_ok=True)
        self.stats = AkShareCollectorStats(run_id=run_id, stream=stream)
        self._seen: set[str] = set()       # 已推送成功的 key（永久去重）
        self._filtered: set[str] = set()   # 被 prefilter 过滤的 key（定期清空，允许重评）
        self._filtered_cycles = 0
        self._redis = None
        # P1-A: 预过滤
        self._prefilter = _init_prefilter(
            enabled=prefilter_enabled,
            mode=prefilter_mode,
            model_path=prefilter_model_path,
            fail_open=prefilter_fail_open,
        )
        self.stats.filter_mode = prefilter_mode if prefilter_enabled else "off"

    async def run_forever(self) -> None:
        self.stats.running = True
        self.stats.started_at = _now_iso()
        self._write_status()
        try:
            while True:
                await self.collect_once()
                await asyncio.sleep(self.poll_interval_seconds)
        finally:
            self.stats.running = False
            self._write_status()
            if self._redis is not None:
                await self._redis.aclose()

    # ── Source priority for cross-source dedup ─────────────────────────
    _SOURCE_PRIORITY: dict[str, int] = {
        "cls": 100,
        "akshare_cls": 95,
        "akshare_em": 80,
        "akshare_futu": 70,
        "akshare_ths": 60,
        "akshare_sina": 50,
        "akshare_cctv": 40,
    }

    async def collect_once(self) -> dict[str, int]:
        self.stats.last_fetch_at = _now_iso()
        self._prefilter.new_batch()  # P1-A2.1: 重置批次 Qwen 预算
        try:
            rows = await self._fetch_news()
            # 跨源语义去重
            before_dedup = len(rows)
            rows = await self._cross_source_dedup(rows)
            cross_dedup = before_dedup - len(rows)
            self.stats.cross_dedup_count += cross_dedup
            self.stats.fetched_count += len(rows)
            pushed = 0
            duplicate = 0
            filtered = 0
            for row in rows:
                payload = self._normalize_payload(row)
                dedupe_key = self._dedupe_key(payload)

                # 已在成功集中 → 永久去重
                if dedupe_key in self._seen:
                    duplicate += 1
                    continue

                # P1-A: prefilter hook — SKIP 则不 publish
                triage = self._prefilter.evaluate(payload)
                if not triage.pass_:
                    filtered += 1
                    self.stats.last_filter_reason = triage.reason
                    # 加入 _filtered（非 _seen），允许 prefilter 变更后重评
                    self._filtered.add(dedupe_key)
                    self._write_skip_log(payload, triage)
                    continue

                self.stats.filter_pass_count += 1
                payload.update(self._prefilter.to_payload_fields(triage))
                self._seen.add(dedupe_key)
                await self._publish(payload)
                pushed += 1

            # 每 10 个周期清空 _filtered，避免无限增长且允许重评
            self._filtered_cycles += 1
            if self._filtered_cycles >= 10:
                self._filtered.clear()
                self._filtered_cycles = 0

            self.stats.pushed_count += pushed
            self.stats.duplicate_count += duplicate
            self.stats.filtered_count += filtered
            self.stats.last_success_at = _now_iso()
            self.stats.last_error = None
            self._write_status()
            return {"fetched": len(rows), "pushed": pushed, "duplicate": duplicate, "filtered": filtered}
        except Exception as exc:
            self.stats.error_count += 1
            self.stats.last_error = str(exc)
            self._write_status()
            logger.exception("akshare realtime collect_once failed")
            return {"fetched": 0, "pushed": 0, "duplicate": 0, "filtered": 0}

    async def _fetch_news(self) -> list[dict[str, Any]]:
        """Fetch from CLS (有重要性过滤) + 4 additional sources in parallel."""
        results: list[dict[str, Any]] = []

        # Source 1: CLS 财联社 (primary, with importance filter)
        try:
            from news_crawler_service.services.news_crawler_service import get_news_crawler_service
            service = get_news_crawler_service()
            result = await service.crawl_news_auto(count=self.batch_size, prefer_real=True)
            if result.get("status") == "success":
                cls_rows = list((result.get("response") or {}).get("news_list") or [])
                for r in cls_rows:
                    r["source_channel"] = "cls"
                results.extend(cls_rows)
        except Exception as exc:
            logger.warning("CLS fetch failed, continuing with other sources: %s", exc)

        # Sources 2-5: 东方财富 / 新浪 / 同花顺 / 富途 (parallel)
        other_rows = await self._fetch_multi_source()
        results.extend(other_rows)

        if not results:
            logger.warning("All sources failed, fallback to direct akshare")
            return await asyncio.to_thread(self._fetch_direct_akshare)

        return results

    async def _fetch_multi_source(self) -> list[dict[str, Any]]:
        """Fetch from 东方财富/新浪/同花顺/富途 in parallel via thread executor."""
        import akshare as ak

        sources: list[tuple[str, Any, str]] = [
            ("cls",       ak.stock_info_global_cls, "cls"),
            ("sina",      ak.stock_info_global_sina, "sina"),
            ("ths",       ak.stock_info_global_ths, "ths"),
            ("futu",      ak.stock_info_global_futu, "futu"),
            ("cctv",      ak.news_cctv, "cctv"),
        ]

        # Per-source row limits to balance coverage vs noise
        _SOURCE_LIMITS = {"cls": 30, "em": 50, "sina": 20, "ths": 20, "futu": 50, "cctv": 12}

        async def _fetch_one(label: str, func, channel: str) -> list[dict[str, Any]]:
            try:
                df = await asyncio.wait_for(asyncio.to_thread(func), timeout=45)
                if df is None or df.empty:
                    return []
                limit = _SOURCE_LIMITS.get(channel, 50)
                records = df.head(limit).to_dict("records")
                for r in records:
                    r["source_channel"] = f"akshare_{channel}"
                    # 新浪特殊处理: 只有"时间"和"内容"两列，无标题
                    if channel == "sina":
                        content_text = str(r.get("内容", ""))
                        r["title"] = content_text[:40]  # 前40字作为标题
                        r["publish_time"] = str(r.get("时间", ""))
                        r["publish_date"] = datetime.now(CN_TZ).date().isoformat()
                return [dict(row) for row in records]
            except Exception as exc:
                logger.warning("Source %s fetch failed: %s", label, exc)
                return []

        tasks = [asyncio.create_task(_fetch_one(label, func, ch)) for label, func, ch in sources]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        all_rows: list[dict[str, Any]] = []
        for i, rows in enumerate(gathered):
            if isinstance(rows, Exception):
                logger.warning("Source %s exception: %s", sources[i][0], rows)
            else:
                all_rows.extend(rows)
                if rows:
                    logger.info("Source %s: %d rows", sources[i][0], len(rows))
        return all_rows

    async def _cross_source_dedup(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """跨源语义去重：标题相似度 + Qwen 1.5B 判定。

        策略:
          1. 按 normalize(title[:30]) 分桶（快速粗筛）
          2. 桶内 pair 计算 SequenceMatcher 相似度
             - > 0.85 → 自动判为重复
             - 0.5-0.85 → 调用 Qwen 判定
             - < 0.5 → 保留两者
          3. 重复对中保留 source_channel 优先级高的
        """
        if len(rows) <= 1:
            return rows

        import difflib

        # 1. 按标题前缀分桶
        import re as _regex

        def _norm_title(s: str) -> str:
            return _regex.sub(r'[^\w]', '', str(s)[:30]).lower()

        buckets: dict[str, list[int]] = {}  # norm_key → list of indices
        for i, row in enumerate(rows):
            raw_title = (_pick(row, "title", "新闻标题", "标题")
                         or _pick(row, "content", "内容", "摘要")
                         or "")
            bucket_key = _norm_title(raw_title)
            buckets.setdefault(bucket_key, []).append(i)

        # 2. 找出需要去重的对
        dup_pairs: list[tuple[int, int]] = []  # (keeper_idx, dropped_idx)
        for indices in buckets.values():
            if len(indices) < 2:
                continue
            for a in range(len(indices)):
                for b in range(a + 1, len(indices)):
                    ia, ib = indices[a], indices[b]
                    title_a = str(_pick(rows[ia], "title", "新闻标题", "标题") or "")
                    title_b = str(_pick(rows[ib], "title", "新闻标题", "标题") or "")
                    if not title_a or not title_b:
                        continue

                    ratio = difflib.SequenceMatcher(None, title_a, title_b).ratio()

                    is_dup = False
                    if ratio > 0.85:
                        is_dup = True
                    elif ratio > 0.5:
                        # 灰区：交给 Qwen
                        result = self._prefilter.check_semantic_duplicate(title_a, title_b)
                        if result is True:
                            is_dup = True
                        elif result is None:
                            # Qwen 不可用，高相似度 (>0.75) 保守去重
                            is_dup = ratio > 0.75

                    if is_dup:
                        # 保留 source_channel 优先级高的
                        ch_a = str(_pick(rows[ia], "source_channel") or "")
                        ch_b = str(_pick(rows[ib], "source_channel") or "")
                        pri_a = self._SOURCE_PRIORITY.get(ch_a, 0)
                        pri_b = self._SOURCE_PRIORITY.get(ch_b, 0)
                        if pri_a >= pri_b:
                            dup_pairs.append((ia, ib))
                        else:
                            dup_pairs.append((ib, ia))

        if dup_pairs:
            dropped = {d for _, d in dup_pairs}
            logger.info(
                "cross-source dedup: %d pairs merged, dropping %d rows (%.0f%%)",
                len(dup_pairs), len(dropped),
                len(dropped) / max(len(rows), 1) * 100,
            )
            rows = [r for i, r in enumerate(rows) if i not in dropped]

        return rows

    def _fetch_direct_akshare(self) -> list[dict[str, Any]]:
        import akshare as ak

        df = ak.stock_news_em()
        if df is None:
            return []
        records = df.head(self.batch_size).to_dict("records")
        return [dict(row) for row in records]

    def _normalize_payload(self, row: dict[str, Any]) -> dict[str, str]:
        title = _pick(row, "title", "新闻标题", "标题") or ""
        content = _pick(row, "content", "新闻内容", "内容", "摘要") or title
        source = _pick(row, "source", "新闻来源", "来源") or "akshare"
        source_channel = _pick(row, "source_channel") or "akshare_realtime"
        url = _pick(row, "url", "链接", "新闻链接") or ""
        publish_date = _pick(row, "publish_date", "date", "日期")
        publish_time = _pick(row, "publish_time", "time", "发布时间", "时间")
        now = datetime.now(CN_TZ)
        # Validate publish_date: reject dates older than 7 days (stale source data)
        if publish_date:
            try:
                pd = date.fromisoformat(str(publish_date)[:10])
                if pd < (now.date() - timedelta(days=7)):
                    logger.debug("Rejecting stale publish_date=%s, using today", pd)
                    publish_date = None
            except ValueError:
                publish_date = None
        if not publish_date:
            publish_date = now.date().isoformat()
        publish_time_text = str(publish_time or now.strftime("%H:%M:%S"))
        external_id = _pick(row, "external_id", "news_id", "id")
        if not external_id:
            external_id = f"{source_channel}:" + hashlib.sha1(f"{title}|{content}|{publish_date}|{publish_time_text}".encode()).hexdigest()[:24]

        payload = {
            "news_id": str(external_id),
            "external_id": str(external_id),
            "title": str(title),
            "content": str(content),
            "source": "akshare_realtime",
            "source_channel": str(source_channel),
            "publish_date": str(publish_date)[:10],
            "publish_time": publish_time_text,
            "collected_at": _now_iso(),
            "url": str(url),
            "run_id": self.run_id,
            "type": "raw_news",
        }
        return {k: v for k, v in payload.items() if v is not None}

    async def _publish(self, payload: dict[str, str]) -> None:
        if self._redis is None:
            import redis.asyncio as redis

            self._redis = redis.Redis.from_url(self.redis_url, decode_responses=True)
        await self._redis.xadd(self.stream, payload, maxlen=10000, approximate=True)

    @staticmethod
    def _dedupe_key(payload: dict[str, str]) -> str:
        value = payload.get("external_id") or f"{payload.get('title')}|{payload.get('content')}"
        return hashlib.sha1(str(value).encode()).hexdigest()

    def _write_status(self) -> None:
        if not self.status_path:
            return
        stats_dict = asdict(self.stats)
        # Merge prefilter stats
        pf_stats = getattr(self._prefilter, "get_stats", None)
        if callable(pf_stats):
            stats_dict["prefilter_stats"] = pf_stats()
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(json.dumps(stats_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    def _write_skip_log(self, payload: dict[str, str], triage_result) -> None:
        if not self._prefilter_skip_log:
            return
        try:
            entry = {
                "time": _now_iso(),
                "title": str(payload.get("title", ""))[:200],
                "reason": str(triage_result.reason)[:200],
                "mode": str(triage_result.mode),
                "source": str(payload.get("source", "")),
            }
            with open(self._prefilter_skip_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass  # skip log 不是关键路径


def _pick(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _now_iso() -> str:
    return datetime.now(CN_TZ).isoformat()


def _init_prefilter(
    *,
    enabled: bool,
    mode: str,
    model_path: str,
    fail_open: bool,
):
    """Initialize the prefilter adapter (lazy import to avoid blocking collector startup)."""
    try:
        from stock_processing_service.application.services.news_prefilter import (
            NewsPreFilterAdapter,
        )
        return NewsPreFilterAdapter(
            enabled=enabled,
            mode=mode,
            model_path=model_path,
            fail_open=fail_open,
        )
    except ImportError as exc:
        logger.warning("NewsPreFilterAdapter unavailable, prefilter disabled: %s", exc)
        from stock_processing_service.application.services.news_prefilter import (
            NewsPreFilterAdapter,
        )
        return NewsPreFilterAdapter(enabled=False)

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
        self._seen: set[str] = set()
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

    async def collect_once(self) -> dict[str, int]:
        self.stats.last_fetch_at = _now_iso()
        try:
            rows = await self._fetch_news()
            self.stats.fetched_count += len(rows)
            pushed = 0
            duplicate = 0
            filtered = 0
            for row in rows:
                payload = self._normalize_payload(row)
                dedupe_key = self._dedupe_key(payload)
                if dedupe_key in self._seen:
                    duplicate += 1
                    continue

                # P1-A: prefilter hook — SKIP 则不 publish
                triage = self._prefilter.evaluate(payload)
                if not triage.pass_:
                    filtered += 1
                    self.stats.last_filter_reason = triage.reason
                    self._seen.add(dedupe_key)
                    self._write_skip_log(payload, triage)
                    continue

                self.stats.filter_pass_count += 1
                payload.update(self._prefilter.to_payload_fields(triage))
                self._seen.add(dedupe_key)
                await self._publish(payload)
                pushed += 1

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
        try:
            from news_crawler_service.services.news_crawler_service import get_news_crawler_service

            service = get_news_crawler_service()
            result = await service.crawl_news_auto(count=self.batch_size, prefer_real=True)
            if result.get("status") == "success":
                return list((result.get("response") or {}).get("news_list") or [])
            raise RuntimeError(str(result.get("error") or "crawl_news_auto failed"))
        except Exception as crawler_exc:
            logger.warning("news_crawler_service unavailable, fallback to direct akshare: %s", crawler_exc)
            return await asyncio.to_thread(self._fetch_direct_akshare)

    def _fetch_direct_akshare(self) -> list[dict[str, Any]]:
        import akshare as ak

        df = ak.stock_news_em()
        if df is None:
            return []
        records = df.head(self.batch_size).to_dict("records")
        return [dict(row) for row in records]

    def _normalize_payload(self, row: dict[str, Any]) -> dict[str, str]:
        title = _pick(row, "title", "新闻标题", "标题") or ""
        content = _pick(row, "content", "新闻内容", "内容") or title
        source = _pick(row, "source", "新闻来源", "来源") or "akshare"
        url = _pick(row, "url", "链接", "新闻链接") or ""
        publish_date = _pick(row, "publish_date", "date", "日期")
        publish_time = _pick(row, "publish_time", "time", "发布时间", "时间")
        now = datetime.now(CN_TZ)
        if not publish_date:
            publish_date = now.date().isoformat()
        publish_time_text = str(publish_time or now.strftime("%H:%M:%S"))
        external_id = _pick(row, "external_id", "news_id", "id")
        if not external_id:
            external_id = "akshare:" + hashlib.sha1(f"{title}|{content}|{publish_date}|{publish_time_text}".encode()).hexdigest()[:24]

        payload = {
            "news_id": str(external_id),
            "external_id": str(external_id),
            "title": str(title),
            "content": str(content),
            "source": "akshare_realtime",
            "source_channel": "akshare_realtime",
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
        self.status_path.parent.mkdir(parents=True, exist_ok=True)
        self.status_path.write_text(json.dumps(asdict(self.stats), ensure_ascii=False, indent=2), encoding="utf-8")

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

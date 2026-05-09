from __future__ import annotations

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from services.jyhf_cdp_service.app_manager import JyhfAppManager
from services.jyhf_cdp_service.cdp_client import CDPClient
from services.jyhf_cdp_service.config import JyhfCdpServiceConfig
from services.jyhf_cdp_service.extractors import NewEventExtractor
from services.jyhf_cdp_service.normalizer import JyhfEventNormalizer
from services.jyhf_cdp_service.schemas import CollectorStatus
from services.jyhf_cdp_service.sinks import RawEventJsonlSink
from services.jyhf_cdp_service.state import DedupStore, StatusStore


CN_TZ = ZoneInfo("Asia/Shanghai")


class JyhfCdpCollectorService:
    def __init__(self, config: JyhfCdpServiceConfig, logger) -> None:
        self._config = config
        self._logger = logger
        self._status = StatusStore(config.status_path, cdp_port=config.cdp_port)
        self._dedup = DedupStore(config.dedup_path)
        self._app = JyhfAppManager(config.app_path, config.cdp_port)
        self._extractor = NewEventExtractor()
        self._normalizer = JyhfEventNormalizer()
        self._sink = RawEventJsonlSink(config.raw_event_dir)
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    def status(self) -> CollectorStatus:
        return self._status.get()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())
        self._status.update(collector_running=True, last_error=None)
        self._logger.info("collector start requested")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task and not self._task.done():
            await asyncio.wait([self._task], timeout=5)
        self._status.update(collector_running=False)
        self._logger.info("collector stop requested")

    def logs(self, lines: int = 300) -> list[str]:
        lines = max(20, min(int(lines), 2000))
        if not self._config.log_path.exists():
            return []
        return self._config.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]

    async def _loop(self) -> None:
        totals = self._status.get().model_dump()
        while not self._stop_event.is_set():
            try:
                await asyncio.to_thread(self._capture_once, totals)
            except Exception as exc:
                totals["parse_error_count_total"] = int(totals.get("parse_error_count_total") or 0) + 1
                self._status.update(
                    collector_running=True,
                    app_running=False,
                    cdp_connected=False,
                    parse_error_count_total=totals["parse_error_count_total"],
                    last_capture_at=datetime.now(CN_TZ).isoformat(),
                    last_error=str(exc),
                )
                self._logger.exception("capture loop failed")
            await asyncio.sleep(max(self._config.interval_seconds, 5.0))
        self._status.update(collector_running=False)

    def _capture_once(self, totals: dict) -> None:
        self._app.ensure_running()
        cdp = CDPClient(self._config.cdp_port)
        cdp.connect()
        try:
            self._extractor.prepare(cdp)
            raw_events, feed_date, body_text = self._extractor.read(cdp)
        finally:
            cdp.close()

        capture_time = datetime.now(CN_TZ)
        new_count = 0
        duplicate_count = 0
        last_event_at = None
        for raw in raw_events:
            event = self._normalizer.normalize(raw, feed_date=feed_date, capture_time=capture_time)
            last_event_at = event.event_time or last_event_at
            if self._dedup.seen(event.dedup_key):
                duplicate_count += 1
                continue
            self._sink.write(event)
            self._dedup.mark(event.dedup_key)
            new_count += 1

        totals["capture_count_total"] = int(totals.get("capture_count_total") or 0) + len(raw_events)
        totals["new_event_count_total"] = int(totals.get("new_event_count_total") or 0) + new_count
        totals["duplicate_count_total"] = int(totals.get("duplicate_count_total") or 0) + duplicate_count
        self._status.update(
            collector_running=True,
            app_running=True,
            cdp_connected=True,
            current_route="/",
            current_tab="新事件",
            last_capture_at=capture_time.isoformat(),
            last_event_at=last_event_at,
            capture_count_total=totals["capture_count_total"],
            new_event_count_total=totals["new_event_count_total"],
            duplicate_count_total=totals["duplicate_count_total"],
            last_error=None,
        )
        self._logger.info("capture ok events=%s new=%s duplicate=%s", len(raw_events), new_count, duplicate_count)


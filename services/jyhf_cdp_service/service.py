from __future__ import annotations

import asyncio
import os
from datetime import datetime
from pathlib import Path
from threading import Lock
from zoneinfo import ZoneInfo

import websocket

from services.jyhf_cdp_service.app_manager import JyhfAppManager
from services.jyhf_cdp_service.cdp_client import CDPClient
from services.jyhf_cdp_service.config import JyhfCdpServiceConfig
from services.jyhf_cdp_service.db_sink import DatabaseSink
from services.jyhf_cdp_service.extractors import (
    NewEventExtractor,
    NotificationPopupExtractor,
    PersistentHookInjector,
    PrepareRetryError,
)
from services.jyhf_cdp_service.intel_pusher import IntelPusher
from services.jyhf_cdp_service.normalizer import JyhfEventNormalizer
from services.jyhf_cdp_service.schemas import CollectorStatus, RawJyhfCdpEvent
from services.jyhf_cdp_service.sinks import RawEventJsonlSink
from services.jyhf_cdp_service.state import DedupStore, StatusStore
from services.jyhf_cdp_service.token_extractor import TokenExtractor


CN_TZ = ZoneInfo("Asia/Shanghai")


class CollectorStartupFailed(RuntimeError):
    """Raised when JYHF App/CDP/DOM startup exceeded the retry fuse."""


class JyhfCdpCollectorService:
    def __init__(self, config: JyhfCdpServiceConfig, logger) -> None:
        self._config = config
        self._logger = logger
        self._status = StatusStore(config.status_path, cdp_port=config.cdp_port)
        self._dedup = DedupStore(config.dedup_path)
        self._app = JyhfAppManager(config.app_path, config.cdp_port)
        self._extractor = NewEventExtractor()
        self._popup_extractor = NotificationPopupExtractor()
        self._hook_injector = PersistentHookInjector()
        self._normalizer = JyhfEventNormalizer()
        self._sink = RawEventJsonlSink(config.raw_event_dir)
        self._intel_pusher = IntelPusher(config, logger) if config.allow_push_intel else None
        self._db_sink = DatabaseSink(config, logger) if config.allow_push_db else None
        self._token_extractor = TokenExtractor()
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        self._lifecycle_lock = asyncio.Lock()
        self._capture_lock = Lock()
        self._db_events_lock = Lock()
        self._pending_db_events: list[RawJyhfCdpEvent] = []
        # Popup/hook events to write directly to subject_history_staging
        # (the table SPS polls for intel feed display).
        self._pending_popup_rows: list[dict] = []
        self._popup_rows_lock = Lock()
        self._run_id = 0
        self._started_at: datetime | None = None
        self._startup_failure_count = 0
        self._startup_failure_limit = int(os.getenv("JYHF_CDP_STARTUP_FAILURE_LIMIT", "3"))

    def status(self) -> CollectorStatus:
        return self._status.get()

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._task and not self._task.done():
                return
            self._run_id += 1
            self._started_at = datetime.now(CN_TZ)
            self._startup_failure_count = 0
            self._stop_event.clear()
            self._task = asyncio.create_task(self._loop(self._run_id))
            self._status.update(
                collector_running=True,
                collector_state="starting",
                started_at=self._started_at.isoformat(),
                uptime_seconds=0.0,
                last_error=None,
            )
            self._logger.info("collector start requested run_id=%s", self._run_id)

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            self._run_id += 1
            self._status.update(collector_state="stopping")
            self._stop_event.set()
            task = self._task
            if task and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=1.5)
                except (asyncio.CancelledError, asyncio.TimeoutError, TimeoutError):
                    pass
                except Exception:
                    self._logger.exception("collector task stop failed")
            self._status.update(collector_running=False, collector_state="stopped", cdp_connected=False)
            self._logger.info("collector stop requested")
            # Kill JYHF app so next start doesn't conflict with stale instance
            try:
                await asyncio.to_thread(self._app.stop_app)
            except Exception:
                pass

    def logs(self, lines: int = 300) -> list[str]:
        lines = max(20, min(int(lines), 2000))
        if not self._config.log_path.exists():
            return []
        return self._config.log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]

    async def _loop(self, run_id: int) -> None:
        totals = self._status.get().model_dump()
        self._status.update(collector_state="running")
        while not self._stop_event.is_set() and run_id == self._run_id:
            try:
                await asyncio.to_thread(self._capture_once, totals, run_id)
                await self._flush_db_events()
            except asyncio.CancelledError:
                raise
            except CollectorStartupFailed as exc:
                totals["parse_error_count_total"] = int(totals.get("parse_error_count_total") or 0) + 1
                self._status.update(
                    collector_running=False,
                    collector_state="failed",
                    app_running=False,
                    cdp_connected=False,
                    parse_error_count_total=totals["parse_error_count_total"],
                    last_capture_at=datetime.now(CN_TZ).isoformat(),
                    last_error=str(exc),
                )
                self._stop_event.set()
                self._logger.error("collector startup fuse tripped: %s", exc)
                break
            except Exception as exc:
                totals["parse_error_count_total"] = int(totals.get("parse_error_count_total") or 0) + 1
                if self._record_startup_failure(str(exc)):
                    self._status.update(
                        collector_running=False,
                        collector_state="failed",
                        app_running=False,
                        cdp_connected=False,
                        parse_error_count_total=totals["parse_error_count_total"],
                        last_capture_at=datetime.now(CN_TZ).isoformat(),
                        last_error=str(exc),
                    )
                    self._stop_event.set()
                    self._logger.exception("capture loop failed; startup fuse tripped")
                    break
                else:
                    self._status.update(
                        collector_running=True,
                        collector_state="error",
                        app_running=False,
                        cdp_connected=False,
                        parse_error_count_total=totals["parse_error_count_total"],
                        last_capture_at=datetime.now(CN_TZ).isoformat(),
                        last_error=str(exc),
                    )
                self._logger.exception("capture loop failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=max(self._config.interval_seconds, 5.0))
            except (asyncio.TimeoutError, TimeoutError):
                pass
        if run_id == self._run_id:
            current = self._status.get()
            if current.collector_state != "failed":
                self._status.update(collector_running=False, collector_state="stopped")

    def _capture_once(self, totals: dict, run_id: int) -> None:
        if not self._capture_lock.acquire(blocking=False):
            self._status.update(last_error="previous capture still running")
            self._logger.warning("skip capture because previous capture is still running")
            return
        try:
            self._capture_once_locked(totals, run_id)
        finally:
            self._capture_lock.release()

    def _capture_once_locked(self, totals: dict, run_id: int) -> None:
        if not self._app.ensure_running(should_stop=self._stop_event.is_set):
            if self._record_startup_failure("JYHF app launch already in progress"):
                raise CollectorStartupFailed(self._startup_failure_message("JYHF app launch already in progress"))
            return
        if self._stop_event.is_set() or run_id != self._run_id:
            return
        cdp = CDPClient(self._config.cdp_port)
        max_ws_retries = 2  # WebSocket 瞬断重试次数
        for ws_attempt in range(max_ws_retries + 1):
            try:
                cdp.connect()
            except Exception as exc:
                if ws_attempt < max_ws_retries:
                    self._logger.warning("CDP connect failed (attempt %s/%s): %s", ws_attempt + 1, max_ws_retries + 1, exc)
                    continue
                raise
            try:
                # ── Phase 0: Persistent hooks (idempotent) ──
                try:
                    self._hook_injector.ensure_injected(cdp)
                except Exception:
                    pass

                # ── Phase 1: Token hooks ──
                try:
                    self._token_extractor.inject_hooks(cdp)
                except Exception:
                    pass

                # ── Phase 2: Drain hook notifications + capture popup ──
                # These are INDEPENDENT of feed extraction.  They produce
                # unmasked events (subject_id + full driver text) even when
                # the feed is paywalled.  Write them directly to
                # subject_history_staging so SPS/frontend see them immediately.
                raw_events: list[dict] = []

                # 2a: Hook notifications (router beforeEach + hashchange)
                try:
                    raw_notifs = self._hook_injector.drain_notifications(cdp)
                    for n in raw_notifs:
                        ev = self._raw_notification_to_event(n)
                        if ev:
                            raw_events.append(ev)
                    if raw_notifs:
                        self._logger.info(
                            "drained %s hook notifications subjects=%s",
                            len(raw_notifs),
                            [e.get("subject_name", "") for e in raw_events[-len(raw_notifs):]],
                        )
                except Exception:
                    pass

                # 2b: Current popup (if displayed)
                try:
                    if self._popup_extractor.detect(cdp):
                        popup_evs = self._popup_extractor.read(cdp)
                        raw_events.extend(popup_evs)
                        if popup_evs:
                            self._logger.info(
                                "popup captured subject=%s subject_key=%s",
                                popup_evs[0].get("subject_name"),
                                popup_evs[0].get("subject_key"),
                            )
                except Exception:
                    pass

                # Queue popup/hook events for direct write to
                # subject_history_staging (the table SPS polls).
                # These have unmasked subject_id + full driver text.
                if raw_events:
                    with self._popup_rows_lock:
                        self._pending_popup_rows.extend(raw_events)

                # ── Phase 3: Feed extraction (best-effort — may fail on
                # paywalled or stale pages without blocking popup events) ──
                feed_date = ""
                body_text = ""
                try:
                    self._extractor.prepare(cdp)
                    feed_events, feed_date, body_text = self._extractor.read(cdp)
                    # Filter: skip masked feed events (account expired).
                    # Popup events provide the unmasked data for followed subjects.
                    masked_count = sum(1 for e in feed_events if e.get("subject_name") == "********")
                    feed_events = [e for e in feed_events if e.get("subject_name") != "********"]
                    if masked_count:
                        self._logger.debug("filtered %s masked feed events", masked_count)
                    raw_events.extend(feed_events)
                except PrepareRetryError as e:
                    self._logger.warning("feed extraction skipped: %s", e)
                except Exception as e:
                    self._logger.warning("feed extraction failed: %s", e)

                # Phase 2: after navigation triggered API calls, read captured tokens
                token_extracted = False
                try:
                    token_extracted = self._token_extractor.read_captured_tokens(cdp) is not None
                except Exception:
                    pass
                break  # 成功，退出重试循环
            except (PrepareRetryError, websocket.WebSocketConnectionClosedException) as exc:
                cdp.close()
                if ws_attempt < max_ws_retries:
                    self._logger.warning(
                        "CDP ws error (attempt %s/%s), reconnecting: %s",
                        ws_attempt + 1, max_ws_retries + 1, exc,
                    )
                    continue  # 重连重试
                else:
                    # 所有重试耗尽，走原有熔断逻辑
                    reason = f"JYHF CDP prepare failed after {max_ws_retries + 1} attempts: {exc}"
                    if self._record_startup_failure(reason):
                        raise CollectorStartupFailed(self._startup_failure_message(reason))
                    self._logger.warning(
                        "prepare not ready, will retry next cycle (%s/%s)",
                        self._startup_failure_count,
                        self._startup_failure_limit,
                    )
                    return
            finally:
                cdp.close()

        capture_time = datetime.now(CN_TZ)
        # feed_date 为空时用采集时间（避免旧事件被标记为未来时间）
        if not feed_date:
            feed_date = capture_time.strftime("%Y-%m-%d")

        # Always update token status, even if no events captured
        if token_extracted:
            self._status.update(
                token_extracted=True,
                token_last_at=capture_time.isoformat(),
            )

        # Always update status to reflect CDP connectivity, even with 0 events.
        # This prevents the frontend from showing "CDP 未连接" when the
        # capture cycle ran but found nothing new.
        if self._stop_event.is_set() or run_id != self._run_id:
            return

        new_count = 0
        last_event_at = None
        if raw_events:
            for raw in raw_events:
                if self._stop_event.is_set() or run_id != self._run_id:
                    return
                event = self._normalizer.normalize(raw, feed_date=feed_date, capture_time=capture_time)
                last_event_at = capture_time.replace(tzinfo=CN_TZ).isoformat()
                new_count += 1
                if self._intel_pusher:
                    self._intel_pusher.push(event)
                if self._db_sink:
                    with self._db_events_lock:
                        self._pending_db_events.append(event)

        totals["capture_count_total"] = int(totals.get("capture_count_total") or 0) + len(raw_events)
        totals["new_event_count_total"] = int(totals.get("new_event_count_total") or 0) + new_count
        pushed_to_stream = int(totals.get("pushed_to_stream_count_total") or 0) + new_count
        pushed_to_intel = int(totals.get("pushed_to_intel_count_total") or 0) + (new_count if self._intel_pusher else 0)
        totals["pushed_to_stream_count_total"] = pushed_to_stream
        totals["pushed_to_intel_count_total"] = pushed_to_intel
        if self._stop_event.is_set() or run_id != self._run_id:
            return
        self._status.update(
            collector_running=True,
            collector_state="running",
            app_running=True,
            cdp_connected=True,
            current_route="/",
            current_tab="新事件",
            last_capture_at=capture_time.isoformat(),
            last_event_at=last_event_at,
            capture_count_total=totals["capture_count_total"],
            new_event_count_total=totals["new_event_count_total"],
            duplicate_count_total=0,
            pushed_to_stream_count_total=totals["pushed_to_stream_count_total"],
            pushed_to_intel_count_total=totals["pushed_to_intel_count_total"],
            uptime_seconds=self._uptime_seconds(capture_time),
            token_extracted=bool(self._token_extractor.last_token),
            token_last_at=datetime.fromtimestamp(self._token_extractor.last_extract_time, tz=CN_TZ).isoformat() if self._token_extractor.last_token else None,
            last_error=None,
        )
        self._logger.info("capture ok events=%s new=%s token=%s", len(raw_events), new_count, "yes" if self._token_extractor.last_token else "no")
        self._startup_failure_count = 0

    def _record_startup_failure(self, reason: str) -> bool:
        if self._status.get().capture_count_total > 0:
            return False
        self._startup_failure_count += 1
        self._logger.warning(
            "JYHF startup failure %s/%s: %s",
            self._startup_failure_count,
            self._startup_failure_limit,
            reason,
        )
        return self._startup_failure_count >= self._startup_failure_limit

    def _startup_failure_message(self, reason: str) -> str:
        return (
            f"JYHF startup failed after {self._startup_failure_count}/"
            f"{self._startup_failure_limit} attempts: {reason}; "
            "collector stopped to prevent repeated app relaunch"
        )

    async def _flush_db_events(self) -> None:
        # 1) Write popup/hook events to subject_history_staging
        #    (the table SPS polls for frontend intel feed).
        with self._popup_rows_lock:
            if self._pending_popup_rows:
                popup_rows = self._pending_popup_rows
                self._pending_popup_rows = []
            else:
                popup_rows = None

        if popup_rows:
            try:
                await self._write_popup_rows_to_staging(popup_rows)
            except Exception:
                self._logger.exception("popup staging write failed")

        # 2) Write normalized events via db_sink (event_subject_map).
        if not self._db_sink:
            return
        with self._db_events_lock:
            if not self._pending_db_events:
                return
            events = self._pending_db_events
            self._pending_db_events = []
        batch_id = f"cdp_{datetime.now(CN_TZ).strftime('%Y%m%d_%H%M%S')}"
        try:
            written = await self._db_sink.write_events(events, batch_id)
            self._status.update(pushed_to_db_count_total=int(
                (self._status.get().pushed_to_db_count_total or 0) + written
            ))
        except Exception:
            self._logger.exception("db_sink flush failed batch_id=%s count=%s", batch_id, len(events))

    async def _write_popup_rows_to_staging(self, rows: list[dict]) -> int:
        """Write popup/hook event dicts directly to subject_history_staging.

        This is the table that SPS polls for the intel feed frontend display.
        Uses ``source_type='jyhf_cdp'`` to match the SPS query filter.
        """
        import asyncpg

        conn = await asyncpg.connect(
            host=self._config.pg_host,
            port=self._config.pg_port,
            database=self._config.pg_database,
            user=self._config.pg_username,
            password=self._config.pg_password,
            timeout=10,
        )
        try:
            td = datetime.now(CN_TZ).date()
            batch_id = f"popup_{datetime.now(CN_TZ).strftime('%Y%m%d_%H%M%S')}"
            written = 0

            for ev in rows:
                sn = str(ev.get("subject_name") or "").strip()
                sid = str(ev.get("subject_key") or "").strip()
                dt = str(ev.get("driver_title") or "").strip()
                desc_text = str(ev.get("driver_desc") or "").strip()
                ns = str(ev.get("news_source") or "").strip()

                if not sn:
                    continue

                desc = f"【驱动事件：{dt}】"
                if desc_text:
                    desc += f"\n{desc_text}"
                if ns:
                    desc += f"\n（新闻来源：{ns}）"

                await conn.execute(
                    "INSERT INTO subject_history_staging "
                    "(subject_key,subject_name,rank_date,description,heat,heat_name,"
                    " pct_chg,his_pct_chg,source_type,ingest_batch_id) "
                    "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)",
                    sid or sn, sn, td, desc, 3, "热", 0.0, 0.0,
                    "jyhf_cdp", batch_id,
                )
                written += 1

            if written:
                self._logger.info(
                    "popup_staging: wrote %s rows to subject_history_staging",
                    written,
                )
            return written
        finally:
            await conn.close()

    # ── Notification conversion ──────────────────────────────────

    @staticmethod
    def _raw_notification_to_event(raw: dict) -> dict | None:
        """Convert a raw hook notification dict to the event format expected
        by the normalizer (same shape as ``NewEventExtractor.read()`` output).
        """
        import re

        subject_name = str(raw.get("subject_name") or "").strip()
        subject_id = str(raw.get("subject_id") or "").strip()
        content = str(raw.get("content") or "").strip()

        if not subject_name or not content:
            return None

        # Parse structured fields from content (same logic as popup extractor)
        driver_title = ""
        driver_desc = ""
        news_source = ""

        dm = re.search(r"【驱动事件[：:](.*?)】", content)
        if dm:
            driver_title = dm.group(1).strip()

        sm = re.search(r"（新闻来源[：:](.*?)）", content)
        if sm:
            news_source = sm.group(1).strip()

        desc_start = content.find("】") + 1
        desc_end = content.find("（新闻来源：")
        if desc_end < 0:
            desc_end = len(content)
        if 0 < desc_start < desc_end:
            driver_desc = content[desc_start:desc_end].strip()
        elif desc_start > 0:
            driver_desc = content[desc_start:].strip()

        capture_time = raw.get("captured_at", "")
        event_time = ""
        if capture_time:
            # Extract HH:MM from ISO timestamp
            tm = re.search(r"T(\d{2}:\d{2})", capture_time)
            if tm:
                event_time = tm.group(1)

        return {
            "event_time": event_time,
            "subject_name": subject_name,
            "subject_key": subject_id,
            "pct_chg_text": "",
            "driver_title": driver_title,
            "driver_desc": driver_desc,
            "news_source": news_source,
            "event_type": "驱动事件",
            "raw_text": content,
        }

    def _uptime_seconds(self, now: datetime | None = None) -> float:
        if not self._started_at:
            return 0.0
        return max(((now or datetime.now(CN_TZ)) - self._started_at).total_seconds(), 0.0)

    def _save_snapshot(self, body_text: str, reason: str, ts: datetime) -> Path:
        safe_reason = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in reason)[:80]
        self._config.snapshot_dir.mkdir(parents=True, exist_ok=True)
        path = self._config.snapshot_dir / f"new_event_{ts.strftime('%Y%m%d_%H%M%S')}_{safe_reason}.txt"
        path.write_text(body_text or "", encoding="utf-8")
        self._logger.warning("saved DOM snapshot: %s", path)
        return path

    @staticmethod
    def _format_event_datetime(trade_date: str, event_time: str) -> str | None:
        if not trade_date or not event_time:
            return None
        try:
            return datetime.fromisoformat(f"{trade_date}T{event_time}:00").replace(tzinfo=CN_TZ).isoformat()
        except Exception:
            return event_time

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

    # ── P1.5: New subject auto-registration ───────────────────────
    # Per CDP_DOM行情数据采集P1设计方案.md §12.6, when a popup
    # notification carries a subject_key not in subject_detail, the
    # collector auto-registers it: subject_detail + theme_gate_profile
    # + subject_stock_staging (best-effort API fetch).

    async def _write_popup_rows_to_staging(self, rows: list[dict]) -> int:
        """Write popup/hook event dicts directly to subject_history_staging.

        This is the table that SPS polls for the intel feed frontend display.
        Uses ``source_type='jyhf_cdp'`` to match the SPS query filter.

        P1.5: New subjects (subject_key not in subject_detail) trigger
        auto-registration of subject_detail + theme_gate_profile.
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
            newly_registered: set[str] = set()

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

                # ── P1.5: New subject detection & auto-registration ──
                if sid and sid.strip().isdigit() and sid not in newly_registered:
                    newly_registered.add(sid)
                    try:
                        is_new = await self._ensure_subject_registered(
                            conn, sid, sn, dt, desc_text, ns,
                        )
                        if is_new:
                            self._logger.info(
                                "new_subject_registered: key=%s name=%s",
                                sid, sn,
                            )
                            # Best-effort: fetch constituent stocks via JYHF API
                            try:
                                stock_count = await self._fetch_subject_stocks(
                                    conn, sid, sn,
                                )
                                if stock_count:
                                    self._logger.info(
                                        "new_subject_stocks: key=%s count=%s",
                                        sid, stock_count,
                                    )
                                    # P1.5: extract taxonomy graph via CDP DOM
                                    stock_rows = await conn.fetch(
                                        "SELECT stock_id, stock_name FROM "
                                        "subject_stock_staging WHERE subject_key=$1",
                                        sid,
                                    )
                                    api_stocks = [
                                        {"stock_id": r["stock_id"],
                                         "stock_name": r["stock_name"]}
                                        for r in stock_rows
                                    ]
                                    await self._extract_subject_graph_via_cdp(
                                        conn, sid, sn, api_stocks,
                                    )
                            except Exception:
                                self._logger.exception(
                                    "new_subject_stocks_failed: key=%s", sid,
                                )
                    except Exception:
                        self._logger.exception(
                            "new_subject_registration_failed: key=%s name=%s",
                            sid, sn,
                        )

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

    async def _ensure_subject_registered(
        self,
        conn,
        subject_key: str,
        subject_name: str,
        driver_title: str,
        driver_desc: str,
        news_source: str,
    ) -> bool:
        """Ensure subject_key exists in subject_detail + theme_gate_profile.

        Returns True if this is a newly registered subject, False if it
        already existed.
        """
        existing = await conn.fetchval(
            "SELECT 1 FROM subject_detail WHERE subject_key = $1", subject_key,
        )
        if existing:
            return False

        reason_short = driver_title
        detail_html = (
            f"<p><strong>题材：</strong>{subject_name}</p>"
            f"<p><strong>驱动事件：</strong>{driver_title}</p>"
        )
        if driver_desc:
            detail_html += f"<p>{driver_desc}</p>"
        if news_source:
            detail_html += f"<p><strong>新闻来源：</strong>{news_source}</p>"
            reason_short += f"（来源：{news_source}）"

        # Step 1: subject_detail
        await conn.execute(
            """INSERT INTO subject_detail
               (subject_key, detail_html, reason_short, detail_version,
                is_current, created_at, updated_at)
               VALUES ($1, $2, $3, 1, true, NOW(), NOW())
               ON CONFLICT (subject_key) DO UPDATE SET
                  reason_short = EXCLUDED.reason_short,
                  detail_html = EXCLUDED.detail_html,
                  updated_at = NOW()""",
            subject_key, detail_html, reason_short,
        )

        # Step 2: theme_master (required for active_binding status in
        # vw_subject_theme_binding — without it the frontend shows "staging_only")
        await conn.execute(
            """INSERT INTO theme_master (
                 name, code, description, status, theme_type,
                 source_system, source_id,
                 heat_score, confidence_score, lifecycle_stage,
                 created_at, updated_at
               ) VALUES ($1, $2, $3, 'active', 'concept',
                         'jyhf', $4, 60, 0.85, 'growth', NOW(), NOW())
               ON CONFLICT DO NOTHING""",
            subject_name, subject_key,
            f"【驱动事件：{driver_title}】{driver_desc[:200] if driver_desc else ''}",
            subject_key,
        )

        # Step 3: subject_node_staging (required by vw_subject_theme_binding
        # for ThemeWorkspace frontend navigation to resolve).
        await conn.execute(
            """INSERT INTO subject_node_staging
               (subject_key, subject_name, node_level, source_type,
                status, created_at, updated_at)
               VALUES ($1, $2, 1, 'jyhf_cdp_popup', 'active', NOW(), NOW())
               ON CONFLICT DO NOTHING""",
            subject_key, subject_name,
        )

        # Step 3: theme_gate_profile (auto-derived from subject_name + driver)
        gate = self._derive_gate_profile(subject_name, driver_title, driver_desc)
        await self._upsert_gate_profile(conn, subject_key, subject_name, gate)

        # Step 4: subject_rank_daily — so the subject appears in frontend rankings
        rank_desc = f"【驱动事件：{driver_title}】{driver_desc[:120] if driver_desc else ''}"
        await conn.execute(
            """INSERT INTO subject_rank_daily
               (subject_key, rank_date, heat, heat_name, pct_chg, his_pct_chg,
                red, description, source_system, created_at, updated_at)
               VALUES ($1, CURRENT_DATE, 3, '热', 0.0, 0.0,
                       true, $2, 'jyhf', NOW(), NOW())
               ON CONFLICT (subject_key, rank_date) DO NOTHING""",
            subject_key, rank_desc,
        )

        return True

    async def _upsert_gate_profile(
        self, conn, subject_key: str, subject_name: str, gate: dict,
    ) -> None:
        import json as _json

        must_terms = gate.get("must", [])
        strong_terms = gate.get("strong", [])
        weak_terms = gate.get("weak", [])
        negative_terms = gate.get("not", [])
        all_terms = [subject_name, *must_terms, *strong_terms, *weak_terms]
        search_text = " ".join(dict.fromkeys(all_terms))

        ontology = _json.dumps({
            "concept": subject_name,
            "semantic_type": "event_driven",
            "strategy_type": "concept",
            "dimensions": {},
        }, ensure_ascii=False)
        gate_json = _json.dumps({
            "concept": subject_name,
            "semantic_type": "event_driven",
            "strategy_type": "concept",
            "must": must_terms,
            "should": strong_terms + weak_terms,
            "not": negative_terms,
            "quality": "cdp_auto",
            "source": "jyhf_cdp_popup",
        }, ensure_ascii=False)

        await conn.execute(
            """INSERT INTO theme_gate_profile (
                 subject_key, source_system, concept, semantic_type, strategy_type,
                 ontology_json, gate_json,
                 must_terms, should_terms, not_terms,
                 strong_terms, weak_terms, negative_terms,
                 search_text, quality, gate_version,
                 created_at, updated_at
               ) VALUES (
                 $1, 'jyhf', $2, 'event_driven', 'concept',
                 $3::jsonb, $4::jsonb,
                 $5::jsonb, $6::jsonb, $7::jsonb,
                 $8::jsonb, $9::jsonb, $10::jsonb,
                 $11, 'cdp_auto', 1,
                 NOW(), NOW()
               )
               ON CONFLICT (subject_key) DO UPDATE SET
                 concept = EXCLUDED.concept,
                 gate_json = EXCLUDED.gate_json,
                 must_terms = EXCLUDED.must_terms,
                 strong_terms = EXCLUDED.strong_terms,
                 weak_terms = EXCLUDED.weak_terms,
                 search_text = EXCLUDED.search_text,
                 quality = EXCLUDED.quality,
                 updated_at = NOW()""",
            subject_key, subject_name,
            ontology, gate_json,
            _json.dumps(must_terms, ensure_ascii=False),
            _json.dumps(strong_terms + weak_terms, ensure_ascii=False),
            _json.dumps(negative_terms, ensure_ascii=False),
            _json.dumps(strong_terms, ensure_ascii=False),
            _json.dumps(weak_terms, ensure_ascii=False),
            _json.dumps(negative_terms, ensure_ascii=False),
            search_text,
        )

    async def _fetch_subject_stocks(
        self, conn, subject_key: str, subject_name: str,
    ) -> int:
        """Fetch constituent stocks via JYHF API and write to
        subject_stock_staging.  Best-effort — failures are logged but
        never propagate.
        """
        import json as _json
        import httpx

        token = self._load_jyhf_token()
        if not token:
            self._logger.warning("new_subject_stocks: no JYHF token available")
            return 0

        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                r = await client.get(
                    "https://app.txcfgl.com/api/app/stock/realtime-by-subject/v2",
                    params={"subjectId": subject_key},
                    headers={"Authorization": f"Bearer {token}"},
                )
            if r.status_code != 200:
                self._logger.warning(
                    "new_subject_stocks API returned %s for subject %s",
                    r.status_code, subject_key,
                )
                return 0
            rows = r.json().get("rows", [])
        except Exception:
            self._logger.exception(
                "new_subject_stocks API call failed for subject %s", subject_key,
            )
            return 0

        if not rows:
            return 0

        batch_id = f"jyhf_api_{datetime.now(CN_TZ).strftime('%Y%m%d_%H%M%S')}"
        inserted = 0
        for rank_idx, row in enumerate(rows):
            try:
                raw_code = str(row[2])
                stock_id = f"{raw_code}.{'SH' if raw_code.startswith(('6','9')) else 'SZ'}"
                stock_name = str(row[3])
                ev = _json.dumps({
                    "current": row[4], "pct_chg": row[10],
                    "amount": row[13], "vol": row[12],
                    "open": row[5], "high": row[7], "low": row[6],
                    "rank_no": row[19] if len(row) > 19 and row[19] else None,
                }, ensure_ascii=False)
                await conn.execute(
                    """INSERT INTO subject_stock_staging (
                         subject_key, stock_id, stock_name, source_type,
                         confidence, sort, evidence_json, ingest_batch_id,
                         created_at, updated_at
                       ) VALUES (
                         $1, $2, $3, 'jyhf_api',
                         1.0, $4, $5::jsonb, $6,
                         NOW(), NOW()
                       )
                       ON CONFLICT (subject_key, stock_id) DO UPDATE SET
                         stock_name = EXCLUDED.stock_name,
                         confidence = EXCLUDED.confidence,
                         sort = EXCLUDED.sort,
                         evidence_json = EXCLUDED.evidence_json,
                         updated_at = NOW()""",
                    subject_key, stock_id, stock_name,
                    rank_idx + 1, ev, batch_id,
                )
                inserted += 1
            except Exception:
                self._logger.exception(
                    "new_subject_stocks insert failed for %s row %s",
                    subject_key, rank_idx,
                )
        return inserted

    # ── P1.5: CDP subject taxonomy graph extraction ─────────────────
    # Per CDP_DOM行情数据采集P1设计方案.md §12.7, the subject taxonomy
    # (参股/合作/钼矿 etc.) is embedded in the JYHF app DOM (not API).
    # This extracts the tree via CDP, maps API-returned stocks to nodes,
    # and persists everything to subject_children_staging +
    # jyhf_subject_taxonomy_relation + subject_child_stock_reason.

    async def _extract_subject_graph_via_cdp(
        self, conn, subject_key: str, subject_name: str, api_stocks: list[dict],
    ) -> bool:
        """Extract JYHF subject taxonomy graph via CDP DOM and persist.

        Navigates to ``#/subject/detail/{id}/vip-table``, parses the
        taxonomy tree from body text, maps API-provided stocks to
        taxonomy nodes, and inserts into the three graph tables.

        Best-effort — failures are logged but never propagate.
        """
        import asyncio as _asyncio
        import time as _time

        cdp = None
        try:
            # ── Navigate to subject detail page ──
            cdp = CDPClient(self._config.cdp_port)
            cdp.connect()

            # Click the subject in the excavate page (only reliable method)
            clicked = cdp.evaluate(
                f"""(function() {{
    var all = document.querySelectorAll('td, [class*="row"], [class*="item"]');
    for (var i = 0; i < all.length; i++) {{
        if (all[i].innerText && all[i].innerText.indexOf('{subject_name}') >= 0) {{
            all[i].click();
            return 'clicked';
        }}
    }}
    return 'not_found';
}})()""",
                timeout=6.0,
            )
            if str(clicked) != "clicked":
                # Fallback: router push
                cdp.evaluate(
                    f"""(function() {{
    var app = document.querySelector('#app');
    if (app && app.__vue_app__) {{
        app.__vue_app__.config.globalProperties.$router.push(
            '/subject/detail/{subject_key}/vip-table');
    }}
}})()""",
                    timeout=3.0,
                )

            # Wait for page render
            _time.sleep(4.0)

            # ── Extract body text ──
            body_text = cdp.evaluate("document.body.innerText", timeout=6.0)
            if not isinstance(body_text, str) or len(body_text) < 50:
                self._logger.warning(
                    "subject_graph: empty body text for %s", subject_key,
                )
                return False

            # ── Parse taxonomy tree ──
            taxonomy = self._parse_subject_taxonomy(body_text, subject_name)
            if not taxonomy:
                self._logger.warning(
                    "subject_graph: taxonomy parse failed for %s", subject_key,
                )
                return False

            # ── Map stocks to taxonomy nodes ──
            self._map_stocks_to_taxonomy(taxonomy, api_stocks)

            # ── Persist ──
            await self._persist_taxonomy_graph(
                conn, subject_key, subject_name, taxonomy,
            )

            total_nodes = sum(
                1 + len(v) for v in taxonomy.values()
            )
            self._logger.info(
                "subject_graph: persisted taxonomy for %s (%s branches, %s nodes)",
                subject_key, len(taxonomy), total_nodes,
            )
            return True

        except Exception:
            self._logger.exception(
                "subject_graph: CDP extraction failed for %s", subject_key,
            )
            return False
        finally:
            if cdp:
                cdp.close()

    @staticmethod
    def _parse_subject_taxonomy(body_text: str, subject_name: str) -> dict | None:
        """Parse JYHF subject detail DOM text into taxonomy tree.

        Returns ``{l1_name: {l2_name: []}}`` where leaf values are
        placeholder lists for stock mappings.

        Heuristic: a node is Level-1 (category) if it is immediately
        followed by PCT then another NODE (its first child).  A node is
        Level-2 (leaf) if it is followed by PCT then STAR (masked stock).
        """
        import re

        graph_idx = body_text.find("题材图谱")
        if graph_idx < 0:
            return None

        section = body_text[graph_idx:]
        lines = [line.strip() for line in section.split("\n") if line.strip()]

        # Find root node (second occurrence of subject_name)
        root_idx = None
        for i, line in enumerate(lines):
            if line == subject_name and i > 0:
                root_idx = i
                break
        if root_idx is None:
            return None

        pct_re = re.compile(r"^[+-]?\d+\.?\d*%$")
        star_re = re.compile(r"^\*+$")

        # Skip root + its pct_chg
        i = root_idx + 1
        if i < len(lines) and pct_re.match(lines[i]):
            i += 1

        taxonomy: dict[str, dict[str, list]] = {}
        current_l1: str | None = None

        while i < len(lines):
            line = lines[i]

            if pct_re.match(line) or star_re.match(line):
                i += 1
                continue

            if line == subject_name:
                i += 1
                continue

            # Determine L1 vs L2: skip the immediate PCT, then check
            # whether the next meaningful line is a NODE (→ L1) or
            # STAR/end (→ L2).
            look = i + 1
            if look < len(lines) and pct_re.match(lines[look]):
                look += 1
            next_is_node = (
                look < len(lines)
                and not pct_re.match(lines[look])
                and not star_re.match(lines[look])
            )

            if current_l1 is None or next_is_node:
                # New Level-1 branch (first node, or node has children)
                current_l1 = line
                taxonomy[line] = {}
            else:
                # Level-2 leaf under current L1
                if current_l1 and current_l1 in taxonomy:
                    taxonomy[current_l1][line] = []

            i = look

        return taxonomy if taxonomy else None

    @staticmethod
    def _map_stocks_to_taxonomy(
        taxonomy: dict, api_stocks: list[dict],
    ) -> None:
        """Map API-returned stocks to taxonomy leaf nodes by keyword matching.

        Modifies *taxonomy* in-place, setting leaf values to lists of
        ``{"stock_id": ..., "stock_name": ..., "reason": ...}`` dicts.
        """
        # Build keyword index from taxonomy node names
        node_keywords: dict[str, list[str]] = {}
        for l1_name, l2_map in taxonomy.items():
            for l2_name in l2_map:
                keywords = [l2_name]
                # Add L1 context words
                if "原材料" in l1_name:
                    keywords.extend(["矿", "材料", "金属", "资源"])
                if "半导体" in l1_name:
                    keywords.extend(["半导体", "芯片", "封测", "靶材", "气"])
                if "钼" in l2_name:
                    keywords.append("钼")
                if "钨" in l2_name:
                    keywords.append("钨")
                if "参股" in l2_name:
                    keywords.extend(["合资", "持股", "参股"])
                if "合作" in l2_name:
                    keywords.extend(["合作", "供应", "分销", "封测", "服务"])
                node_keywords[l2_name] = keywords

        # For each stock, find best matching node
        for stock in api_stocks:
            stock_id = stock.get("stock_id", "")
            stock_name = stock.get("stock_name", "")
            stock_text = f"{stock_name}"

            best_node = None
            best_score = 0

            for l2_name, keywords in node_keywords.items():
                score = sum(1 for kw in keywords if kw in stock_text)
                if score > best_score:
                    best_score = score
                    best_node = l2_name

            if best_node and best_score > 0:
                for l1_name, l2_map in taxonomy.items():
                    if best_node in l2_map:
                        l2_map[best_node].append({
                            "stock_id": stock_id,
                            "stock_name": stock_name,
                            "reason": f"「{best_node}」相关标的",
                        })
                        break

    async def _persist_taxonomy_graph(
        self,
        conn,
        subject_key: str,
        subject_name: str,
        taxonomy: dict,
    ) -> None:
        """Insert taxonomy tree into subject_children_staging +
        jyhf_subject_taxonomy_relation + subject_child_stock_reason.
        """
        import json as _json

        # Delete old entries for idempotent rebuild
        await conn.execute(
            "DELETE FROM jyhf_subject_taxonomy_relation "
            "WHERE parent_subject_key LIKE $1",
            f"{subject_key}%",
        )
        await conn.execute(
            "DELETE FROM subject_children_staging "
            "WHERE parent_subject_key LIKE $1",
            f"{subject_key}%",
        )
        await conn.execute(
            "DELETE FROM subject_child_stock_reason "
            "WHERE subject_key LIKE $1",
            f"{subject_key}%",
        )

        l1_sort = 0
        for l1_name, l2_map in taxonomy.items():
            l1_sort += 1
            l1_key = f"{subject_key}_{l1_name}"

            # ── subject_children_staging (L1) ──
            total_stocks = sum(len(v) for v in l2_map.values())
            await conn.execute(
                """INSERT INTO subject_children_staging (
                     parent_subject_key, child_subject_key, child_name,
                     stock_count, source_type, sort, created_at, updated_at
                   ) VALUES ($1, $2, $3, $4, 'jyhf_cdp_dom', $5, NOW(), NOW())""",
                subject_key, l1_key, l1_name, total_stocks, l1_sort,
            )

            # ── jyhf_subject_taxonomy_relation (root → L1) ──
            await conn.execute(
                """INSERT INTO jyhf_subject_taxonomy_relation (
                     parent_subject_key, parent_subject_name,
                     child_subject_key, child_subject_name,
                     relation_type, depth, source_table, confidence
                   ) VALUES ($1, $2, $3, $4, 'child', 1,
                             'subject_children_staging', 1.0)""",
                subject_key, subject_name, l1_key, l1_name,
            )

            l2_sort = 0
            for l2_name, stocks in l2_map.items():
                l2_sort += 1
                l2_key = f"{subject_key}_{l2_name}"

                # ── subject_children_staging (L2) ──
                await conn.execute(
                    """INSERT INTO subject_children_staging (
                         parent_subject_key, child_subject_key, child_name,
                         stock_count, source_type, sort, created_at, updated_at
                       ) VALUES ($1, $2, $3, $4, 'jyhf_cdp_dom', $5, NOW(), NOW())""",
                    l1_key, l2_key, l2_name, len(stocks), l2_sort,
                )

                # ── jyhf_subject_taxonomy_relation (L1 → L2) ──
                await conn.execute(
                    """INSERT INTO jyhf_subject_taxonomy_relation (
                         parent_subject_key, parent_subject_name,
                         child_subject_key, child_subject_name,
                         relation_type, depth, source_table, confidence
                       ) VALUES ($1, $2, $3, $4, 'child', 2,
                                 'subject_children_staging', 1.0)""",
                    l1_key, l1_name, l2_key, l2_name,
                )

                # ── subject_child_stock_reason ──
                for sort_order, s in enumerate(stocks):
                    await conn.execute(
                        """INSERT INTO subject_child_stock_reason (
                             subject_key, child_name, stock_id, stock_name,
                             reason, source_type, sort_order,
                             created_at, updated_at
                           ) VALUES ($1, $2, $3, $4, $5,
                                     'jyhf_cdp_dom', $6, NOW(), NOW())""",
                        l2_key, l2_name,
                        s["stock_id"], s["stock_name"],
                        s.get("reason", f"「{l2_name}」相关标的"),
                        sort_order + 1,
                    )

    def _load_jyhf_token(self) -> str | None:
        """Read JYHF auth token from the in-memory extractor or on-disk file."""
        if self._token_extractor.last_token:
            return self._token_extractor.last_token
        try:
            import json as _json
            return _json.loads(
                Path("/tmp/jyhf_auth_token.json").read_text()
            ).get("token")
        except Exception:
            return None

    @staticmethod
    def _derive_gate_profile(
        subject_name: str, driver_title: str, driver_desc: str,
    ) -> dict:
        """Auto-generate a minimal gate profile from popup event fields.

        Rule-based term extraction without external NLP dependencies.
        Produces must/strong/weak term lists for theme_gate_profile.
        """
        import re

        # ── Segment subject name on common separators ──
        name_parts: list[str] = []
        for chunk in re.split(r"[以的及与和：:，,、（）()\s]+", subject_name):
            chunk = chunk.strip()
            if len(chunk) >= 2:
                name_parts.append(chunk)

        # ── Extract structured terms from driver event text ──
        full_text = f"{driver_title} {driver_desc}"

        def _dedup(items: list[str]) -> list[str]:
            return list(dict.fromkeys(item for item in items if item))

        _fn_prefixes = {
            "使用", "在于", "并将", "并在", "以及", "及其", "替代", "计划",
            "此次", "该产", "在同等",
        }
        _fn_chars = "的使用在为将于和与及以并最已该此代士正可即"

        def _trim_fn_prefix(raw: str) -> str:
            """Strip common function-word prefixes that create sentence fragments."""
            for pf in sorted(_fn_prefixes, key=len, reverse=True):
                if raw.startswith(pf):
                    raw = raw[len(pf):]
                    break
            else:
                while raw and raw[0] in _fn_chars:
                    raw = raw[1:]
            return raw

        # Company names: 2-6 汉字 + 公司/集团/股份
        company_hits: list[str] = []
        for m in re.finditer(
            r"[\u4e00-\u9fff]{2,6}(?:公司|集团|股份)", full_text,
        ):
            company_hits.append(m.group(0))

        # Product/technology: 2-4 汉字 + 材料/闪存/芯片/内存/金属/工艺/技术
        product_hits: list[str] = []
        for m in re.finditer(
            r"[\u4e00-\u9fff]{2,4}(?:材料|闪存|芯片|内存|金属|工艺|技术)",
            full_text,
        ):
            raw = _trim_fn_prefix(m.group(0))
            if len(raw) >= 3:
                product_hits.append(raw)
        product_hits = _dedup(product_hits)

        # Acronyms: NAND, HBM, DRAM, HBM4E etc. (delimited by non-letter)
        acronym_hits: list[str] = []
        for m in re.finditer(r"(?:^|[^A-Za-z])([A-Z]{2,}[0-9]*[A-Z]*)", full_text):
            acronym_hits.append(m.group(1))

        # Bracket-quoted key phrases 【驱动事件：XXX】
        bracket_hits: list[str] = []
        for m in re.finditer(r"【(.+?)】", full_text):
            inner = m.group(1)
            inner = re.sub(r"^(驱动事件|新题材更新)[：:]", "", inner)
            for chunk in re.split(r"[：:，,、]", inner):
                chunk = chunk.strip()
                if len(chunk) >= 3:
                    bracket_hits.append(chunk)

        # Technical nouns with suffixes
        tech_hits: list[str] = []
        for m in re.finditer(
            r"[\u4e00-\u9fff]{2,6}(?:线|层|制程|电阻|读写|量产|生产|验证)",
            full_text,
        ):
            raw = _trim_fn_prefix(m.group(0))
            if len(raw) >= 3:
                tech_hits.append(raw)
        tech_hits = _dedup(tech_hits)

        # Acronym-heavy tech terms (NAND, HBM, DRAM, HBM4E, etc.)
        acronym_hits = re.findall(
            r"\b([A-Z]{2,}[0-9]*[A-Z]*)\b", full_text,
        )

        # Bracket-quoted key phrases 【驱动事件：XXX】
        bracket_hits: list[str] = []
        for m in re.finditer(r"【(.+?)】", full_text):
            inner = m.group(1)
            inner = re.sub(r"^(驱动事件|新题材更新)[：:]", "", inner)
            for chunk in re.split(r"[：:，,、]", inner):
                chunk = chunk.strip()
                if len(chunk) >= 3:
                    bracket_hits.append(chunk)

        # Technical nouns with specific suffixes
        tech_hits = re.findall(
            r"([\u4e00-\u9fff]{2,6}(?:线|层|制程|电阻|读写|速度|量产|生产))",
            full_text,
        )

        # ── Build term hierarchies ──
        must_terms = _dedup([subject_name, *name_parts])[:6]
        strong_terms = _dedup([
            *name_parts, *company_hits, *product_hits,
            *acronym_hits, *bracket_hits, *tech_hits,
        ])[:16]

        # Weak: meaningful 3-10 char Chinese clauses (split by punctuation, not
        # sliding-window, to avoid fragment noise like "海力士使"/"用钼材料").
        clauses = re.split(r"[，,、。；：:！!？?\s]+", full_text)
        clause_terms = [
            c.strip() for c in clauses
            if 3 <= len(c.strip()) <= 10 and not c.strip().startswith(("《", "》"))
        ]
        weak_candidates = _dedup([*clause_terms, *product_hits, *tech_hits])
        strong_set = set(strong_terms) | set(must_terms)
        weak_terms = [
            t for t in weak_candidates
            if t not in strong_set and len(t) >= 3
        ][:24]

        return {
            "must": must_terms,
            "strong": strong_terms,
            "weak": weak_terms,
            "not": [],
        }

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

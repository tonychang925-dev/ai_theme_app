"""Phase 5: New-chain realtime stack manager.

Manages start/stop/status of the realtime pipeline:
  - AkShare realtime collector (DEPRECATED since Phase 4E, disabled by default)
    Legacy mode writes stream:news:raw:legacy only.
    Formal raw stream producer is RealTimeNewsCollector (database_service/streams/).
  - raw_news_services (NewsStreamHandler + NewsStreamProcessor)
  - phase0_decision_services (ThemeProcessor + DecisionExecutor)
  - pre-market brief minimal rebuild loop
  - Intel Stream Producer + Intel Collection Pipeline

Explicitly does NOT start: frontend_bff:8003, old matcher,
old run_realtime_stack.sh.

Environment is frozen to Phase 4.7 baseline (THEME_PROFILE_VERSION=v2 etc.).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]

# ── Phase 4.7 baseline environment ────────────────────────────────

BASELINE_ENV = {
    "THEME_PROFILE_VERSION": "v2",
    "THEME_PROFILE_V2_STATUS": "accepted_candidate",
    "THEME_PROFILE_V2_FALLBACK_TO_V1": "true",
    "THEME_PROFILE_V2_REQUIRE_LOADED": "true",
    "THEME_PROFILE_CACHE_TTL_SECONDS": "300",
    "THEME_MATCH_LLM_JUDGE_MODE": "auto",
    "THEME_PROCESSOR_STRUCTURED_CONCURRENCY": "2",
    "THEME_MATCH_ENABLE_EVENT_PROFILE_LLM": "false",
    "DB_TYPE": "postgresql",
    # 消除 macOS fork 子进程时的 tokenizers Rayon 线程池警告
    # 实际 ML 推理走 llama_cpp，不依赖 tokenizers 并行
    "TOKENIZERS_PARALLELISM": "false",
}

# ── Redis streams to monitor ───────────────────────────────────────

MONITOR_STREAMS = [
    "stream:news:raw",
    "stream:events:structured",
    "stream:events:decision",
]

REDIS_STREAM_METRIC_KEYS = [
    "length",
    "groups",
    "last-generated-id",
    "first-entry",
    "last-entry",
]


@dataclass
class RealtimeStackState:
    running: bool = False
    started_at: str | None = None
    pid: int | None = None
    akshare_pid: int | None = None
    akshare_collector_enabled: bool = False
    akshare_legacy_mode: bool = False
    raw_news_pid: int | None = None
    decision_pid: int | None = None
    rebuild_pid: int | None = None
    intel_producer_pid: int | None = None
    intel_collection_pid: int | None = None
    db_collector_pid: int | None = None  # Phase 4F
    db_collector_enabled: bool = False    # Phase 4F
    run_id: str = ""
    last_error: str = ""
    log_dir: str = ""
    status_source: str = "uninitialized"  # sps_live_pid_check | pidfile_restore | cleared

    def clear(self) -> None:
        self.running = False
        self.pid = None
        self.akshare_pid = None
        self.raw_news_pid = None
        self.decision_pid = None
        self.rebuild_pid = None
        self.intel_producer_pid = None
        self.intel_collection_pid = None
        self.db_collector_pid = None
        self.db_collector_enabled = False
        self.run_id = ""
        self.started_at = None
        self.last_error = ""
        self.status_source = "cleared"


class RealtimeStackManager:
    """Manage the Phase 4.7 new-chain realtime pipeline."""

    def __init__(
        self,
        *,
        python_cmd: str | None = None,
        redis_url: str = "redis://127.0.0.1:6379/0",
        write_db: str | None = None,
        log_dir: str | None = None,
    ) -> None:
        self._python_cmd = python_cmd or os.environ.get(
            "PYTHON_CMD", os.environ.get("CONDA_PYTHON_CMD", sys.executable)
        )
        self._redis_url = _normalize_redis_url(redis_url)
        # P1-C: 当前阶段硬锁 stock_data_test 单库，禁止读写分离或 stock_data 混用
        self._db_name = write_db or os.environ.get("PG_DATABASE") or "stock_data_test"
        if self._db_name != "stock_data_test":
            raise RuntimeError(
                f"RealtimeStackManager: 当前阶段只允许使用 stock_data_test, "
                f"got write_db={write_db}, PG_DATABASE={os.environ.get('PG_DATABASE')}. "
                f"设置 PG_DATABASE=stock_data_test 并移除 write_db 参数。"
            )
        self._log_dir = Path(
            log_dir or os.environ.get("REALTIME_LOG_DIR", str(ROOT / "logs" / "realtime"))
        )
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._state = RealtimeStackState()
        self._akshare_process: asyncio.subprocess.Process | None = None
        self._raw_process: asyncio.subprocess.Process | None = None
        self._decision_process: asyncio.subprocess.Process | None = None
        self._rebuild_process: asyncio.subprocess.Process | None = None
        self._intel_producer_process: asyncio.subprocess.Process | None = None
        self._intel_collection_process: asyncio.subprocess.Process | None = None
        self._stream_services_process: asyncio.subprocess.Process | None = None  # Phase 4E: RealTimeNewsCollector
        self._lock = asyncio.Lock()
        self._refresh_observed_state()

    # ── Public API ─────────────────────────────────────────────────

    async def start(self) -> dict[str, Any]:
        """Start the new-chain realtime stack.  Idempotent."""
        async with self._lock:
            self._refresh_observed_state()
            if self._state.running:
                return {"ok": True, "status": "already_running", "detail": self.status_sync()}

            run_id = f"realtime_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

            # P1-C-pre: start 前 Redis group 诊断
            group_diag = await self._diagnose_redis_groups()
            logger.warning("[REDIS_DIAG] %s", json.dumps(group_diag, ensure_ascii=False))
            if group_diag.get("alerts"):
                for alert in group_diag["alerts"]:
                    logger.warning("[REDIS_DIAG_ALERT] %s", alert)

            # P1-C1: orphan sweep — 启动前检查旧 pidfile
            orphans = await self._sweep_orphans()
            if orphans:
                logger.warning("[ORPHAN_SWEEP] found %d orphans: %s", len(orphans), json.dumps(orphans))
                # P1-C1: auto-clean orphans from pidfile before start
                await self.cleanup_orphans()

            # P1-C1: pidfile 目录。
            # 默认不再把实时采集子进程绑定到 SPS PID；SPS 重启不应静默停止实时采集。
            # 需要旧 watchdog 行为时显式设置 REALTIME_CHILD_WATCH_PARENT=true。
            watch_parent = os.environ.get("REALTIME_CHILD_WATCH_PARENT", "false").lower() in ("1", "true", "yes", "on")
            parent_pid = os.getpid() if watch_parent else 0
            runtime_dir = self._log_dir / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            pidfile_path = runtime_dir / "realtime_stack.json"
            pidfile_path.write_text(json.dumps({
                "run_id": run_id, "parent_pid": parent_pid,
                "manager_pid": os.getpid(),
                "watch_parent": watch_parent,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "db": self._db_name,
            }, ensure_ascii=False, indent=2))

            env = self._build_env(run_id, parent_pid)
            akshare_log = self._log_dir / f"akshare_{run_id}.log"
            raw_log = self._log_dir / f"raw_news_{run_id}.log"
            decision_log = self._log_dir / f"decision_{run_id}.log"
            rebuild_log = self._log_dir / f"brief_rebuild_{run_id}.log"
            intel_log = self._log_dir / f"intel_producer_{run_id}.log"
            intel_collection_log = self._log_dir / f"intel_collection_{run_id}.log"
            db_collector_log = self._log_dir / f"db_collector_{run_id}.log"          # Phase 4F
            akshare_status = self._log_dir / f"akshare_{run_id}.status.json"
            akshare_skip_log = self._log_dir / f"akshare_{run_id}.prefilter_skipped.jsonl"
            rebuild_status = self._log_dir / f"brief_rebuild_{run_id}.status.json"
            intel_status = self._log_dir / f"intel_producer_{run_id}.status.json"
            intel_collection_status = self._log_dir / f"intel_collection_{run_id}.status.json"
            db_collector_status = self._log_dir / f"db_collector_{run_id}.status.json"  # Phase 4F

            try:
                # raw_news/phase0 use REALTIME_PARENT_PID env var for watchdog (no --parent-pid CLI arg)
                self._raw_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "evaluate_service/e2e/pre_market_brief/run_raw_news_services.py"),
                    "--db-name", self._db_name,
                    "--run-id", run_id,
                    "--redis-url", self._redis_url,
                    "--batch-size", os.environ.get("REALTIME_RAW_NEWS_BATCH_SIZE", "10"),
                    "--block-time", os.environ.get("REALTIME_RAW_NEWS_BLOCK_MS", "5000"),
                    "--storage-concurrency", os.environ.get("REALTIME_RAW_STORAGE_CONCURRENCY", "3"),
                    "--allow-production",
                    **_detached_child_kwargs(),
                    stdout=open(raw_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )
                self._decision_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "evaluate_service/e2e/pre_market_brief/run_phase0_decision_services.py"),
                    "--db-name", self._db_name,
                    "--run-id", run_id,
                    "--redis-url", self._redis_url,
                    "--allow-production",
                    **_detached_child_kwargs(),
                    stdout=open(decision_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )

                # P1-C2-fix: group ready gate — 等待 critical groups 就绪
                if not await self._wait_for_realtime_groups(run_id, timeout=45):
                    logger.error("realtime critical groups not ready within 45s — continuing but group health degraded")
                    # Don't kill processes — they may still be initializing

                # Phase 4E: AkShare collector gating
                _akshare_enabled = os.environ.get("ENABLE_AKSHARE_REALTIME_COLLECTOR", "false").lower() == "true"
                _akshare_legacy = os.environ.get("ENABLE_LEGACY_AKSHARE_COLLECTOR", "false").lower() == "true"
                self._state.akshare_collector_enabled = _akshare_enabled
                self._state.akshare_legacy_mode = _akshare_legacy

                if _akshare_enabled or _akshare_legacy:
                    # Legacy mode: physically isolated stream, NEVER formal raw
                    _akshare_stream = "stream:news:raw:legacy" if _akshare_legacy else "stream:news:raw"
                    if _akshare_legacy:
                        logger.warning(
                            "AkShare LEGACY mode: writing to %s ONLY, NOT to stream:news:raw",
                            _akshare_stream,
                        )

                    self._akshare_process = await asyncio.create_subprocess_exec(
                        self._python_cmd,
                        str(ROOT / "stock_processing_service/scripts/run_akshare_realtime_news_collector.py"),
                        "--redis-url", self._redis_url,
                        "--stream", _akshare_stream,
                        "--run-id", run_id,
                        "--poll-interval-seconds", os.environ.get("AKSHARE_REALTIME_POLL_SECONDS", "180"),
                        "--lookback-minutes", os.environ.get("AKSHARE_REALTIME_LOOKBACK_MINUTES", "180"),
                        "--status-path", str(akshare_status),
                        "--prefilter-skip-log", str(akshare_skip_log),
                        *(["--parent-pid", str(parent_pid)] if parent_pid else []),
                        **_detached_child_kwargs(),
                        stdout=open(akshare_log, "w"),
                        stderr=asyncio.subprocess.STDOUT,
                        env=env,
                    )
                    logger.info(
                        "AkShare collector subprocess started: pid=%d stream=%s legacy=%s",
                        self._akshare_process.pid,
                        _akshare_stream,
                        _akshare_legacy,
                    )
                else:
                    logger.info(
                        "AkShare collector DISABLED (ENABLE_AKSHARE_REALTIME_COLLECTOR=false, "
                        "ENABLE_LEGACY_AKSHARE_COLLECTOR=false) — "
                        "RealTimeNewsCollector is the sole raw stream producer"
                    )
                    self._akshare_process = None

                # Phase 4F: DB RealTimeNewsCollector — 唯一正式新闻采集入口
                self._state.db_collector_enabled = os.environ.get("ENABLE_DB_REALTIME_COLLECTOR", "true").lower() != "false"
                if self._state.db_collector_enabled:
                    self._db_collector_process = await asyncio.create_subprocess_exec(
                        self._python_cmd,
                        str(ROOT / "database_service/streams/run_realtime_news_collector.py"),
                        "--redis-url", self._redis_url,
                        "--db-name", self._db_name,
                        "--run-id", run_id,
                        "--collection-interval",
                        os.environ.get("DB_COLLECTOR_INTERVAL_SECONDS", "300"),
                        "--stream-maxlen",
                        os.environ.get("REALTIME_NEWS_RAW_STREAM_MAXLEN", "50000"),
                        "--status-path", str(db_collector_status),
                        *(["--parent-pid", str(parent_pid)] if parent_pid else []),
                        **_detached_child_kwargs(),
                        stdout=open(db_collector_log, "w"),
                        stderr=asyncio.subprocess.STDOUT,
                        env=env,
                    )
                    self._state.db_collector_pid = self._db_collector_process.pid
                    logger.info(
                        "DB RealTimeNewsCollector started: pid=%d run_id=%s (Phase 4F)",
                        self._db_collector_process.pid, run_id,
                    )
                else:
                    logger.warning("DB RealTimeNewsCollector DISABLED (ENABLE_DB_REALTIME_COLLECTOR=false)")
                    self._db_collector_process = None
                    self._state.db_collector_pid = None

                self._rebuild_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "stock_processing_service/scripts/run_pre_market_brief_rebuild_loop.py"),
                    "--interval-seconds", os.environ.get("PRE_MARKET_BRIEF_REALTIME_REBUILD_SECONDS", "300"),
                    "--source", "db_first",
                    "--limit", os.environ.get("PRE_MARKET_BRIEF_REALTIME_LIMIT", "200"),
                    "--status-path", str(rebuild_status),
                    *(["--parent-pid", str(parent_pid)] if parent_pid else []),
                    **_detached_child_kwargs(),
                    stdout=open(rebuild_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )
                # P0-E: Intel Stream Producer — 周期性投递 pending 公告到 stream:events:structured
                self._intel_producer_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "stock_processing_service/scripts/run_intel_stream_producer.py"),
                    "--db-name", self._db_name,
                    "--redis-url", self._redis_url,
                    "--run-id", run_id,
                    "--poll-interval-seconds", os.environ.get("INTEL_PRODUCER_POLL_SECONDS", "30"),
                    "--batch-size", os.environ.get("INTEL_PRODUCER_BATCH_SIZE", "50"),
                    "--status-path", str(intel_status),
                    *(["--parent-pid", str(parent_pid)] if parent_pid else []),
                    **_detached_child_kwargs(),
                    stdout=open(intel_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )
                # P0-E: Intel Collection Pipeline (Stages 1-3) — CNINFO采集+入库+LLM结构化
                self._intel_collection_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "stock_processing_service/scripts/run_intel_collection_pipeline.py"),
                    "--db-name", self._db_name,
                    "--run-id", run_id,
                    "--poll-interval-seconds", os.environ.get("INTEL_COLLECTION_POLL_SECONDS", "600"),
                    "--days-back", os.environ.get("INTEL_COLLECTION_DAYS_BACK", "1"),
                    "--max-pages", os.environ.get("INTEL_COLLECTION_MAX_PAGES", "5"),
                    "--extraction-limit", os.environ.get("INTEL_COLLECTION_EXTRACTION_LIMIT", "20"),
                    "--status-path", str(intel_collection_status),
                    *(["--parent-pid", str(parent_pid)] if parent_pid else []),
                    **_detached_child_kwargs(),
                    stdout=open(intel_collection_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )

                # Brief warmup — give subprocesses time to start
                await asyncio.sleep(1)

                # P1-C1: write pidfiles for lifecycle tracking
                if self._akshare_process is not None:
                    _write_pidfile(runtime_dir / f"akshare_{run_id}.pid", self._akshare_process.pid)
                _write_pidfile(runtime_dir / f"raw_news_{run_id}.pid", self._raw_process.pid)
                _write_pidfile(runtime_dir / f"decision_{run_id}.pid", self._decision_process.pid)
                _write_pidfile(runtime_dir / f"rebuild_{run_id}.pid", self._rebuild_process.pid)
                _write_pidfile(runtime_dir / f"intel_producer_{run_id}.pid", self._intel_producer_process.pid)
                _write_pidfile(runtime_dir / f"intel_collection_{run_id}.pid", self._intel_collection_process.pid)
                if self._db_collector_process is not None:
                    _write_pidfile(runtime_dir / f"db_collector_{run_id}.pid", self._db_collector_process.pid)

                self._state.running = True
                self._state.status_source = "sps_live_pid_check"
                self._state.started_at = datetime.now(timezone.utc).isoformat()
                self._state.pid = os.getpid()
                self._state.akshare_pid = self._akshare_process.pid if self._akshare_process else None
                self._state.raw_news_pid = self._raw_process.pid
                self._state.decision_pid = self._decision_process.pid
                self._state.rebuild_pid = self._rebuild_process.pid
                self._state.intel_producer_pid = self._intel_producer_process.pid
                self._state.intel_collection_pid = self._intel_collection_process.pid
                self._state.run_id = run_id
                self._state.last_error = ""
                self._state.log_dir = str(self._log_dir)

                logger.info(
                    "realtime stack started: run_id=%s db_collector_pid=%s akshare_pid=%s raw_pid=%s decision_pid=%s rebuild_pid=%s intel_pid=%s intel_collection_pid=%s",
                    run_id,
                    self._state.db_collector_pid or "disabled",
                    self._state.akshare_pid or "disabled",
                    self._raw_process.pid,
                    self._decision_process.pid,
                    self._rebuild_process.pid,
                    self._intel_producer_process.pid,
                    self._intel_collection_process.pid,
                )
                return {"ok": True, "status": "started", "detail": self.status_sync()}

            except Exception as exc:
                self._state.last_error = str(exc)
                await self._cleanup_processes()
                logger.exception("realtime stack start failed")
                return {"ok": False, "status": "error", "error": str(exc)}

    async def stop(self) -> dict[str, Any]:
        """停止实时 pipeline：SIGTERM → wait 1.5s → SIGKILL → wait 0.5s → verify → 清理 pidfile → 清空 state。"""
        async with self._lock:
            self._refresh_observed_state()

            if not self._state.running:
                self._cleanup_runtime_files()
                self._state.clear()
                return {
                    "ok": True,
                    "status": "not_running",
                    "killed": [],
                    "alive_after": [],
                    "detail": self.status_sync(),
                }

            targets = self._runtime_pids()
            killed: list[int] = []
            errors: list[dict[str, Any]] = []

            for pid in sorted(targets):
                try:
                    os.kill(pid, signal.SIGTERM)
                    killed.append(pid)
                except ProcessLookupError:
                    pass
                except PermissionError as exc:
                    errors.append({"pid": pid, "error": str(exc)})

            await asyncio.sleep(1.5)

            for pid in sorted(targets):
                if _pid_alive(pid):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    except PermissionError as exc:
                        errors.append({"pid": pid, "error": str(exc)})

            await asyncio.sleep(0.5)

            alive_after = [pid for pid in sorted(targets) if _pid_alive(pid)]

            if alive_after:
                self._state.last_error = f"failed to stop pids: {alive_after}"
                return {
                    "ok": False,
                    "status": "partial_stop",
                    "killed": killed,
                    "alive_after": alive_after,
                    "errors": errors,
                    "detail": self.status_sync(),
                }

            self._cleanup_runtime_files()
            self._state.clear()
            logger.info("realtime stack stopped")

            return {
                "ok": True,
                "status": "stopped",
                "killed": killed,
                "alive_after": [],
                "errors": errors,
                "detail": self.status_sync(),
            }

    def _cleanup_runtime_files(self) -> None:
        """移除 runtime pidfile 目录下的所有 pid 文件和 stack.json。"""
        runtime_dir = self._log_dir / "runtime"
        if not runtime_dir.exists():
            return
        for f in runtime_dir.glob("*.pid"):
            try:
                f.unlink()
            except OSError:
                pass
        stack_json = runtime_dir / "realtime_stack.json"
        try:
            stack_json.unlink()
        except OSError:
            pass

    async def status(self) -> dict[str, Any]:
        """Return current stack status including Redis stream metrics."""
        self._refresh_observed_state()
        base = self.status_sync()

        # Try to enrich with Redis stream info
        try:
            import redis.asyncio as aioredis
            r = aioredis.Redis.from_url(self._redis_url, decode_responses=True)
            stream_info: dict[str, Any] = {}
            for stream_name in MONITOR_STREAMS:
                try:
                    info = await r.xinfo_stream(stream_name)
                    stream_info[stream_name] = {
                        "length": info.get("length", 0),
                        "groups": info.get("groups", 0),
                    }
                except Exception:
                    stream_info[stream_name] = {"length": -1, "groups": -1}
            # DB collector / Qwen status from latest status file
            # Phase 6A: prefer file matching current run_id, avoid stale files with later alphabetical names
            try:
                import glob as _glob, json as _json, os as _os2
                status_files = sorted(_glob.glob(str(self._log_dir / "db_collector_realtime_*.status.json")))
                matched = [f for f in status_files if self._state.run_id and self._state.run_id in _os2.path.basename(f)]
                target_file = matched[-1] if matched else (status_files[-1] if status_files else None)
                if target_file:
                    with open(target_file) as f:
                        dc = _json.load(f)
                    base["qwen_dedup_ready"] = dc.get("qwen_dedup_ready", False)
                    base["qwen_dedup_calls"] = dc.get("qwen_dedup_call_count", 0)
                    base["semantic_dedup_count"] = dc.get("semantic_dedup_batch_count", 0)
                    base["prefilter_skipped"] = dc.get("news_prefilter_skipped", 0)        # LLM低质量skip
                    base["news_dedup_skipped"] = dc.get("news_dedup_skipped", 0)           # 硬去重skip
                    base["news_published_total"] = dc.get("news_published_total", 0)        # 最终feed通过
                    base["hard_protect_count"] = dc.get("hard_protect_count", 0)            # 白名单保护
            except Exception:
                base["qwen_dedup_ready"] = False

            # pending / dead letter
            try:
                pending_info = await r.xinfo_stream("stream:events:pending")
                base["pending_count"] = pending_info.get("length", 0)
            except Exception:
                base["pending_count"] = -1
            try:
                dl_info = await r.xinfo_stream("stream:dead:letter")
                base["dead_letter_count"] = dl_info.get("length", 0)
            except Exception:
                base["dead_letter_count"] = -1
            try:
                review_info = await r.xinfo_stream("stream:events:decision")
                base["decision_stream_count"] = review_info.get("length", 0)
            except Exception:
                base["decision_stream_count"] = -1
            base["redis_streams"] = stream_info
            await r.aclose()
        except Exception as exc:
            base["redis_error"] = str(exc)

        base["akshare_collector"] = self._read_status_file("akshare")
        base["brief_rebuild"] = self._read_status_file("brief_rebuild")
        base["intel_producer"] = self._read_status_file("intel_producer")
        base["intel_collection"] = self._read_status_file("intel_collection")
        base["realtime_groups"] = await self._read_realtime_groups()
        base["review_queue_count"] = await self._read_review_queue_count()

        return base

    def status_sync(self) -> dict[str, Any]:
        """Synchronous subset of status (no Redis)."""
        self._refresh_observed_state()
        # running_verified 必须来自 live PID 验证结果，不能仅 mirror self._state.running
        _verified = bool(self._state.raw_news_pid or self._state.decision_pid)
        return {
            "running": self._state.running,
            "running_verified": _verified,
            "status_source": self._state.status_source,
            "run_id": self._state.run_id,
            "started_at": self._state.started_at,
            # Phase 4E: AkShare collector status
            "akshare_pid": self._state.akshare_pid,
            "akshare_collector_enabled": self._state.akshare_collector_enabled,
            "akshare_legacy_mode": self._state.akshare_legacy_mode,
            "raw_news_pid": self._state.raw_news_pid,
            "decision_pid": self._state.decision_pid,
            "rebuild_pid": self._state.rebuild_pid,
            "intel_producer_pid": self._state.intel_producer_pid,
            "intel_collection_pid": self._state.intel_collection_pid,
            # Phase 4F: DB RealTimeNewsCollector
            "db_collector_pid": self._state.db_collector_pid,
            "db_collector_enabled": self._state.db_collector_enabled,
            "active_collector": "RealTimeNewsCollector" if self._state.db_collector_enabled else "none",
            "collector_version": "phase4e",
            "log_dir": self._state.log_dir,
            "last_error": self._state.last_error,
            "profile_version": BASELINE_ENV.get("THEME_PROFILE_VERSION", "v2"),
            "profile_status": BASELINE_ENV.get("THEME_PROFILE_V2_STATUS", "draft"),
            "profile_fallback": BASELINE_ENV.get("THEME_PROFILE_V2_FALLBACK_TO_V1", "true"),
            "llm_judge_mode": BASELINE_ENV.get("THEME_MATCH_LLM_JUDGE_MODE", "auto"),
            "structured_concurrency": int(BASELINE_ENV.get("THEME_PROCESSOR_STRUCTURED_CONCURRENCY", "2")),
            "write_db": self._db_name,
            "read_db": self._db_name,
            "same_db": True,
        }

    # ── Internal ───────────────────────────────────────────────────

    def _refresh_observed_state(self) -> None:
        """每次调用都实时验证 pidfile 和 PID 存活状态。

        不缓存 stale state——如果 pidfile 不存在或核心 PID 已死，立即清空状态。
        SPS 是实时采集 pipeline 的唯一生命周期 Owner，状态必须以 live check 为准。
        """

        runtime_dir = self._log_dir / "runtime"
        stack_json = runtime_dir / "realtime_stack.json"

        if not stack_json.exists():
            self._state.clear()
            return

        try:
            meta = json.loads(stack_json.read_text(encoding="utf-8"))
        except Exception:
            self._state.clear()
            return

        run_id = str(meta.get("run_id") or "")
        if not run_id:
            self._state.clear()
            return

        def _read_live_pid(prefix: str) -> int | None:
            path = runtime_dir / f"{prefix}_{run_id}.pid"
            try:
                pid = int(path.read_text().strip())
            except Exception:
                return None
            return pid if _pid_alive(pid) else None

        raw_pid = _read_live_pid("raw_news")
        decision_pid = _read_live_pid("decision")

        # 核心进程 raw_news + decision：至少一个活着才算 running
        if not raw_pid and not decision_pid:
            self._state.clear()
            return

        self._state.running = True
        self._state.status_source = "sps_live_pid_check"
        self._state.started_at = str(meta.get("started_at") or "")
        self._state.pid = int(meta.get("manager_pid") or meta.get("parent_pid") or 0) or None
        self._state.akshare_pid = _read_live_pid("akshare")
        self._state.raw_news_pid = raw_pid
        self._state.decision_pid = decision_pid
        self._state.rebuild_pid = _read_live_pid("rebuild")
        self._state.intel_producer_pid = _read_live_pid("intel_producer")
        self._state.intel_collection_pid = _read_live_pid("intel_collection")
        self._state.db_collector_pid = _read_live_pid("db_collector")
        self._state.db_collector_enabled = bool(self._state.db_collector_pid)
        self._state.run_id = run_id
        self._state.log_dir = str(self._log_dir)
        self._state.last_error = ""

    def _build_env(self, run_id: str, parent_pid: int = 0) -> dict[str, str]:
        env = os.environ.copy()
        env.update(BASELINE_ENV)
        # P1-C: 统一单库 stock_data_test — 所有子进程强制继承
        env["PG_DATABASE"] = self._db_name
        env["DB_NAME"] = self._db_name
        env["READ_PG_DATABASE"] = self._db_name
        env["POSTGRES_DATABASE"] = self._db_name
        env["REDIS_URL"] = self._redis_url
        env["RUN_ID"] = run_id
        env["REALTIME_PARENT_PID"] = str(parent_pid)
        return env

    async def _sweep_orphans(self) -> list[dict[str, Any]]:
        """P1-C1: 扫描旧 pidfile，检测 orphan 进程。"""
        orphans: list[dict[str, Any]] = []
        runtime_dir = self._log_dir / "runtime"
        if not runtime_dir.exists():
            return orphans
        for pidfile in runtime_dir.glob("*.pid"):
            try:
                old_pid = int(pidfile.read_text().strip())
                if pidfile.name.startswith("akshare_"):
                    name = "akshare"
                elif pidfile.name.startswith("raw_news_"):
                    name = "raw_news"
                elif pidfile.name.startswith("decision_"):
                    name = "decision"
                elif pidfile.name.startswith("rebuild_"):
                    name = "rebuild"
                elif pidfile.name.startswith("intel_producer_"):
                    name = "intel_producer"
                elif pidfile.name.startswith("intel_collection_"):
                    name = "intel_collection"
                elif pidfile.name.startswith("db_collector_"):
                    name = "db_collector"
                else:
                    name = pidfile.stem
                alive = _pid_alive(old_pid)
                if alive:
                    orphans.append({"name": name, "pid": old_pid, "pidfile": str(pidfile), "alive": True})
            except (ValueError, OSError):
                pass
        return orphans

    GATE_CRITICAL = {"theme_processor_realtime", "decision_executor_realtime"}

    async def _wait_for_realtime_groups(self, run_id: str, timeout: int = 30) -> bool:
        """P1-C2-fix: 等待 critical protected groups 就绪（structured + decision 流）。"""
        expected = {
            "stream:events:structured": "theme_processor_realtime",
            "stream:events:decision": "decision_executor_realtime",
            "stream:news:raw": "news_storage_realtime",
            "stream:events:normal": "news_processor_realtime",
        }
        deadline = time.monotonic() + timeout
        last_missing: set[str] = set(expected.values())
        while time.monotonic() < deadline:
            missing: set[str] = set()
            try:
                import redis.asyncio as aioredis
                r = aioredis.Redis.from_url(self._redis_url, decode_responses=True)
                try:
                    for stream, group in expected.items():
                        try:
                            info = await r.xinfo_groups(stream)
                            names = {g.get("name", "") for g in info}
                            if group not in names:
                                missing.add(group)
                        except Exception:
                            missing.add(group)
                finally:
                    await r.aclose()
            except Exception:
                missing = set(expected.values())

            critical_missing = missing & self.GATE_CRITICAL
            if not critical_missing:
                logger.info("realtime critical groups ready (advisory missing: %s)", missing)
                return True
            if critical_missing != (last_missing & self.GATE_CRITICAL):
                logger.warning("waiting for realtime groups: critical_missing=%s remaining=%.0fs", critical_missing, deadline - time.monotonic())
            last_missing = missing
            await asyncio.sleep(2)
        logger.error("realtime groups timeout: missing=%s", last_missing)
        return False

    async def _diagnose_redis_groups(self) -> dict[str, Any]:
        """P1-C-pre: 启动前 Redis group 体检。"""
        protected = {
            "news_storage_realtime", "news_processor_realtime",
            "theme_processor_realtime", "decision_executor_realtime",
        }
        result: dict[str, Any] = {"streams": {}, "alerts": []}
        try:
            import redis.asyncio as aioredis
            r = aioredis.Redis.from_url(self._redis_url, decode_responses=True)
            for stream in ["stream:news:raw", "stream:events:structured", "stream:events:decision"]:
                info: dict[str, Any] = {"groups": [], "group_count": 0}
                try:
                    groups = await r.xinfo_groups(stream)
                    for g in groups:
                        gname = g.get("name", "")
                        consumers = int(g.get("consumers", 0))
                        pending = int(g.get("pending", 0))
                        info["groups"].append({
                            "name": gname, "consumers": consumers,
                            "pending": pending, "protected": gname in protected,
                        })
                        if consumers == 0 and pending == 0 and gname not in protected:
                            info["groups"][-1]["zombie"] = True
                    info["group_count"] = len(info["groups"])
                    zombie_count = sum(1 for g in info["groups"] if g.get("zombie"))
                    if zombie_count > 0:
                        result["alerts"].append(
                            f"{stream}: {zombie_count} zombie groups (0 consumers, 0 pending)"
                        )
                    missing = protected - {g["name"] for g in info["groups"]}
                    if missing:
                        result["alerts"].append(f"{stream}: missing protected groups: {missing}")
                except Exception:
                    info["error"] = "unavailable"
                result["streams"][stream] = info
            await r.aclose()
        except Exception as exc:
            result["error"] = str(exc)
        return result

    async def _cleanup_processes(self) -> None:
        pid_targets = self._runtime_pids()
        for proc in [self._akshare_process, self._db_collector_process, self._raw_process, self._decision_process, self._rebuild_process, self._intel_producer_process, self._intel_collection_process]:
            if proc is None or proc.returncode is not None:
                continue
            pid_targets.add(proc.pid)
            try:
                proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
        for pid in sorted(pid_targets):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                logger.warning("no permission to terminate realtime child pid=%s", pid)
        # Give processes a moment to exit
        await asyncio.sleep(1)
        for proc in [self._akshare_process, self._db_collector_process, self._raw_process, self._decision_process, self._rebuild_process, self._intel_producer_process, self._intel_collection_process]:
            if proc is None or proc.returncode is not None:
                continue
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        for pid in sorted(pid_targets):
            if not _pid_alive(pid):
                continue
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError:
                logger.warning("no permission to kill realtime child pid=%s", pid)
        self._akshare_process = None
        self._raw_process = None
        self._decision_process = None
        self._rebuild_process = None
        self._intel_producer_process = None
        self._db_collector_process = None
        self._intel_collection_process = None
        self._state.clear()
        # P1-C1: clean pidfiles + old status files
        runtime_dir = self._log_dir / "runtime"
        for pattern in ["akshare_*.pid", "db_collector_*.pid", "raw_news_*.pid", "decision_*.pid", "rebuild_*.pid", "intel_producer_*.pid", "intel_collection_*.pid"]:
            for pf in runtime_dir.glob(pattern):
                try: pf.unlink()
                except OSError: pass
        stack_json = runtime_dir / "realtime_stack.json"
        try: stack_json.unlink()
        except OSError: pass
        # Clean old status/log files from previous runs (keep current run_id)
        current_run = self._state.run_id
        if current_run:
            patterns_to_clean = [
                "akshare_*.status.json", "akshare_*.prefilter_skipped.jsonl",
                "brief_rebuild_*.status.json", "intel_producer_*.status.json", "intel_collection_*.status.json",
                "db_collector_*.status.json",
                "akshare_*.log", "raw_news_*.log", "decision_*.log", "db_collector_*.log",
                "brief_rebuild_*.log", "intel_producer_*.log", "intel_collection_*.log",
            ]
            for pattern in patterns_to_clean:
                for f in self._log_dir.glob(pattern):
                    if current_run not in f.name:
                        try: f.unlink()
                        except OSError: pass

    def _read_status_file(self, prefix: str) -> dict[str, Any]:
        if not self._state.run_id:
            return {}
        path = self._log_dir / f"{prefix}_{self._state.run_id}.status.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"error": str(exc)}

    async def _read_realtime_groups(self) -> dict[str, Any]:
        """P1-C2-fix: 读取四个 protected group 状态。"""
        expected = {
            "stream:events:structured": "theme_processor_realtime",
            "stream:events:decision": "decision_executor_realtime",
            "stream:news:raw": "news_storage_realtime",
            "stream:events:normal": "news_processor_realtime",
        }
        result: dict[str, Any] = {}
        try:
            import redis.asyncio as aioredis
            r = aioredis.Redis.from_url(self._redis_url, decode_responses=True)
            try:
                for stream, group in expected.items():
                    try:
                        info = await r.xinfo_groups(stream)
                        for g in info:
                            if g.get("name") == group:
                                result[group] = {
                                    "exists": True,
                                    "stream": stream,
                                    "consumers": int(g.get("consumers", 0)),
                                    "pending": int(g.get("pending", 0)),
                                    "last_delivered_id": g.get("last-delivered-id", ""),
                                }
                                break
                        if group not in result:
                            result[group] = {"exists": False, "stream": stream}
                    except Exception:
                        result[group] = {"exists": False, "stream": stream, "error": "stream_unavailable"}
            finally:
                await r.aclose()
        except Exception as exc:
            result["error"] = str(exc)
        return result

    async def _read_review_queue_count(self) -> int:
        try:
            import asyncpg

            conn = await asyncpg.connect(
                host=os.environ.get("PG_HOST", "localhost"),
                port=int(os.environ.get("PG_PORT", "5432")),
                database=self._db_name,
                user=os.environ.get("PG_USERNAME", "postgres"),
                password=os.environ.get("PG_PASSWORD", ""),
            )
            try:
                exists = await conn.fetchval("SELECT to_regclass('public.event_review_queue')::text")
                if not exists:
                    return 0
                return int(await conn.fetchval("SELECT count(*) FROM event_review_queue WHERE review_status = 'waiting'") or 0)
            finally:
                await conn.close()
        except Exception:
            return -1

    # ── P1-C1: orphan lifecycle ──────────────────────────────────────

    def _runtime_pids(self) -> set[int]:
        """返回当前 run_id 对应的存活 PID，不返回旧 run_id 的残留 pidfile。"""
        runtime_dir = self._log_dir / "runtime"
        run_id = self._state.run_id
        if not run_id:
            return set()
        prefixes = ["akshare", "db_collector", "raw_news", "decision", "rebuild", "intel_producer", "intel_collection"]
        pids: set[int] = set()
        for prefix in prefixes:
            pf = runtime_dir / f"{prefix}_{run_id}.pid"
            try:
                pid = int(pf.read_text().strip())
            except Exception:
                continue
            if _pid_alive(pid):
                pids.add(pid)
        return pids

    async def get_orphans(self) -> dict[str, Any]:
        orphans = await self._sweep_orphans()
        return {"orphans": orphans, "count": len(orphans)}

    async def cleanup_orphans(self) -> dict[str, Any]:
        """清理 pidfile 记录的本项目 realtime 子进程。只按 pidfile 杀，不按关键词全局 kill。"""
        runtime_dir = self._log_dir / "runtime"
        killed = []
        errors = []
        for pattern in ["akshare_*.pid", "db_collector_*.pid", "raw_news_*.pid", "decision_*.pid", "rebuild_*.pid", "intel_producer_*.pid", "intel_collection_*.pid"]:
            for pf in sorted(runtime_dir.glob(pattern)):
                try:
                    old_pid = int(pf.read_text().strip())
                    if _pid_alive(old_pid):
                        try:
                            os.kill(old_pid, signal.SIGTERM)
                            killed.append({"pid": old_pid, "pidfile": str(pf)})
                        except ProcessLookupError:
                            pf.unlink()
                        except Exception as exc:
                            errors.append({"pid": old_pid, "error": str(exc)})
                    else:
                        pf.unlink()
                except (ValueError, OSError):
                    try: pf.unlink()
                    except OSError: pass
        # Wait for processes to exit
        await asyncio.sleep(1)
        for entry in killed:
            if not _pid_alive(entry["pid"]):
                try: Path(entry["pidfile"]).unlink()
                except OSError: pass
            else:
                try:
                    os.kill(entry["pid"], signal.SIGKILL)
                    try: Path(entry["pidfile"]).unlink()
                    except OSError: pass
                except ProcessLookupError:
                    try: Path(entry["pidfile"]).unlink()
                    except OSError: pass
        stack_json = runtime_dir / "realtime_stack.json"
        try: stack_json.unlink()
        except OSError: pass
        return {"killed": len(killed), "errors": errors}


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _write_pidfile(path: Path, pid: int | None) -> None:
    if pid is not None:
        path.write_text(str(pid))


def _detached_child_kwargs() -> dict[str, Any]:
    """Start realtime children outside the SPS/screen session."""
    return {"start_new_session": True} if os.name == "posix" else {}


def _normalize_redis_url(url: str | None) -> str:
    v = (url or os.getenv("REDIS_URL") or "").strip().strip("'\"")
    if not v:
        v = "redis://127.0.0.1:6379/0"
    if not v.startswith(("redis://", "rediss://", "unix://")):
        raise RuntimeError(f"Invalid REDIS_URL: {v!r}")
    return v

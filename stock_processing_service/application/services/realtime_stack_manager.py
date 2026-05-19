"""Phase 5: New-chain realtime stack manager.

Manages start/stop/status of the stream-only realtime pipeline:
  - raw_news_services (NewsStreamHandler + NewsStreamProcessor)
  - phase0_decision_services (ThemeProcessor + DecisionExecutor)

Explicitly does NOT start: frontend_bff:8003, old collector, old matcher,
old run_realtime_stack.sh.

Environment is frozen to Phase 4.7 baseline (THEME_PROFILE_VERSION=v2 etc.).
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[4]

# ── Phase 4.7 baseline environment ────────────────────────────────

BASELINE_ENV = {
    "THEME_PROFILE_VERSION": "v2",
    "THEME_PROFILE_V2_STATUS": "draft",
    "THEME_PROFILE_V2_FALLBACK_TO_V1": "true",
    "THEME_PROFILE_V2_REQUIRE_LOADED": "true",
    "THEME_PROFILE_CACHE_TTL_SECONDS": "300",
    "THEME_MATCH_LLM_JUDGE_MODE": "auto",
    "THEME_PROCESSOR_STRUCTURED_CONCURRENCY": "2",
    "THEME_MATCH_ENABLE_EVENT_PROFILE_LLM": "false",
    "DB_TYPE": "postgresql",
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
    raw_news_pid: int | None = None
    decision_pid: int | None = None
    run_id: str = ""
    last_error: str = ""
    log_dir: str = ""


class RealtimeStackManager:
    """Manage the Phase 4.7 new-chain realtime pipeline."""

    def __init__(
        self,
        *,
        python_cmd: str | None = None,
        redis_url: str = "redis://127.0.0.1:6379/0",
        write_db: str = "stock_data",
        log_dir: str | None = None,
    ) -> None:
        self._python_cmd = python_cmd or os.environ.get(
            "PYTHON_CMD", os.environ.get("CONDA_PYTHON_CMD", "python")
        )
        self._redis_url = redis_url
        self._write_db = write_db
        self._log_dir = Path(
            log_dir or os.environ.get("REALTIME_LOG_DIR", str(ROOT / "logs" / "realtime"))
        )
        self._log_dir.mkdir(parents=True, exist_ok=True)

        self._state = RealtimeStackState()
        self._raw_process: asyncio.subprocess.Process | None = None
        self._decision_process: asyncio.subprocess.Process | None = None
        self._lock = asyncio.Lock()

    # ── Public API ─────────────────────────────────────────────────

    async def start(self) -> dict[str, Any]:
        """Start the new-chain realtime stack.  Idempotent."""
        async with self._lock:
            if self._state.running:
                return {"ok": True, "status": "already_running", "detail": self.status_sync()}

            run_id = f"realtime_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            env = self._build_env(run_id)
            raw_log = self._log_dir / f"raw_news_{run_id}.log"
            decision_log = self._log_dir / f"decision_{run_id}.log"

            try:
                self._raw_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "evaluate_service/e2e/pre_market_brief/run_raw_news_services.py"),
                    "--db-name", self._write_db,
                    "--run-id", run_id,
                    "--redis-url", self._redis_url,
                    "--allow-production",
                    stdout=open(raw_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )
                self._decision_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "evaluate_service/e2e/pre_market_brief/run_phase0_decision_services.py"),
                    "--db-name", self._write_db,
                    "--run-id", run_id,
                    "--redis-url", self._redis_url,
                    "--allow-production",
                    stdout=open(decision_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )

                # Brief warmup — give subprocesses time to start
                await asyncio.sleep(2)

                self._state.running = True
                self._state.started_at = datetime.now(timezone.utc).isoformat()
                self._state.pid = os.getpid()
                self._state.raw_news_pid = self._raw_process.pid
                self._state.decision_pid = self._decision_process.pid
                self._state.run_id = run_id
                self._state.last_error = ""
                self._state.log_dir = str(self._log_dir)

                logger.info("realtime stack started: run_id=%s raw_pid=%d decision_pid=%d",
                            run_id, self._raw_process.pid, self._decision_process.pid)
                return {"ok": True, "status": "started", "detail": self.status_sync()}

            except Exception as exc:
                self._state.last_error = str(exc)
                await self._cleanup_processes()
                logger.exception("realtime stack start failed")
                return {"ok": False, "status": "error", "error": str(exc)}

    async def stop(self) -> dict[str, Any]:
        """Gracefully stop the realtime stack."""
        async with self._lock:
            if not self._state.running:
                return {"ok": True, "status": "not_running"}

            await self._cleanup_processes()
            self._state.running = False
            logger.info("realtime stack stopped")
            return {"ok": True, "status": "stopped"}

    async def status(self) -> dict[str, Any]:
        """Return current stack status including Redis stream metrics."""
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
            base["redis_streams"] = stream_info
            await r.aclose()
        except Exception as exc:
            base["redis_error"] = str(exc)

        return base

    def status_sync(self) -> dict[str, Any]:
        """Synchronous subset of status (no Redis)."""
        return {
            "running": self._state.running,
            "run_id": self._state.run_id,
            "started_at": self._state.started_at,
            "raw_news_pid": self._state.raw_news_pid,
            "decision_pid": self._state.decision_pid,
            "log_dir": self._state.log_dir,
            "last_error": self._state.last_error,
            "profile_version": BASELINE_ENV.get("THEME_PROFILE_VERSION", "v2"),
            "profile_status": BASELINE_ENV.get("THEME_PROFILE_V2_STATUS", "draft"),
            "profile_fallback": BASELINE_ENV.get("THEME_PROFILE_V2_FALLBACK_TO_V1", "true"),
            "llm_judge_mode": BASELINE_ENV.get("THEME_MATCH_LLM_JUDGE_MODE", "auto"),
            "structured_concurrency": int(BASELINE_ENV.get("THEME_PROCESSOR_STRUCTURED_CONCURRENCY", "2")),
        }

    # ── Internal ───────────────────────────────────────────────────

    def _build_env(self, run_id: str) -> dict[str, str]:
        env = os.environ.copy()
        env.update(BASELINE_ENV)
        env["PG_DATABASE"] = self._write_db
        env["DB_NAME"] = self._write_db
        env["REPLAY_DB_NAME"] = self._write_db
        env["REDIS_URL"] = self._redis_url
        env["RUN_ID"] = run_id
        env["READ_PG_DATABASE"] = os.environ.get("READ_PG_DATABASE", "stock_data_test")
        return env

    async def _cleanup_processes(self) -> None:
        for proc in [self._raw_process, self._decision_process]:
            if proc is None or proc.returncode is not None:
                continue
            try:
                proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
        # Give processes a moment to exit
        await asyncio.sleep(1)
        for proc in [self._raw_process, self._decision_process]:
            if proc is None or proc.returncode is not None:
                continue
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        self._raw_process = None
        self._decision_process = None

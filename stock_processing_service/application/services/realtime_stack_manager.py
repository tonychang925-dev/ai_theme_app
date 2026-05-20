"""Phase 5: New-chain realtime stack manager.

Manages start/stop/status of the realtime pipeline:
  - akshare realtime collector (writes stream:news:raw)
  - raw_news_services (NewsStreamHandler + NewsStreamProcessor)
  - phase0_decision_services (ThemeProcessor + DecisionExecutor)
  - pre-market brief minimal rebuild loop

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
    raw_news_pid: int | None = None
    decision_pid: int | None = None
    rebuild_pid: int | None = None
    intel_producer_pid: int | None = None
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
        write_db: str | None = None,
        log_dir: str | None = None,
    ) -> None:
        self._python_cmd = python_cmd or os.environ.get(
            "PYTHON_CMD", os.environ.get("CONDA_PYTHON_CMD", sys.executable)
        )
        self._redis_url = redis_url
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
        self._lock = asyncio.Lock()

    # ── Public API ─────────────────────────────────────────────────

    async def start(self) -> dict[str, Any]:
        """Start the new-chain realtime stack.  Idempotent."""
        async with self._lock:
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

            # P1-C1: pidfile 目录
            parent_pid = os.getpid()
            runtime_dir = self._log_dir / "runtime"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            pidfile_path = runtime_dir / "realtime_stack.json"
            pidfile_path.write_text(json.dumps({
                "run_id": run_id, "parent_pid": parent_pid,
                "started_at": datetime.now(timezone.utc).isoformat(),
                "db": self._db_name,
            }, ensure_ascii=False, indent=2))

            env = self._build_env(run_id, parent_pid)
            akshare_log = self._log_dir / f"akshare_{run_id}.log"
            raw_log = self._log_dir / f"raw_news_{run_id}.log"
            decision_log = self._log_dir / f"decision_{run_id}.log"
            rebuild_log = self._log_dir / f"brief_rebuild_{run_id}.log"
            intel_log = self._log_dir / f"intel_producer_{run_id}.log"
            akshare_status = self._log_dir / f"akshare_{run_id}.status.json"
            akshare_skip_log = self._log_dir / f"akshare_{run_id}.prefilter_skipped.jsonl"
            rebuild_status = self._log_dir / f"brief_rebuild_{run_id}.status.json"
            intel_status = self._log_dir / f"intel_producer_{run_id}.status.json"

            try:
                # raw_news/phase0 use REALTIME_PARENT_PID env var for watchdog (no --parent-pid CLI arg)
                self._raw_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "evaluate_service/e2e/pre_market_brief/run_raw_news_services.py"),
                    "--db-name", self._db_name,
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
                    "--db-name", self._db_name,
                    "--run-id", run_id,
                    "--redis-url", self._redis_url,
                    "--allow-production",
                    stdout=open(decision_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )

                # P1-C2-fix: group ready gate — 等待 critical groups 就绪
                if not await self._wait_for_realtime_groups(run_id, timeout=45):
                    logger.error("realtime critical groups not ready within 45s — continuing but group health degraded")
                    # Don't kill processes — they may still be initializing

                self._akshare_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "stock_processing_service/scripts/run_akshare_realtime_news_collector.py"),
                    "--redis-url", self._redis_url,
                    "--stream", "stream:news:raw",
                    "--run-id", run_id,
                    "--poll-interval-seconds", os.environ.get("AKSHARE_REALTIME_POLL_SECONDS", "60"),
                    "--lookback-minutes", os.environ.get("AKSHARE_REALTIME_LOOKBACK_MINUTES", "180"),
                    "--status-path", str(akshare_status),
                    "--prefilter-skip-log", str(akshare_skip_log),
                    "--parent-pid", str(parent_pid),
                    stdout=open(akshare_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )
                self._rebuild_process = await asyncio.create_subprocess_exec(
                    self._python_cmd,
                    str(ROOT / "stock_processing_service/scripts/run_pre_market_brief_rebuild_loop.py"),
                    "--interval-seconds", os.environ.get("PRE_MARKET_BRIEF_REALTIME_REBUILD_SECONDS", "300"),
                    "--source", "db_first",
                    "--limit", os.environ.get("PRE_MARKET_BRIEF_REALTIME_LIMIT", "200"),
                    "--status-path", str(rebuild_status),
                    "--parent-pid", str(parent_pid),
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
                    "--parent-pid", str(parent_pid),
                    stdout=open(intel_log, "w"),
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )

                # Brief warmup — give subprocesses time to start
                await asyncio.sleep(1)

                # P1-C1: write pidfiles for lifecycle tracking
                _write_pidfile(runtime_dir / f"akshare_{run_id}.pid", self._akshare_process.pid)
                _write_pidfile(runtime_dir / f"raw_news_{run_id}.pid", self._raw_process.pid)
                _write_pidfile(runtime_dir / f"decision_{run_id}.pid", self._decision_process.pid)
                _write_pidfile(runtime_dir / f"rebuild_{run_id}.pid", self._rebuild_process.pid)
                _write_pidfile(runtime_dir / f"intel_producer_{run_id}.pid", self._intel_producer_process.pid)

                self._state.running = True
                self._state.started_at = datetime.now(timezone.utc).isoformat()
                self._state.pid = os.getpid()
                self._state.akshare_pid = self._akshare_process.pid
                self._state.raw_news_pid = self._raw_process.pid
                self._state.decision_pid = self._decision_process.pid
                self._state.rebuild_pid = self._rebuild_process.pid
                self._state.intel_producer_pid = self._intel_producer_process.pid
                self._state.run_id = run_id
                self._state.last_error = ""
                self._state.log_dir = str(self._log_dir)

                logger.info(
                    "realtime stack started: run_id=%s akshare_pid=%d raw_pid=%d decision_pid=%d rebuild_pid=%d intel_pid=%d",
                    run_id,
                    self._akshare_process.pid,
                    self._raw_process.pid,
                    self._decision_process.pid,
                    self._rebuild_process.pid,
                    self._intel_producer_process.pid,
                )
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
        base["realtime_groups"] = await self._read_realtime_groups()
        base["review_queue_count"] = await self._read_review_queue_count()

        return base

    def status_sync(self) -> dict[str, Any]:
        """Synchronous subset of status (no Redis)."""
        return {
            "running": self._state.running,
            "run_id": self._state.run_id,
            "started_at": self._state.started_at,
            "akshare_pid": self._state.akshare_pid,
            "raw_news_pid": self._state.raw_news_pid,
            "decision_pid": self._state.decision_pid,
            "rebuild_pid": self._state.rebuild_pid,
            "intel_producer_pid": self._state.intel_producer_pid,
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
        for proc in [self._akshare_process, self._raw_process, self._decision_process, self._rebuild_process, self._intel_producer_process]:
            if proc is None or proc.returncode is not None:
                continue
            try:
                proc.send_signal(signal.SIGTERM)
            except ProcessLookupError:
                pass
        # Give processes a moment to exit
        await asyncio.sleep(1)
        for proc in [self._akshare_process, self._raw_process, self._decision_process, self._rebuild_process, self._intel_producer_process]:
            if proc is None or proc.returncode is not None:
                continue
            try:
                proc.kill()
            except ProcessLookupError:
                pass
        self._akshare_process = None
        self._raw_process = None
        self._decision_process = None
        self._rebuild_process = None
        self._intel_producer_process = None
        self._state.akshare_pid = None
        self._state.raw_news_pid = None
        self._state.decision_pid = None
        self._state.rebuild_pid = None
        self._state.intel_producer_pid = None
        # P1-C1: clean pidfiles + old status files
        runtime_dir = self._log_dir / "runtime"
        for pattern in ["akshare_*.pid", "raw_news_*.pid", "decision_*.pid", "rebuild_*.pid", "intel_producer_*.pid"]:
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
                "brief_rebuild_*.status.json", "intel_producer_*.status.json",
                "akshare_*.log", "raw_news_*.log", "decision_*.log",
                "brief_rebuild_*.log", "intel_producer_*.log",
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

    async def get_orphans(self) -> dict[str, Any]:
        orphans = await self._sweep_orphans()
        return {"orphans": orphans, "count": len(orphans)}

    async def cleanup_orphans(self) -> dict[str, Any]:
        """清理 pidfile 记录的本项目 realtime 子进程。只按 pidfile 杀，不按关键词全局 kill。"""
        runtime_dir = self._log_dir / "runtime"
        killed = []
        errors = []
        for pattern in ["akshare_*.pid", "raw_news_*.pid", "decision_*.pid", "rebuild_*.pid", "intel_producer_*.pid"]:
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

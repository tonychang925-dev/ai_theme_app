"""JYHF CDP service lifecycle — direct Popen management, no shell scripts.

Ownership model:
- managed: this manager instance started the process (self._process is set)
- external: process was already running on the port when we probed
- managed  → stop_collector kills both collector and process
- external → stop_collector only stops collector, never touches the process
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_HEALTH_ENDPOINTS = ("/health", "/healthz", "/status")
_READY_TIMEOUT = 30.0
_GRACEFUL_STOP = 2.0


class JyhfCdpManager:
    def __init__(self, project_root: str, port: int = 8095) -> None:
        self._project_root = Path(project_root).resolve()
        self._port = port
        self._base_url = f"http://127.0.0.1:{port}"
        self._log_file = self._resolve_log_path()
        self._process: subprocess.Popen | None = None
        self._owner: str = "none"   # "managed" | "external" | "none"
        self._last_error: str | None = None
        self._start_lock = asyncio.Lock()
        self._managed_pid: int | None = None
        self._managed_pgid: int | None = None
        self._status_seq: int = 0
        self._cached_status: dict[str, Any] | None = None

    def _clear_state_trace(self, reason: str, clear_managed_pid: bool = False) -> None:
        """Log every state clear with full context before clearing."""
        import traceback as _tb
        logging.getLogger().warning(
            "CDP_STATE_CLEAR_TRACE reason=%s before_owner=%s before_process_pid=%s before_managed_pid=%s stack=%s",
            reason,
            self._owner,
            self._process.pid if self._process else None,
            self._managed_pid,
            "".join(_tb.format_stack(limit=6))[-300:].replace("\n", " ← "),
        )
        if clear_managed_pid:
            self._managed_pid = None
            self._managed_pgid = None

    def _resolve_log_path(self) -> Path:
        desktop_log = os.getenv("DESKTOP_LOG_DIR")
        if desktop_log:
            return Path(desktop_log) / "jyhf_cdp_service.log"
        return self._project_root / "logs" / "jyhf_cdp_service.log"

    # ── public ───────────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        import os as _manager_os

        self._status_seq += 1
        seq = self._status_seq

        logger.error(
            "CDP_STATUS_ENTER seq=%s owner=%s process_pid=%s managed_pid=%s managed_pgid=%s",
            seq, self._owner, self._process.pid if self._process else None, self._managed_pid, self._managed_pgid,
        )

        popen_pid: int | None = self._process.pid if self._process else None
        popen_alive: bool = bool(self._process and self._process.poll() is None)

        # Step 1: HTTP /status — always tried first, authoritative
        collector_status: dict | None = None
        collector_running: bool = False
        http_alive: bool = False
        http_error: str | None = None

        logging.getLogger().warning("CDP_STATUS_TRACE seq=%s step=before_http base_url=%s", seq, self._base_url)

        try:
            collector_status = await self._get("/status")
            collector_running = bool(collector_status.get("collector_running"))
            http_alive = True
            logging.getLogger().warning("CDP_STATUS_TRACE seq=%s step=http_ok collector_running=%s", seq, collector_running)
        except Exception as exc:
            http_error = str(exc)
            logging.getLogger().warning("CDP_STATUS_TRACE seq=%s step=http_fail error=%s", seq, http_error)

        # Step 2: lsof port_pid — fallback / diagnostic, not a gate
        logging.getLogger().warning("CDP_STATUS_TRACE seq=%s step=before_lsof port=%s", seq, self._port)
        port_pid: int | None = await asyncio.to_thread(self._find_pid_by_port_blocking)
        logging.getLogger().warning("CDP_STATUS_TRACE seq=%s step=after_lsof port_pid=%s", seq, port_pid)

        service_alive: bool = http_alive or (port_pid is not None)

        # Step 3: owner resolution — managed_pid NEVER cleared here
        effective_pid = port_pid or popen_pid or self._managed_pid

        if service_alive:
            if self._owner == "none":
                if effective_pid and self._managed_pid and effective_pid == self._managed_pid:
                    self._owner = "managed"
                    logging.getLogger().warning("CDP_OWNER_RECOVER seq=%s none→managed effective_pid=%s managed_pid=%s", seq, effective_pid, self._managed_pid)
                else:
                    self._owner = "external"
                    logging.getLogger().warning("CDP_OWNER_RECOVER seq=%s none→external effective_pid=%s managed_pid=%s", seq, effective_pid, self._managed_pid)
            elif self._owner == "managed":
                if port_pid and self._managed_pid and port_pid != self._managed_pid:
                    self._owner = "external"
        else:
            if self._owner in ("managed", "external"):
                logging.getLogger().warning(
                    "CDP_STATE_CLEAR_TRACE reason=get_status_service_dead seq=%s before_owner=%s before_process_pid=%s before_managed_pid=%s popen_pid=%s popen_alive=%s port_pid=%s http_error=%s",
                    seq, self._owner, self._process.pid if self._process else None, self._managed_pid, popen_pid, popen_alive, port_pid, http_error)
                self._clear_state_trace("get_status_service_dead")
                self._owner = "none"
                self._process = None
                # managed_pid preserved for recovery

        result: dict[str, Any] = {
            "service_running": service_alive,
            "service_owner": self._owner,
            "service_pid": port_pid or (popen_pid if popen_alive else (self._managed_pid if service_alive else None)),
            "service_port": self._port,
            "collector_running": collector_running,
            "collector_status": collector_status,
            "last_error": self._last_error,
            "bff_pid": _manager_os.getpid(),
            "bff_port": int(_manager_os.getenv("WEB_PORT", "8000")),
            "manager_id": id(self),
            "popen_pid": popen_pid,
            "popen_alive": popen_alive,
            "port_pid": port_pid,
            "managed_pid": self._managed_pid,
            "http_alive": http_alive,
        }
        if http_error:
            result["http_error"] = http_error

        logging.getLogger().warning(
            "CDP_STATUS_TRACE seq=%s step=return sr=%s owner=%s popen_pid=%s port_pid=%s managed_pid=%s http_alive=%s http_error=%s",
            seq, service_alive, self._owner, popen_pid, port_pid, self._managed_pid, http_alive, http_error,
        )

        if isinstance(collector_status, dict):
            for k in ("app_running", "cdp_connected", "cdp_port", "current_route", "current_tab",
                      "last_capture_at", "last_event_at", "capture_count_total",
                      "new_event_count_total", "duplicate_count_total",
                      "parse_error_count_total", "pushed_to_stream_count_total",
                      "pushed_to_intel_count_total", "pushed_to_db_count_total",
                      "review_queue_count_total"):
                if k in collector_status:
                    result[k] = collector_status[k]
        return result

    async def get_logs(self, lines: int = 300) -> dict[str, Any]:
        lines = max(20, min(int(lines), 2000))
        log_lines: list[str] = []
        if self._log_file.exists():
            log_lines = self._log_file.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        collector_lines: list[str] = []
        if await self._probe():
            try:
                resp = await self._get("/collector/logs", params={"lines": lines})
                collector_lines = resp.get("lines") or []
            except Exception:
                pass
        return {"log_file": str(self._log_file), "lines": log_lines, "collector_lines": collector_lines}

    async def start_collector(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        push_intel = payload.get("push_intel", True)
        push_db = payload.get("push_db", True)

        async with self._start_lock:
            return await self._start_collector_locked(payload, push_intel, push_db)

    async def stop_collector(self, stop_service: bool = True) -> dict[str, Any]:
        collector_msg = ""
        if await self._probe():
            try:
                await self._post("/collector/stop", payload={})
                collector_msg = "collector stopped"
            except Exception as exc:
                collector_msg = f"collector already stopped ({exc})"
        else:
            collector_msg = "CDP service not running"

        service_msg = ""
        if stop_service and self._owner == "managed":
            if await self._probe():
                service_msg = await self._stop_managed_process()
            else:
                self._clear_state_trace("stop_collector_already_stopped")
                self._owner = "none"
                self._process = None
                service_msg = "CDP service already stopped"
        elif stop_service and self._owner == "external":
            service_msg = "external service not stopped (owner=external)"

        self._last_error = None
        return self._cmd_result(True, f"{collector_msg}; {service_msg}".strip("; "), False)

    async def stop_service(self) -> dict[str, Any]:
        """Public API: only stops if managed."""
        if not await self._probe():
            self._clear_state_trace("stop_service_already_dead")
            self._owner = "none"
            self._process = None
            return self._cmd_result(True, "already stopped", False)
        if self._owner != "managed":
            return self._cmd_result(True, "not managed, not stopped", False)
        msg = await self._stop_managed_process()
        return self._cmd_result(True, msg, False)

    async def force_stop_service(self) -> dict[str, Any]:
        """诊断接口：按端口强杀 8095 进程，不限 owner。仅用于清理旧残留。"""
        if not await self._probe():
            return self._cmd_result(True, "no CDP service on port", False)
        prev_owner = self._owner
        try:
            await self._post("/collector/stop", payload={})
        except Exception:
            pass
        if self._owner == "managed" and self._process:
            await self._stop_managed_process()
        else:
            killed = await asyncio.to_thread(self._kill_port_blocking)
            if not killed:
                return self._cmd_result(False, "force-stop: could not kill process on port", False)
            await asyncio.sleep(1)
        self._clear_state_trace("force_stop_done")
        self._owner = "none"
        self._process = None
        return self._cmd_result(True, f"force-stopped CDP service (was owner={prev_owner})", False)

    def _kill_port_blocking(self) -> bool:
        """Blocking port-based kill via lsof + kill. Runs in thread."""
        import subprocess as sp
        try:
            out = sp.run(
                ["lsof", "-t", "-i", f"TCP:{self._port}", "-s", "TCP:LISTEN"],
                capture_output=True, text=True, timeout=10,
            )
            pid_str = out.stdout.strip()
            if pid_str and pid_str.isdigit():
                os.kill(int(pid_str), signal.SIGKILL)
                return True
            logging.getLogger().warning("force-stop: lsof returned unexpected output: %r", out.stdout[:100])
        except Exception as exc:
            logging.getLogger().warning("force-stop: lsof/kill failed: %s", exc)
        return False

    def _cmd_result(
        self, ok: bool, message: str, collector_running: bool,
        *, service_running: bool | None = None,
    ) -> dict[str, Any]:
        """Build a uniform command response with core status fields."""
        pid = self._process.pid if (self._process and self._process.poll() is None) else None
        if service_running is None:
            service_running = bool(pid) or self._owner == "external"
        return {
            "ok": ok,
            "message": message,
            "service_running": service_running,
            "service_owner": self._owner,
            "service_pid": pid,
            "service_port": self._port,
            "collector_running": collector_running,
            "last_error": self._last_error,
        }

    async def _status_result(self, ok: bool, message: str) -> dict[str, Any]:
        """Build a command response that includes full status from get_status()."""
        status = await self.get_status()
        return {"ok": ok, "message": message, **status}

    async def _start_collector_locked(self, payload: dict, push_intel: bool, push_db: bool) -> dict[str, Any]:
        if not await self._probe():
            ok, msg = await self._launch_process(push_intel=push_intel, push_db=push_db)
            if not ok:
                self._last_error = msg
                return self._cmd_result(False, msg, False)
        elif self._owner == "none":
            self._owner = "external"

        try:
            result = await self._post("/collector/start", payload=payload or {})
        except Exception as exc:
            self._last_error = str(exc)
            if self._owner == "managed" and not payload.get("keep_service_on_error"):
                await self._stop_managed_process()
            return self._cmd_result(False, f"collector start failed: {exc}", False)

        # Wait for collector to confirm running (not just "start accepted")
        confirmed = False
        for _ in range(15):
            if await self._probe():
                try:
                    st = await self._get("/status")
                    if st.get("collector_running"):
                        confirmed = True
                        break
                except Exception:
                    pass
            await asyncio.sleep(0.5)

        if not confirmed:
            self._last_error = "collector did not enter running state within timeout"
            logging.getLogger().warning("collector_start_confirm_timeout service_kept_alive=true")
            # Do NOT kill CDP service — it may still be initializing.
            # Return ok=true: start command was submitted successfully.
            # collector readiness is surfaced via status fields, not ok/fail.
            return await self._status_result(
                True,
                "collector start submitted; waiting for JYHF App/CDP/DOM"
            )

        self._last_error = None
        # Return full status so frontend can show layered state immediately
        return await self._status_result(True, result.get("message", "collector started"))

    async def _launch_process(self, *, push_intel: bool, push_db: bool) -> tuple[bool, str]:
        python = sys_executable()
        env = os.environ.copy()
        env["JYHF_CDP_PUSH_INTEL"] = "1" if push_intel else "0"
        env["JYHF_CDP_PUSH_DB"] = "1" if push_db else "0"
        env["JYHF_CDP_SERVICE_PORT"] = str(self._port)

        self._log_file.parent.mkdir(parents=True, exist_ok=True)
        log_fd = open(str(self._log_file), "a")

        try:
            proc = subprocess.Popen(
                [python, "-m", "uvicorn", "services.jyhf_cdp_service.app:app",
                 "--host", "127.0.0.1", "--port", str(self._port), "--workers", "1"],
                cwd=str(self._project_root),
                env=env,
                stdout=log_fd,
                stderr=log_fd,
                start_new_session=True,
            )
        except Exception as exc:
            log_fd.close()
            return False, f"failed to spawn CDP process: {exc}"

        self._process = proc
        self._owner = "managed"
        self._managed_pid = proc.pid
        self._managed_pgid = os.getpgid(proc.pid)
        logging.getLogger().warning("CDP_MANAGED_LAUNCH pid=%s pgid=%s", proc.pid, self._managed_pgid)

        deadline = time.time() + _READY_TIMEOUT
        while time.time() < deadline:
            rc = proc.poll()
            if rc is not None and rc != 0:
                log_fd.close()
                self._process = None
                self._owner = "none"
                self._clear_state_trace("process_exited_or_unreachable")
                return False, f"CDP process exited with code {rc}"
            if await self._probe():
                return True, "CDP service ready"
            await asyncio.sleep(0.8)

        # Timeout: kill the failed process
        log_fd.close()
        await self._stop_managed_process()
        return False, f"CDP service did not start within {_READY_TIMEOUT}s"

    async def _stop_managed_process(self) -> str:
        import traceback
        logging.getLogger().warning(
            "BFF _stop_managed_process called from:\n%s",
            "".join(traceback.format_stack(limit=8)[:-1]),
        )
        proc = self._process
        if proc is None:
            self._clear_state_trace("stop_managed_proc_is_none")
            self._owner = "none"
            return "no managed process"

        pid = proc.pid
        if pid is None:
            self._clear_state_trace("stop_managed_pid_is_none")
            self._owner = "none"
            self._process = None
            return "managed process has no PID"

        logging.getLogger().warning("BFF killing CDP: PID=%s PGID=%s", pid, os.getpgid(pid))
        try:
            pgid = os.getpgid(pid)
            os.killpg(pgid, signal.SIGTERM)
            for _ in range(int(_GRACEFUL_STOP)):
                if not await self._probe():
                    break
                await asyncio.sleep(1)
            if await self._probe():
                os.killpg(pgid, signal.SIGKILL)
                await asyncio.sleep(0.5)
        except (ProcessLookupError, OSError):
            pass

        self._clear_state_trace("stop_managed_process_done")
        self._owner = "none"
        self._process = None
        return f"CDP service stopped (PID={pid})"

    def _find_pid_by_port_blocking(self) -> int | None:
        """Find the PID listening on self._port via lsof. Runs synchronously."""
        try:
            out = subprocess.run(
                ["lsof", "-t", "-i", f"TCP:{self._port}", "-s", "TCP:LISTEN"],
                capture_output=True, text=True, timeout=5,
            )
            pid_str = out.stdout.strip()
            if pid_str and pid_str.isdigit():
                return int(pid_str)
        except Exception:
            pass
        return None

    async def _probe(self) -> bool:
        for ep in _HEALTH_ENDPOINTS:
            try:
                async with httpx.AsyncClient(timeout=3.0, trust_env=False) as c:
                    r = await c.get(f"{self._base_url}{ep}")
                    if r.status_code == 200:
                        r.json()
                        return True
            except Exception:
                continue
        return False

    async def _get(self, path: str, *, params: dict | None = None, **kw) -> dict:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as c:
            r = await c.get(f"{self._base_url}{path}", params=params, **kw)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {}

    async def _post(self, path: str, *, payload: dict | None = None, **kw) -> dict:
        async with httpx.AsyncClient(timeout=30.0, trust_env=False) as c:
            r = await c.post(f"{self._base_url}{path}", json=payload or {}, **kw)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {}


def sys_executable() -> str:
    return os.getenv("PYTHON", os.getenv("CONDA_PYTHON", os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        ".venv", "bin", "python"
    )))

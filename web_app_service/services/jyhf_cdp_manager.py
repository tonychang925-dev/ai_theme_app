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

    def _resolve_log_path(self) -> Path:
        desktop_log = os.getenv("DESKTOP_LOG_DIR")
        if desktop_log:
            return Path(desktop_log) / "jyhf_cdp_service.log"
        return self._project_root / "logs" / "jyhf_cdp_service.log"

    # ── public ───────────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        alive = await self._probe()
        pid = self._process.pid if (self._process and self._process.poll() is None) else None

        # Auto-reclaim: if managed process died, clear ownership
        if not alive and self._owner == "managed" and self._process and self._process.poll() is not None:
            self._process = None
            self._owner = "none"

        # Auto-detect: alive but not owned → external
        if alive and self._owner == "none":
            self._owner = "external"

        collector_status: dict | None = None
        collector_running = False
        if alive:
            try:
                collector_status = await self._get("/status")
                collector_running = bool(collector_status.get("collector_running"))
            except Exception:
                pass

        result: dict[str, Any] = {
            "service_running": alive,
            "service_owner": self._owner,
            "service_pid": pid,
            "service_port": self._port,
            "collector_running": collector_running,
            "collector_status": collector_status,
            "last_error": self._last_error,
        }
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
            logger.warning("force-stop: lsof returned unexpected output: %r", out.stdout[:100])
        except Exception as exc:
            logger.warning("force-stop: lsof/kill failed: %s", exc)
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
            logger.warning("collector_start_confirm_timeout service_kept_alive=true")
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

        deadline = time.time() + _READY_TIMEOUT
        while time.time() < deadline:
            rc = proc.poll()
            if rc is not None and rc != 0:
                log_fd.close()
                self._process = None
                self._owner = "none"
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
        logger.warning(
            "BFF _stop_managed_process called from:\n%s",
            "".join(traceback.format_stack(limit=8)[:-1]),
        )
        proc = self._process
        if proc is None:
            self._owner = "none"
            return "no managed process"

        pid = proc.pid
        if pid is None:
            self._owner = "none"
            self._process = None
            return "managed process has no PID"

        logger.warning("BFF killing CDP: PID=%s PGID=%s", pid, os.getpgid(pid))
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

        self._owner = "none"
        self._process = None
        return f"CDP service stopped (PID={pid})"

    async def _probe(self) -> bool:
        for ep in _HEALTH_ENDPOINTS:
            try:
                async with httpx.AsyncClient(timeout=3.0) as c:
                    r = await c.get(f"{self._base_url}{ep}")
                    if r.status_code == 200:
                        r.json()
                        return True
            except Exception:
                continue
        return False

    async def _get(self, path: str, *, params: dict | None = None, **kw) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._base_url}{path}", params=params, **kw)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {}

    async def _post(self, path: str, *, payload: dict | None = None, **kw) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{self._base_url}{path}", json=payload or {}, **kw)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, dict) else {}


def sys_executable() -> str:
    return os.getenv("PYTHON", os.getenv("CONDA_PYTHON", os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        ".venv", "bin", "python"
    )))

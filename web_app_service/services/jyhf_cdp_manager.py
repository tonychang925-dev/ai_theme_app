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
_GRACEFUL_STOP = 5.0


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
        return {
            "ok": True,
            "message": f"{collector_msg}; {service_msg}".strip("; "),
            "service_running": await self._probe(),
            "service_owner": self._owner,
            "collector_running": False,
        }

    async def stop_service(self) -> dict[str, Any]:
        """Public API: only stops if managed."""
        if not await self._probe():
            self._owner = "none"
            self._process = None
            return {"ok": True, "message": "already stopped", "service_owner": "none"}
        if self._owner != "managed":
            return {"ok": True, "message": "not managed, not stopped", "service_owner": self._owner}
        msg = await self._stop_managed_process()
        return {"ok": True, "message": msg, "service_owner": "none"}

    # ── internal ─────────────────────────────────────────────────

    async def _start_collector_locked(self, payload: dict, push_intel: bool, push_db: bool) -> dict[str, Any]:
        if not await self._probe():
            ok, msg = await self._launch_process(push_intel=push_intel, push_db=push_db)
            if not ok:
                self._last_error = msg
                return {"ok": False, "message": msg, "service_owner": "none", "collector_running": False}
            # _launch_process sets self._owner = "managed" and self._process
        elif self._owner == "none":
            # Process is alive but we didn't start it
            self._owner = "external"

        try:
            result = await self._post("/collector/start", payload=payload or {})
        except Exception as exc:
            self._last_error = str(exc)
            if self._owner == "managed" and not payload.get("keep_service_on_error"):
                await self._stop_managed_process()
            return {"ok": False, "message": f"collector start failed: {exc}",
                    "service_owner": self._owner, "collector_running": False}

        # Wait for collector to confirm running
        for _ in range(15):
            if await self._probe():
                try:
                    st = await self._get("/status")
                    if st.get("collector_running"):
                        break
                except Exception:
                    pass
            await asyncio.sleep(0.5)

        self._last_error = None
        return {"ok": True, "message": result.get("message", "collector started"),
                "service_owner": self._owner, "collector_running": True}

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
        proc = self._process
        if proc is None:
            self._owner = "none"
            return "no managed process"

        pid = proc.pid
        if pid is None:
            self._owner = "none"
            self._process = None
            return "managed process has no PID"

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

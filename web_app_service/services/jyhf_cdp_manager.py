"""JYHF CDP service lifecycle — thin wrapper over existing scripts.

Reuses ``scripts/start_jyhf_cdp_service.sh`` for process management
instead of reimplementing Popen / env / logging logic.
"""

from __future__ import annotations

import asyncio
import os
import signal
import time
from pathlib import Path
from typing import Any

import httpx

_HEALTH_ENDPOINTS = ("/health", "/healthz", "/status")
_READY_TIMEOUT = 30.0
_GRACEFUL_STOP = 5.0


class JyhfCdpManager:
    """Thin wrapper that delegates process management to start_jyhf_cdp_service.sh."""

    def __init__(self, project_root: str, port: int = 8095) -> None:
        self._project_root = Path(project_root).resolve()
        self._port = port
        self._base_url = f"http://127.0.0.1:{port}"
        self._pid_file = self._project_root / "tmp" / "realtime" / "jyhf_cdp_service" / "service.pid"
        self._log_file = self._project_root / "logs" / "jyhf_cdp_service.log"
        self._managed = False  # True when we started the service via script
        self._last_error: str | None = None
        self._start_lock = asyncio.Lock()

    # ── public ───────────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        alive = await self._probe()
        owner = "managed" if (alive and self._managed) else ("external" if alive else "none")
        pid = self._read_pid()

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
            "service_owner": owner,
            "service_pid": pid,
            "service_port": self._port,
            "collector_running": collector_running,
            "collector_status": collector_status,
            "last_error": self._last_error,
        }
        # Merge legacy fields for frontend compatibility
        if isinstance(collector_status, dict):
            for k in ("app_running", "cdp_connected", "cdp_port", "current_route", "current_tab",
                      "last_capture_at", "last_event_at", "capture_count_total",
                      "new_event_count_total", "duplicate_count_total",
                      "parse_error_count_total", "pushed_to_stream_count_total",
                      "pushed_to_db_count_total", "review_queue_count_total"):
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

    async def _start_collector_locked(self, payload: dict, push_intel: bool, push_db: bool) -> dict[str, Any]:
        if not await self._probe():
            ok, msg = await self._run_start_script(push_intel=push_intel, push_db=push_db)
            if not ok:
                self._last_error = msg
                return {"ok": False, "message": msg, "service_owner": "none", "collector_running": False}
            self._managed = True

        try:
            result = await self._post("/collector/start", payload=payload or {})
        except Exception as exc:
            self._last_error = str(exc)
            if self._managed and not payload.get("keep_service_on_error"):
                await self._stop_service()
            return {"ok": False, "message": f"collector start failed: {exc}",
                    "service_owner": "managed" if self._managed else "external", "collector_running": False}

        self._last_error = None
        return {"ok": True, "message": result.get("message", "collector started"),
                "service_owner": "managed" if self._managed else "external", "collector_running": True,
                "return_code": 0, "stdout": "collector started", "stderr": ""}

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
        if stop_service and await self._probe():
            service_msg = await self._stop_service()
        elif stop_service:
            service_msg = "CDP service already stopped"

        self._last_error = None
        return {"ok": True, "message": f"{collector_msg}; {service_msg}".strip("; "),
                "service_running": await self._probe(), "service_owner": "managed" if self._managed else "none",
                "collector_running": False}

    async def stop_service(self) -> dict[str, Any]:
        if not await self._probe():
            return {"ok": True, "message": "already stopped", "service_owner": "none"}
        msg = await self._stop_service()
        return {"ok": True, "message": msg, "service_owner": "none"}

    # ── internal ─────────────────────────────────────────────────

    async def _run_start_script(self, *, push_intel: bool, push_db: bool) -> tuple[bool, str]:
        python = os.getenv("PYTHON", str(self._project_root / ".venv" / "bin" / "python"))
        cmd = (
            f"JYHF_CDP_PUSH_INTEL={'1' if push_intel else '0'} "
            f"JYHF_CDP_PUSH_DB={'1' if push_db else '0'} "
            f"JYHF_CDP_SERVICE_PORT={self._port} "
            f"PYTHON={python} "
            f"bash {self._project_root}/scripts/start_jyhf_cdp_service.sh"
        )
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                cwd=str(self._project_root),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
                start_new_session=True,
            )
            deadline = time.time() + _READY_TIMEOUT
            while time.time() < deadline:
                if proc.returncode is not None and proc.returncode != 0:
                    return False, f"start script exited with code {proc.returncode}"
                if await self._probe():
                    return True, "CDP service ready"
                await asyncio.sleep(0.8)
            return False, f"CDP service did not start within {_READY_TIMEOUT}s"
        except Exception as exc:
            return False, f"failed to run start script: {exc}"

    async def _stop_service(self) -> str:
        pid = self._read_pid()
        if not pid:
            pid = self._find_pid_by_port()
        if pid:
            try:
                os.kill(pid, signal.SIGTERM)
                for _ in range(int(_GRACEFUL_STOP)):
                    if not await self._probe():
                        break
                    await asyncio.sleep(1)
                if await self._probe():
                    os.kill(pid, signal.SIGKILL)
                    await asyncio.sleep(0.5)
                self._managed = False
                try:
                    self._pid_file.unlink(missing_ok=True)
                except Exception:
                    pass
                return f"CDP service stopped (PID={pid})"
            except (ProcessLookupError, OSError):
                pass
        # If we can't find the PID, try killing by port
        if await self._probe():
            await self._kill_by_port()
        self._managed = False
        try:
            self._pid_file.unlink(missing_ok=True)
        except Exception:
            pass
        return "CDP service stopped"

    def _find_pid_by_port(self) -> int | None:
        """Find the PID of the process listening on the CDP service port."""
        import subprocess
        try:
            out = subprocess.run(
                ["lsof", "-nP", "-iTCP", f":{self._port}", "-sTCP:LISTEN", "-t"],
                capture_output=True, text=True, timeout=5,
            )
            pid_str = out.stdout.strip().split('\n')[0]
            if pid_str and pid_str.isdigit():
                return int(pid_str)
        except Exception:
            pass
        return None

    async def _kill_by_port(self) -> None:
        """Kill the process listening on the CDP service port using fuser or lsof."""
        import subprocess
        try:
            pid = self._find_pid_by_port()
            if pid:
                os.kill(pid, signal.SIGTERM)
                await asyncio.sleep(2)
                if await self._probe():
                    os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

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

    def _read_pid(self) -> int | None:
        try:
            return int(self._pid_file.read_text().strip())
        except Exception:
            return None

    async def _get(self, path: str, *, params: dict | None = None, **kw) -> dict:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(f"{self._base_url}{path}", params=params, **kw)
            r.raise_for_status()
            return r.json() if isinstance(r.json(), dict) else {}

    async def _post(self, path: str, *, payload: dict | None = None, **kw) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as c:
            r = await c.post(f"{self._base_url}{path}", json=payload or {}, **kw)
            r.raise_for_status()
            return r.json() if isinstance(r.json(), dict) else {}

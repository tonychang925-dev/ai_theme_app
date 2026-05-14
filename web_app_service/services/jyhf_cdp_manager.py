"""JYHF CDP service lifecycle manager.

Manages the CDP service process (uvicorn on port 8095) with the following guarantees:

- ``owner=managed``: started by this manager → kill on stop/shutdown
- ``owner=external``: started externally (script/user) → never kill, only stop collector
- ``owner=none``: no CDP service running

Process management uses ``start_new_session=True`` + ``os.killpg()`` to ensure
all child processes (uvicorn workers, Chrome/Playwright subprocesses) are cleaned up.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Literal

import httpx

_HEALTH_ENDPOINTS = ("/healthz", "/health", "/status")
_SERVICE_READY_TIMEOUT_SEC = 30.0
_SERVICE_POLL_INTERVAL_SEC = 0.8
_GRACEFUL_STOP_TIMEOUT_SEC = 5.0
_FORCE_KILL_TIMEOUT_SEC = 2.0


class JyhfCdpManager:
    """Manages the JYHF CDP uvicorn process and its collector lifecycle."""

    def __init__(self, project_root: str, port: int = 8095) -> None:
        self._project_root = Path(project_root).resolve()
        self._port = port
        self._base_url = f"http://127.0.0.1:{port}"
        self._process: subprocess.Popen[bytes] | None = None
        self._owner: Literal["none", "managed", "external"] = "none"
        self._lock = asyncio.Lock()
        self._last_error: str | None = None
        self._managed_started_for_request = False  # set per start_collector call

    # ── public API ───────────────────────────────────────────────

    async def get_status(self) -> dict[str, Any]:
        """Return combined status (local process + remote collector).

        Never raises / returns 503 — always returns a friendly JSON body.
        """
        service_running = await self._probe_service()
        process_pid = self._resolve_process_pid()
        collector_status: dict[str, Any] | None = None
        collector_running = False

        if service_running:
            try:
                collector_status = await self._get_json("/status", timeout=5.0)
                collector_running = bool(collector_status.get("collector_running") or False)
            except Exception:
                collector_running = False

        # Resolve owner based on current reality
        owner = self._resolve_owner(service_running)

        return {
            "service_running": service_running,
            "service_owner": owner,
            "service_pid": process_pid,
            "service_port": self._port,
            "collector_running": collector_running,
            "collector_status": collector_status,
            "last_error": self._last_error,
        }

    async def get_logs(self, lines: int = 300) -> dict[str, Any]:
        """Read the local CDP service log file.

        Does NOT depend on port 8095 being alive.
        """
        lines = max(20, min(int(lines), 2000))
        log_path = self._log_path()
        log_lines: list[str] = []
        if log_path.exists():
            log_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]

        # Optionally merge collector logs if service is alive
        collector_lines: list[str] = []
        if await self._probe_service():
            try:
                resp = await self._get_json("/collector/logs", params={"lines": lines}, timeout=5.0)
                collector_lines = resp.get("lines") or []
            except Exception:
                pass

        return {
            "log_file": str(log_path),
            "lines": log_lines,
            "collector_lines": collector_lines,
        }

    async def start_collector(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """Ensure CDP service is ready, then start the collector loop.

        If the service was started by this manager and the collector fails to start,
        the service is automatically stopped to avoid a dangling process.
        Pass ``keep_service_on_error=true`` in the payload to suppress this behaviour.
        """
        payload = payload or {}
        keep_on_error = bool(payload.get("keep_service_on_error") or False)
        push_intel = bool(payload.get("push_intel") or os.getenv("JYHF_CDP_PUSH_INTEL", "0").strip().lower() in {"1", "true", "yes", "on"})
        push_db = bool(payload.get("push_db") or os.getenv("JYHF_CDP_PUSH_DB", "0").strip().lower() in {"1", "true", "yes", "on"})

        async with self._lock:
            self._managed_started_for_request = False
            try:
                ensure_result = await self._ensure_service(push_intel=push_intel, push_db=push_db)
                if not ensure_result.get("ok"):
                    return ensure_result

                self._managed_started_for_request = (ensure_result.get("owner") == "managed")

                try:
                    result = await self._post_json("/collector/start", payload=payload, timeout=30.0)
                except Exception as exc:
                    self._last_error = f"collector start failed: {exc}"
                    if self._managed_started_for_request and not keep_on_error:
                        await self._stop_service_internal()
                        self._last_error += " (CDP service stopped)"
                    return {
                        "ok": False,
                        "message": self._last_error,
                        "service_owner": self._owner,
                        "collector_running": False,
                    }

                self._last_error = None
                return {
                    "ok": result.get("ok", True),
                    "message": result.get("message", "collector started"),
                    "return_code": result.get("return_code", 0),
                    "stdout": result.get("stdout", ""),
                    "stderr": result.get("stderr", ""),
                    "service_owner": self._owner,
                    "collector_running": True,
                }
            except Exception as exc:
                self._last_error = str(exc)
                return {
                    "ok": False,
                    "message": f"start failed: {exc}",
                    "service_owner": self._owner,
                    "collector_running": False,
                }

    async def stop_collector(self, stop_service: bool = True) -> dict[str, Any]:
        """Stop the collector loop.  If *stop_service* is True and the service
        is managed, also stop the CDP uvicorn process.

        Tolerates the CDP service already being gone (returns ok=True).
        """
        async with self._lock:
            collector_stopped = False
            collector_message = ""

            # 1. Stop collector (best-effort)
            if await self._probe_service():
                try:
                    result = await self._post_json("/collector/stop", payload={}, timeout=15.0)
                    collector_stopped = result.get("ok", True)
                    collector_message = result.get("message", "collector stopped")
                except Exception as exc:
                    collector_message = f"collector stop skipped (service unreachable: {exc})"
                    collector_stopped = True  # service is already gone → effectively stopped
            else:
                collector_message = "CDP service not running, collector already stopped"
                collector_stopped = True

            # 2. Optionally stop managed service
            service_stopped = False
            service_message = ""
            if stop_service and self._owner == "managed":
                service_message = await self._stop_service_internal()
                service_stopped = True
            elif stop_service and self._owner == "external":
                service_message = "external service not stopped"
            elif not stop_service:
                service_message = "service kept running (stop_service=false)"

            # 3. Clean up local state if service is gone
            if not await self._probe_service():
                self._process = None
                self._owner = "none"

            self._last_error = None
            return {
                "ok": True,
                "message": "; ".join(filter(None, [collector_message, service_message])),
                "service_running": await self._probe_service(),
                "service_owner": self._owner,
                "collector_running": False,
                "collector_stopped": collector_stopped,
                "service_stopped": service_stopped,
            }

    async def stop_service(self) -> dict[str, Any]:
        """Force-stop the managed CDP service process.  Never kills external processes."""
        async with self._lock:
            if self._owner != "managed":
                return {
                    "ok": True,
                    "message": "external service not stopped (owner is not managed)",
                    "service_owner": self._owner,
                }
            message = await self._stop_service_internal()
            return {
                "ok": True,
                "message": message,
                "service_owner": self._owner,
            }

    # ── internal ─────────────────────────────────────────────────

    async def _ensure_service(self, *, push_intel: bool, push_db: bool) -> dict[str, Any]:
        """Probe 8095; if not alive, spawn the CDP uvicorn process.

        Returns ``{"ok": True, "owner": "managed"|"external"}`` on success.
        """
        if await self._probe_service():
            if self._owner != "managed":
                self._owner = "external"
            self._last_error = None
            return {"ok": True, "message": "CDP service already running", "owner": self._owner}

        # Service not running — start it
        self._last_error = None
        try:
            pid = await self._start_service_process(push_intel=push_intel, push_db=push_db)
            self._owner = "managed"
            self._last_error = None
            return {"ok": True, "message": f"CDP service started (PID={pid})", "owner": "managed", "pid": pid}
        except Exception as exc:
            self._owner = "none"
            self._process = None
            self._last_error = f"failed to start CDP service: {exc}"
            return {"ok": False, "message": self._last_error, "owner": "none"}

    async def _start_service_process(self, *, push_intel: bool, push_db: bool) -> int:
        """Spawn the CDP uvicorn process and block until it responds to health checks."""
        log_path = self._log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fd = open(str(log_path), "a")

        env = os.environ.copy()
        env["JYHF_CDP_PUSH_INTEL"] = "1" if push_intel else "0"
        env["JYHF_CDP_PUSH_DB"] = "1" if push_db else "0"
        env["JYHF_CDP_SERVICE_PORT"] = str(self._port)
        env["JYHF_CDP_SERVICE_HOST"] = "127.0.0.1"
        env["PYTHONUNBUFFERED"] = "1"

        args = [
            sys.executable,
            "-m", "uvicorn",
            "services.jyhf_cdp_service.app:app",
            "--host", "127.0.0.1",
            "--port", str(self._port),
            "--workers", "1",
        ]

        self._process = subprocess.Popen(
            args,
            cwd=str(self._project_root),
            env=env,
            stdout=log_fd,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

        # Wait for service to become ready
        deadline = time.time() + _SERVICE_READY_TIMEOUT_SEC
        last_error = ""
        while time.time() < deadline:
            if self._process.poll() is not None:
                log_fd.close()
                raise RuntimeError(
                    f"CDP service exited prematurely with code {self._process.returncode}. "
                    f"Check {log_path} for details."
                )
            healthy, last_error = await self._check_health()
            if healthy:
                log_fd.close()
                return self._process.pid
            await asyncio.sleep(_SERVICE_POLL_INTERVAL_SEC)

        log_fd.close()
        # Timeout — kill the process we started
        await self._kill_process_group()
        self._process = None
        raise RuntimeError(
            f"CDP service did not become ready within {_SERVICE_READY_TIMEOUT_SEC}s. "
            f"Last error: {last_error}. Check {log_path} for details."
        )

    async def _stop_service_internal(self) -> str:
        """Kill the managed CDP process group.  Returns a status message."""
        if self._process is None:
            self._owner = "none"
            return "no managed process to stop"

        pid = self._process.pid
        await self._kill_process_group()
        self._process = None
        self._owner = "none"
        return f"CDP service stopped (PID={pid})"

    async def _kill_process_group(self) -> None:
        """Kill the process group: SIGTERM first, then SIGKILL after timeout."""
        if self._process is None or self._process.pid is None:
            return
        try:
            pgid = os.getpgid(self._process.pid)
            os.killpg(pgid, signal.SIGTERM)
            try:
                self._process.wait(timeout=_GRACEFUL_STOP_TIMEOUT_SEC)
                return
            except subprocess.TimeoutExpired:
                pass
            os.killpg(pgid, signal.SIGKILL)
            try:
                self._process.wait(timeout=_FORCE_KILL_TIMEOUT_SEC)
            except subprocess.TimeoutExpired:
                pass
        except (ProcessLookupError, OSError):
            pass  # process already gone

    async def _probe_service(self) -> bool:
        """Check if the CDP service is responding on its port."""
        healthy, _ = await self._check_health()
        return healthy

    async def _check_health(self) -> tuple[bool, str]:
        """Try each health endpoint in order.  Returns (healthy, last_error)."""
        for endpoint in _HEALTH_ENDPOINTS:
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    resp = await client.get(f"{self._base_url}{endpoint}")
                    if resp.status_code == 200:
                        try:
                            resp.json()
                        except Exception:
                            continue
                        return True, ""
            except Exception as exc:
                last_error = str(exc)
                continue
        return False, last_error if 'last_error' in dir() else "no endpoint responded"

    def _resolve_process_pid(self) -> int | None:
        """Return the PID of the managed process, or detect external PID."""
        if self._process is not None and self._process.pid is not None:
            return self._process.pid
        # Try to find external PID via lsof
        try:
            result = subprocess.run(
                ["lsof", "-t", "-nP", f"-iTCP:{self._port}", "-sTCP:LISTEN"],
                capture_output=True, text=True, timeout=5,
            )
            pids = [p for p in result.stdout.strip().split("\n") if p]
            return int(pids[0]) if pids else None
        except Exception:
            return None

    def _resolve_owner(self, service_running: bool) -> str:
        """Determine current owner based on process state and running reality."""
        if not service_running:
            return "none"
        if self._owner in ("managed", "external"):
            # If the managed process died unexpectedly, reset
            if self._owner == "managed" and self._process is not None and self._process.poll() is not None:
                self._owner = "none"
                self._process = None
                return "none"
            return self._owner
        # Service is running but we didn't start it
        return "external"

    def _log_path(self) -> Path:
        log_dir = os.getenv("DESKTOP_LOG_DIR") or str(self._project_root / "logs")
        return Path(log_dir) / "jyhf_cdp_service.log"

    async def _get_json(self, path: str, *, timeout: float = 10.0, params: dict[str, Any] | None = None) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{self._base_url}{path}", params=params)
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}

    async def _post_json(self, path: str, *, payload: dict[str, Any] | None = None, timeout: float = 10.0) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(f"{self._base_url}{path}", json=payload or {})
            resp.raise_for_status()
            data = resp.json()
            return data if isinstance(data, dict) else {}

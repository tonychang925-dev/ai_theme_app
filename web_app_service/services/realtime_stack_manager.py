"""New-chain realtime stack lifecycle owned by web_app_service.

This manager intentionally does not start or restart web_app_service itself.
Calls arrive through web_app_service, so restarting the current process from
inside the request would sever the management channel.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx


class RealtimeStackManager:
    def __init__(self, project_root: str, *, web_port: int = 8000, sps_port: int = 8090) -> None:
        self._project_root = Path(project_root).resolve()
        self._web_port = int(web_port)
        self._sps_port = int(sps_port)
        self._log_dir = Path(os.getenv("REALTIME_LOG_DIR", str(self._project_root / "logs" / "realtime")))
        self._sps_process: subprocess.Popen | None = None
        self._frontend_process: subprocess.Popen | None = None
        self._start_lock = asyncio.Lock()

    async def status(self) -> dict[str, Any]:
        """代理 SPS 的 /api/v1/realtime/status，返回前端需要的结构化数据。"""
        try:
            async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                r = await client.get(f"http://127.0.0.1:{self._sps_port}/api/v1/realtime/status")
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        # SPS 不可达时的 fallback 结构，明确标记状态来源
        return {
            "running": False,
            "running_verified": False,
            "status_source": "bff_sps_unreachable",
            "raw_news_pid": None,
            "decision_pid": None,
            "db_collector_pid": None,
            "pending_count": 0,
            "dead_letter_count": 0,
            "run_id": "",
            "profile_version": "?",
            "profile_status": "?",
            "last_error": "SPS unreachable",
        }

    async def start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """同步代理 SPS /api/v1/realtime/start。BFF 不自行管理 pipeline 子进程。"""
        payload = payload or {}
        stdout: list[str] = []
        stderr: list[str] = []

        if bool(payload.get("restart")):
            message = (
                "web_app_service cannot restart itself from /realtime/collector/start; "
                "run scripts/start_new_chain_stack.sh --restart outside the service"
            )
            return self._cmd_result(False, "", message, ["web_app_service:realtime_stack", "start"], 2)

        async with self._start_lock:
            if not await self._is_http_healthy(f"http://127.0.0.1:{self._sps_port}/healthz"):
                ok, msg = await self._start_sps()
                stdout.append(msg if ok else "")
                stderr.append("" if ok else msg)
                if not ok:
                    return self._cmd_result(
                        False,
                        "\n".join(filter(None, stdout)),
                        "\n".join(filter(None, stderr)),
                        ["bff", "start_sps"],
                        1,
                    )

            try:
                async with httpx.AsyncClient(timeout=90.0, trust_env=False) as client:
                    r = await client.get(f"http://127.0.0.1:{self._sps_port}/api/v1/realtime/start")
                    data = r.json()
            except Exception as exc:
                return self._cmd_result(
                    False,
                    "\n".join(filter(None, stdout)),
                    f"SPS realtime start failed: {exc}",
                    ["bff", "sps_start"],
                    1,
                )

            ok = r.status_code == 200 and data.get("ok") is True
            return self._cmd_result(
                ok,
                "\n".join(filter(None, stdout + [json.dumps(data, ensure_ascii=False, indent=2)])),
                "" if ok else json.dumps(data, ensure_ascii=False, indent=2),
                ["bff", "sps", "realtime/start"],
                0 if ok else 1,
            )

    async def stop(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """同步代理 SPS /api/v1/realtime/stop。BFF 不自行管理 pipeline 子进程。"""
        payload = payload or {}
        force = bool(payload.get("force"))
        stop_sps = bool(payload.get("stop_sps") or force)
        with_frontend = bool(payload.get("with_frontend"))
        stdout: list[str] = []
        stderr: list[str] = []

        if not await self._is_http_healthy(f"http://127.0.0.1:{self._sps_port}/healthz"):
            if stop_sps:
                # SPS unreachable — try force stop by killing port
                ok_sps, msg_sps = await self._stop_sps(force=force)
                stdout.append(msg_sps if ok_sps else "")
                stderr.append("" if ok_sps else msg_sps)
            if with_frontend:
                ok_fe, msg_fe = await self._stop_frontend(force=force)
                stdout.append(msg_fe if ok_fe else "")
                stderr.append("" if ok_fe else msg_fe)
            return self._cmd_result(
                bool(force),  # force stop is best-effort
                "\n".join(filter(None, stdout)),
                "\n".join(filter(None, stderr)),
                ["bff", "sps", "realtime/stop"],
                0 if force else 1,
            )

        try:
            async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
                r = await client.get(f"http://127.0.0.1:{self._sps_port}/api/v1/realtime/stop")
                data = r.json()
        except Exception as exc:
            return self._cmd_result(
                False,
                "",
                f"SPS realtime stop failed: {exc}",
                ["bff", "sps_stop"],
                1,
            )

        ok = r.status_code == 200 and data.get("ok") is True

        if stop_sps:
            ok_sps, msg_sps = await self._stop_sps(force=force)
            stdout.append(msg_sps if ok_sps else "")
            stderr.append("" if ok_sps else msg_sps)

        if with_frontend:
            ok_fe, msg_fe = await self._stop_frontend(force=force)
            stdout.append(msg_fe if ok_fe else "")
            stderr.append("" if ok_fe else msg_fe)

        return self._cmd_result(
            ok,
            "\n".join(filter(None, stdout + [json.dumps(data, ensure_ascii=False, indent=2)])),
            "" if ok else json.dumps(data, ensure_ascii=False, indent=2),
            ["bff", "sps", "realtime/stop"],
            0 if ok else 1,
        )

    async def logs(self, *, lines: int = 200, max_age_minutes: int = 180) -> dict[str, Any]:
        lines = max(20, min(int(lines), 2000))
        max_age_minutes = max(10, min(int(max_age_minutes), 1440))
        files = [
            self._log_dir / "stock_processing_service_8090.log",
            self._log_dir / "web_app_service_8000.log",
            self._log_dir / "frontend_vite.log",
            self._log_dir / "frontend_5173.log",
        ]
        cutoff_ts = time.time() - (max_age_minutes * 60)
        payload: dict[str, list[str]] = {}
        for file_path in files:
            payload[file_path.name] = self._read_recent_lines(file_path, lines=lines, cutoff_ts=cutoff_ts)
        return {
            "log_dir": str(self._log_dir),
            "lines": lines,
            "max_age_minutes": max_age_minutes,
            "files": payload,
        }

    async def _start_sps(self) -> tuple[bool, str]:
        python = self._resolve_sps_python()
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_file = self._log_dir / "stock_processing_service_8090.log"
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": str(self._project_root),
                "HF_HUB_OFFLINE": "1",
                "PYTHON_CMD": python,
                "CONDA_PYTHON_CMD": python,
                "SPS_RUNTIME_PROFILE": env.get("SPS_RUNTIME_PROFILE", "sps-conda-ml"),
                "REDIS_URL": env.get("REDIS_URL", "redis://localhost:6379/0"),
            }
        )
        log_fd = open(log_file, "a")
        try:
            self._sps_process = subprocess.Popen(
                [
                    python,
                    "-m",
                    "uvicorn",
                    "stock_processing_service.api_app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self._sps_port),
                ],
                cwd=str(self._project_root),
                env=env,
                stdout=log_fd,
                stderr=log_fd,
                start_new_session=True,
            )
        except Exception as exc:
            log_fd.close()
            return False, f"[fail] stock_processing_service spawn failed: {exc}"

        deadline = time.time() + 30
        while time.time() < deadline:
            if self._sps_process.poll() is not None:
                log_fd.close()
                return False, f"[fail] stock_processing_service exited with code {self._sps_process.returncode}"
            if await self._is_http_healthy(f"http://127.0.0.1:{self._sps_port}/healthz"):
                return True, f"[ok] stock_processing_service:{self._sps_port} ready"
            await asyncio.sleep(1)
        await self._terminate_process_group(self._sps_process)
        self._sps_process = None
        log_fd.close()
        return False, "[fail] stock_processing_service did not become healthy within 30s"

    async def _start_frontend(self) -> tuple[bool, str]:
        frontend_dir = self._project_root / "frontend"
        if not (frontend_dir / "package.json").exists():
            return False, "[warn] frontend package.json missing"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_fd = open(self._log_dir / "frontend_vite.log", "a")
        try:
            self._frontend_process = subprocess.Popen(
                ["npm", "run", "dev", "--", "--host"],
                cwd=str(frontend_dir),
                env=os.environ.copy(),
                stdout=log_fd,
                stderr=log_fd,
                start_new_session=True,
            )
        except Exception as exc:
            log_fd.close()
            return False, f"[warn] frontend spawn failed: {exc}"
        return True, "[start] frontend vite requested"

    async def _stop_sps(self, *, force: bool) -> tuple[bool, str]:
        if self._sps_process and self._sps_process.poll() is None:
            await self._terminate_process_group(self._sps_process)
            self._sps_process = None
            return True, f"[ok] stopped managed stock_processing_service:{self._sps_port}"
        if not await self._is_http_healthy(f"http://127.0.0.1:{self._sps_port}/healthz"):
            return True, f"[skip] stock_processing_service:{self._sps_port} already stopped"
        if not force:
            return True, f"[skip] stock_processing_service:{self._sps_port} is external; not stopped"
        killed = await asyncio.to_thread(self._kill_port_blocking, self._sps_port)
        return (True, f"[ok] force-stopped stock_processing_service:{self._sps_port}") if killed else (False, f"[fail] could not force-stop port {self._sps_port}")

    async def _stop_frontend(self, *, force: bool) -> tuple[bool, str]:
        if self._frontend_process and self._frontend_process.poll() is None:
            await self._terminate_process_group(self._frontend_process)
            self._frontend_process = None
            return True, "[ok] stopped managed frontend vite"
        if not force:
            return True, "[skip] frontend vite is external or stopped; not stopped"
        killed = await asyncio.to_thread(self._kill_port_blocking, 5173)
        return (True, "[ok] force-stopped frontend vite") if killed else (True, "[skip] no frontend vite listener on 5173")

    async def _is_http_healthy(self, url: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=2.0, trust_env=False) as http:
                resp = await http.get(url)
            return resp.status_code == 200
        except Exception:
            return False

    async def _terminate_process_group(self, proc: subprocess.Popen) -> None:
        pid = proc.pid
        if not pid:
            return
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            for _ in range(5):
                if proc.poll() is not None:
                    return
                await asyncio.sleep(0.5)
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            return

    def _kill_port_blocking(self, port: int) -> bool:
        try:
            out = subprocess.run(
                ["lsof", "-t", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            pids = [int(x) for x in out.stdout.split() if x.isdigit()]
            for pid in pids:
                os.kill(pid, signal.SIGTERM)
            time.sleep(1)
            for pid in pids:
                try:
                    os.kill(pid, 0)
                except OSError:
                    continue
                os.kill(pid, signal.SIGKILL)
            return bool(pids)
        except Exception:
            return False

    def _resolve_sps_python(self) -> str:
        env_python = os.getenv("SPS_PYTHON", "").strip()
        candidates = [Path(env_python)] if env_python else []
        candidates.append(Path("/opt/miniconda3/envs/theme_matcher_env/bin/python"))
        if os.getenv("ALLOW_SPS_VENV_FALLBACK", "").lower() in {"1", "true", "yes", "on"}:
            candidates.append(self._project_root / ".venv" / "bin" / "python")
        for path in candidates:
            if path and path.exists():
                return str(path)
        attempted = ", ".join(str(path) for path in candidates if path)
        raise FileNotFoundError(
            "SPS python not found. Set SPS_PYTHON to the theme_matcher_env python "
            f"or ALLOW_SPS_VENV_FALLBACK=1 for local diagnostics. attempted={attempted}"
        )

    def _read_recent_lines(self, file_path: Path, *, lines: int, cutoff_ts: float) -> list[str]:
        if not file_path.exists():
            return []
        try:
            raw = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            recent = raw[-max(lines * 4, lines):]
            filtered = [row for row in recent if self._line_timestamp(row) is None or self._line_timestamp(row) >= cutoff_ts]
            if not filtered and file_path.stat().st_mtime < cutoff_ts:
                stale_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(file_path.stat().st_mtime))
                filtered = [f"[stale] 日志文件最近更新时间: {stale_time}，当前未检测到最新日志输出"]
            return filtered[-lines:]
        except Exception as exc:
            return [f"[error] {exc}"]

    def _line_timestamp(self, line: str) -> float | None:
        text = (line or "").strip()
        if len(text) < 19:
            return None
        try:
            return time.mktime(time.strptime(text[:19], "%Y-%m-%d %H:%M:%S"))
        except ValueError:
            return None

    def _cmd_result(self, ok: bool, stdout: str, stderr: str, command: list[str], return_code: int) -> dict[str, Any]:
        return {
            "ok": ok,
            "return_code": return_code,
            "stdout": stdout,
            "stderr": stderr,
            "command": command,
        }


def _pid_alive(pid: int) -> bool:
    """检查进程是否存活。"""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False

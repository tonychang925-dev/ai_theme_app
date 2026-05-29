"""New-chain realtime stack lifecycle owned by web_app_service.

This manager intentionally does not start or restart web_app_service itself.
Calls arrive through web_app_service, so restarting the current process from
inside the request would sever the management channel.
"""

from __future__ import annotations

import asyncio
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
        # 直接管理的实时采集子进程（不依赖 SPS）
        self._raw_process: subprocess.Popen | None = None
        self._decision_process: subprocess.Popen | None = None
        self._pipeline_run_id: str = ""
        self._pipeline_start_task: asyncio.Task | None = None
        self._start_lock = asyncio.Lock()

    async def status(self) -> dict[str, Any]:
        """代理 SPS 的 /api/v1/realtime/status，返回前端需要的结构化数据。"""
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
                r = await client.get(f"http://127.0.0.1:{self._sps_port}/api/v1/realtime/status")
                if r.status_code == 200:
                    return r.json()
        except Exception:
            pass
        # fallback: 返回默认结构
        return {"running": False, "raw_news_pid": None, "decision_pid": None,
                "pending_count": 0, "dead_letter_count": 0, "run_id": "",
                "profile_version": "?", "profile_status": "?", "last_error": "SPS unreachable"}

    async def start(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if bool(payload.get("restart")):
            message = (
                "web_app_service cannot restart itself from /realtime/collector/start; "
                "run scripts/start_new_chain_stack.sh --restart outside the service"
            )
            return self._cmd_result(False, "", message, ["web_app_service:realtime_stack", "start"], 2)

        async with self._start_lock:
            stdout: list[str] = []
            stderr: list[str] = []

            if await self._is_http_healthy(f"http://127.0.0.1:{self._sps_port}/healthz"):
                stdout.append(f"[ok] stock_processing_service:{self._sps_port} already running")
            else:
                ok, msg = await self._start_sps()
                stdout.append(msg if ok else "")
                stderr.append("" if ok else msg)
                if not ok:
                    return self._cmd_result(False, "\n".join(filter(None, stdout)), "\n".join(filter(None, stderr)), ["web_app_service:realtime_stack", "start"], 1)

            # 异步触发 SPS 启动实时管线（不阻塞按钮响应），保存引用以便 stop 时取消
            if self._pipeline_start_task and not self._pipeline_start_task.done():
                stdout.append("[ok] realtime pipeline start already pending")
            else:
                self._pipeline_start_task = asyncio.create_task(
                    self._trigger_sps_start(stdout, stderr)
                )

            if bool(payload.get("with_frontend")):
                ok, msg = await self._start_frontend()
                stdout.append(msg if ok else "")
                stderr.append("" if ok else msg)

            return self._cmd_result(True, "\n".join(filter(None, stdout)) + "\n", "\n".join(filter(None, stderr)), ["web_app_service:realtime_stack", "start"], 0)

    async def stop(self, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        """停止实时 pipeline（默认）或 SPS 进程（force=true）。

        - 默认行为：取消 pending start task + 调用 SPS /api/v1/realtime/stop
        - force=true 或 stop_sps=true：停止 SPS 进程
        - 不默认杀 SPS，因为 SPS 还承载其他功能（SSE、decision API 等）
        """
        payload = payload or {}
        stdout: list[str] = []
        stderr: list[str] = []
        force = bool(payload.get("force"))
        stop_sps = bool(payload.get("stop_sps") or force)
        with_frontend = bool(payload.get("with_frontend"))

        # 1. 取消 pending start task
        if self._pipeline_start_task and not self._pipeline_start_task.done():
            self._pipeline_start_task.cancel()
            stdout.append("[ok] cancelled pending realtime pipeline start task")
            self._pipeline_start_task = None

        # 2. 先尝试通过 SPS HTTP 停止 pipeline
        ok_pipeline = True
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=15.0, trust_env=False) as _client:
                r = await _client.get(f"http://127.0.0.1:{self._sps_port}/api/v1/realtime/stop")
                if r.status_code == 200:
                    data = r.json()
                    stdout.append(f"[ok] SPS pipeline stop: {data.get('status', r.status_code)}")
                else:
                    ok_pipeline = False
                    stderr.append(f"[warn] SPS stop returned {r.status_code}")
        except Exception as exc:
            ok_pipeline = False
            stderr.append(f"[warn] SPS stop failed (SPS may be down): {exc}")

        # 3. 直接杀 pidfile 进程（兜底，SPS 不可达或返回错误时用）
        pf_result = None
        if not ok_pipeline:
            pf_result = await self.stop_pipeline()
            stdout.append(f"direct pidfile kill: status={pf_result.get('status')} killed={pf_result.get('killed')}")

        # 判断 pipeline 是否真正停止
        pipeline_stopped = ok_pipeline or (
            pf_result is not None
            and pf_result.get("status") == "stopped"
            and bool(pf_result.get("killed"))
        )
        if not pipeline_stopped:
            stderr.append("[fail] realtime pipeline not stopped: SPS stop failed and no pidfile process killed")

        # 4. 仅 force/stop_sps 时停止 SPS 进程
        if stop_sps:
            ok_sps, msg_sps = await self._stop_sps(force=force)
            stdout.append(msg_sps if ok_sps else "")
            stderr.append("" if ok_sps else msg_sps)

        if with_frontend:
            ok_frontend, msg_frontend = await self._stop_frontend(force=force)
            stdout.append(msg_frontend if ok_frontend else "")
            stderr.append("" if ok_frontend else msg_frontend)

        ok = pipeline_stopped and not any(stderr)
        return self._cmd_result(ok, "\n".join(filter(None, stdout)) + "\n", "\n".join(filter(None, stderr)), ["web_app_service:realtime_stack", "stop"], 0 if ok else 1)

    async def stop_pipeline(self) -> dict[str, Any]:
        """直接停止实时采集子进程（读 pidfile，不依赖 SPS）。

        实时子进程已通过 start_new_session=True 从 SPS 剥离，
        SPS 重启/停止不会带着它们一起退出。此方法直接根据 runtime
        pidfiles 找到进程并发送 SIGTERM/SIGKILL。

        会按顺序尝试多个 log 目录：REALTIME_LOG_DIR > BFF默认 > SPS默认。
        """
        import json as _json

        # 按优先级尝试多个 runtime 目录（SPS 和 BFF 可能用不同的 log dir）
        candidate_dirs = [self._log_dir]
        sps_default = self._project_root / "logs" / "realtime"
        if sps_default != self._log_dir:
            candidate_dirs.append(sps_default)

        runtime_dir = None
        stack_json = None
        run_id = ""
        killed: list[str] = []
        errors: list[str] = []

        for log_dir in candidate_dirs:
            rt_dir = log_dir / "runtime"
            sj = rt_dir / "realtime_stack.json"
            if sj.exists():
                runtime_dir = rt_dir
                stack_json = sj
                try:
                    meta = _json.loads(sj.read_text(encoding="utf-8"))
                    run_id = str(meta.get("run_id") or "")
                except Exception:
                    pass
                if run_id:
                    break

        if not run_id or not runtime_dir:
            tried = [str(d / "runtime") for d in candidate_dirs]
            return {"ok": True, "status": "no_pidfile", "killed": [], "message": f"没有找到运行中的实时采集 pidfile。尝试了: {tried}"}

        # 所有可能的子进程前缀
        prefixes = [
            "raw_news", "decision", "akshare", "rebuild",
            "intel_producer", "intel_collection", "db_collector",
        ]

        for prefix in prefixes:
            pidfile = runtime_dir / f"{prefix}_{run_id}.pid"
            pid = None
            try:
                pid = int(pidfile.read_text().strip())
            except Exception:
                continue

            if not _pid_alive(pid):
                # 清理僵尸 pidfile
                try:
                    pidfile.unlink()
                except OSError:
                    pass
                continue

            # SIGTERM
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError) as exc:
                errors.append(f"{prefix}(pid={pid}): {exc}")
                continue

            killed.append(f"{prefix}(pid={pid})")

        # 等 1 秒后 SIGKILL 还活着的
        await asyncio.sleep(1)
        for prefix in prefixes:
            pidfile = runtime_dir / f"{prefix}_{run_id}.pid"
            try:
                pid = int(pidfile.read_text().strip())
            except Exception:
                continue

            if _pid_alive(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass

            # 清理 pidfile
            try:
                pidfile.unlink()
            except OSError:
                pass

        # 标记 stack 已停止
        if stack_json.exists():
            try:
                meta = _json.loads(stack_json.read_text(encoding="utf-8")) if stack_json.exists() else {}
            except Exception:
                meta = {}
            meta["stopped_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
            meta["stopped_by"] = "web_app_service"
            try:
                stack_json.write_text(_json.dumps(meta, ensure_ascii=False, indent=2))
            except OSError:
                pass

        return {
            "ok": True,
            "status": "stopped",
            "killed": killed,
            "errors": errors,
            "run_id": run_id,
        }

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

    async def _trigger_sps_start(self, stdout: list, stderr: list) -> None:
        """异步触发 SPS 启动管线，不阻塞按钮响应。"""
        await asyncio.sleep(3)  # 等 SPS 完全就绪
        try:
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=30.0, trust_env=False) as _client:
                r = await _client.get(f"http://127.0.0.1:{self._sps_port}/api/v1/realtime/start")
                if r.status_code == 200:
                    stdout.append("[ok] realtime pipeline started")
                else:
                    stderr.append(f"[warn] SPS start returned {r.status_code}")
        except Exception as exc:
            stderr.append(f"[warn] SPS start failed: {exc}")

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

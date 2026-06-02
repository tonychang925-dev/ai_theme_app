"""P2-B-4: JYHF 竞价采集器生命周期管理 — 集成到 web_app_service."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from collections import deque
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("web_app.auction_manager")

TZ_CN = timezone(timedelta(hours=8))


class JyhfAuctionManager:
    """管理竞价采集器子进程生命周期。"""

    def __init__(self, project_root: str):
        self._project_root = str(project_root)
        self._process: subprocess.Popen | None = None
        self._task: asyncio.Task | None = None
        self._status: dict = {
            "running": False,
            "state": "idle",       # idle | waiting_auction | collecting | finished | error
            "started_at": None,
            "trade_date": None,
            "candidate_date": None,
            "rounds": 0,
            "points": 0,
            "pid": None,
            "last_error": None,
        }
        self._log_lines: deque[str] = deque(maxlen=2000)  # stdout 行环形缓冲

    def status(self) -> dict:
        return dict(self._status)

    def get_logs(self, lines: int = 200) -> dict:
        """返回最近 N 行 stdout 日志（环形缓冲）。"""
        n = max(20, min(int(lines), 2000))
        buf = list(self._log_lines)
        return {"lines": buf[-n:]}

    async def start(self, trade_date: str, candidate_date: str) -> dict:
        # P0-A1: 检查旧进程是否仍存活，防止僵尸
        if self._process is not None:
            rc = self._process.poll()
            if rc is None:
                return {"ok": True, "message": "already running", **self._status}
            else:
                # 旧进程已死，清理状态
                logger.warning("Auction collector was dead (rc=%s), restarting", rc)
                self._status["running"] = False
                self._status["pid"] = None
                self._process = None

        self._status["running"] = True
        self._status["state"] = "starting"
        self._status["trade_date"] = trade_date
        self._status["candidate_date"] = candidate_date
        self._status["started_at"] = datetime.now(TZ_CN).isoformat()
        self._task = asyncio.create_task(self._run_subprocess(trade_date, candidate_date))
        return {"ok": True, "message": "auction collector starting", **self._status}

    async def stop(self) -> dict:
        self._status["state"] = "stopping"
        # P0-A1: 杀前验证 PID 存活，避免误杀
        if self._process and self._process.poll() is None:
            pid = self._process.pid
            try:
                os.kill(pid, 0)  # 信号 0 只检查存活
                self._process.terminate()
                await asyncio.sleep(1)
                if self._process.poll() is None:
                    self._process.kill()
            except OSError:
                logger.warning("Auction collector PID %s already dead", pid)
            except Exception as exc:
                logger.warning("Auction collector kill failed: %s", exc)
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._status["running"] = False
        self._status["state"] = "stopped"
        self._status["pid"] = None
        return {"ok": True, "message": "auction collector stopped", **self._status}

    async def _run_subprocess(self, trade_date: str, candidate_date: str) -> None:
        try:
            # 解析 Python 路径
            python = os.environ.get("PYTHON") or os.environ.get("CONDA_PYTHON") or sys.executable

            cmd = [
                python, "-m", "stock_processing_service.collectors.jyhf_auction_collector",
                "--trade-date", trade_date,
                "--candidate-date", candidate_date,
                "--interval", "3.0",
                "--concurrency", "15",
                "--parent-pid", str(os.getpid()),  # P0-A1: watchdog 守护
            ]
            logger.info("Auction collector: %s", " ".join(cmd))
            logger.info("Auction collector python: %s (cwd=%s)", python, self._project_root)
            self._log_lines.append(f"[manager] spawning: {' '.join(cmd)}")
            self._log_lines.append(f"[manager] python={python} cwd={self._project_root}")

            self._process = await asyncio.to_thread(
                subprocess.Popen,
                cmd,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=self._project_root,
                text=True,
                start_new_session=True,
            )
            self._status["pid"] = self._process.pid
            self._status["state"] = "waiting_auction"

            # 读取 stdout 更新状态（每行通过 asyncio.to_thread 读取，避免同步 I/O 阻塞事件循环）
            while True:
                try:
                    line = await asyncio.to_thread(self._process.stdout.readline)
                except (ValueError, OSError):
                    break  # stdout pipe closed
                if not line:
                    break   # EOF
                line = line.strip()
                if not line:
                    continue
                # 尝试解析 JSON stats
                if line.startswith("{"):
                    try:
                        stats = json.loads(line)
                        self._status["rounds"] = stats.get("rounds", 0)
                        self._status["points"] = stats.get("points_collected", 0)
                        if stats.get("finished_at"):
                            self._status["state"] = "finished"
                    except json.JSONDecodeError:
                        pass

                if "Auction collector finished" in line:
                    self._status["state"] = "finished"
                elif "collecting" in line.lower() or "Round" in line:
                    self._status["state"] = "collecting"

                logger.debug("Auction: %s", line[:200])
                self._log_lines.append(line)

            self._process.wait()
            self._status["running"] = False
            if self._status["state"] not in ("finished", "error"):
                self._status["state"] = "finished"
            logger.info("Auction collector exited (rc=%s)", self._process.returncode)
            self._log_lines.append(f"[manager] subprocess exited (rc={self._process.returncode})")

        except asyncio.CancelledError:
            self._status["state"] = "stopped"
        except Exception as exc:
            self._status["state"] = "error"
            self._status["last_error"] = str(exc)
            logger.exception("Auction collector error: %s", exc)

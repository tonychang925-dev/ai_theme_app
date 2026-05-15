from __future__ import annotations

import os
import signal
import traceback

from fastapi import FastAPI, Query

from services.jyhf_cdp_service.config import load_config
from services.jyhf_cdp_service.logging_config import setup_logger
from services.jyhf_cdp_service.schemas import CommandResult, LogsResponse
from services.jyhf_cdp_service.service import JyhfCdpCollectorService


config = load_config()
logger = setup_logger(config.log_path)

# 信号捕获：记录谁杀了 CDP
def _on_signal(signum, frame):
    pid = os.getpid()
    ppid = os.getppid()
    stack = "".join(traceback.format_stack(frame, limit=8))
    logger.critical(
        "CDP PID=%s PPID=%s received signal %s. Stack:\n%s",
        pid, ppid, signum, stack,
    )
    # Re-raise default handler after logging
    signal.signal(signum, signal.SIG_DFL)
    os.kill(pid, signum)

signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT, _on_signal)

collector = JyhfCdpCollectorService(config=config, logger=logger)

app = FastAPI(title="jyhf_cdp_service", version="0.1.0")

# Boot log: capture PID/PPID/PGID immediately for diagnostics
logger.warning(
    "CDP_SERVICE_BOOT pid=%s ppid=%s pgid=%s port=%s",
    os.getpid(), os.getppid(), os.getpgid(os.getpid()), config.port,
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "jyhf_cdp_service"}


@app.get("/status")
async def status() -> dict:
    return collector.status().model_dump()


@app.post("/collector/start")
async def start_collector() -> CommandResult:
    await collector.start()
    return CommandResult(ok=True, message="collector started", stdout="collector started", command=["POST", "/collector/start"])


@app.post("/collector/stop")
async def stop_collector() -> CommandResult:
    await collector.stop()
    return CommandResult(ok=True, message="collector stopped", stdout="collector stopped", command=["POST", "/collector/stop"])


@app.post("/collector/restart")
async def restart_collector() -> CommandResult:
    await collector.stop()
    await collector.start()
    return CommandResult(ok=True, message="collector restarted", stdout="collector restarted", command=["POST", "/collector/restart"])


@app.get("/collector/logs")
async def logs(lines: int = Query(default=300, ge=20, le=2000)) -> LogsResponse:
    return LogsResponse(log_file=str(config.log_path), lines=collector.logs(lines=lines))

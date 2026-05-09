from __future__ import annotations

from fastapi import FastAPI, Query

from services.jyhf_cdp_service.config import load_config
from services.jyhf_cdp_service.logging_config import setup_logger
from services.jyhf_cdp_service.schemas import CommandResult, LogsResponse
from services.jyhf_cdp_service.service import JyhfCdpCollectorService


config = load_config()
logger = setup_logger(config.log_path)
collector = JyhfCdpCollectorService(config=config, logger=logger)

app = FastAPI(title="jyhf_cdp_service", version="0.1.0")


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

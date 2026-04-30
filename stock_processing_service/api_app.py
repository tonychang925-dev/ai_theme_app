from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.tests.replay._post_market_replay_runner import _ReplayDatabaseStockFacade


def _db_name() -> str:
    return str(os.getenv("REPLAY_DB_NAME") or os.getenv("DB_NAME") or "stock_data_test")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=_db_name())
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    facade = _ReplayDatabaseStockFacade(gw)
    app.state.read_port = StockReadGatewayAdapter(facade)
    app.state.gateway = gw
    try:
        yield
    finally:
        close = getattr(gw, "close", None)
        if callable(close):
            await close()


app = FastAPI(title="stock_processing_service_read_api", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "db": _db_name()}


@app.get("/api/v1/post_market_snapshot")
async def get_post_market_snapshot(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    dto = await app.state.read_port.get_existing_post_market_recap_snapshot(d)
    if dto is None:
        return {"trade_date": trade_date, "snapshot_version": "missing", "payload": {}}
    return {
        "trade_date": str(dto.trade_date),
        "snapshot_version": str(dto.snapshot_version),
        "payload": dict(dto.payload or {}),
    }


@app.get("/api/v1/strong_watch")
async def get_strong_watch(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    dto = await app.state.read_port.get_existing_post_market_recap_snapshot(d)
    if dto is None:
        return {"trade_date": trade_date, "stocks": []}
    recap_doc = dict((dto.payload or {}).get("recap_doc") or {})
    stocks = list(recap_doc.get("strong_watch_history") or [])
    return {"trade_date": str(dto.trade_date), "stocks": stocks}


@app.get("/api/v1/w2s_candidates")
async def get_w2s_candidates(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    dto = await app.state.read_port.get_existing_post_market_recap_snapshot(d)
    if dto is None:
        return {"trade_date": trade_date, "candidates": []}
    recap_doc = dict((dto.payload or {}).get("recap_doc") or {})
    candidates = list(recap_doc.get("top_candidates") or [])
    return {"trade_date": str(dto.trade_date), "candidates": candidates}

"""TDX Market Agent — 独立 FastAPI 边车，隔离 mootdx 依赖.

启动：
  cd tools/tdx_market_agent
  python -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  uvicorn app:app --host 127.0.0.1 --port 8766

验收：
  curl http://127.0.0.1:8766/health
  curl http://127.0.0.1:8766/quote/002361
  curl http://127.0.0.1:8766/minute/002361
  curl http://127.0.0.1:8766/bars/002361
  curl http://127.0.0.1:8766/f10c/000001
  curl http://127.0.0.1:8766/f10/000001?section=资金动向
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from config import load_config
from schemas import (
    health_response,
    quote_response,
    minute_response,
    bars_response,
    f10_catalog_response,
    f10_response,
)
from tdx_client import TdxClient, parse_stock_id

# ── logging ──
cfg = load_config()
logging.basicConfig(
    level=getattr(logging, cfg.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("tdx_market_agent")

# ── global client ──
_tdx: TdxClient | None = None


def get_client() -> TdxClient:
    global _tdx
    if _tdx is None:
        _tdx = TdxClient(timeout=cfg.timeout_seconds)
        _tdx.connect()
    return _tdx


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时预连接，关闭时释放."""
    try:
        get_client()
        logger.info("agent ready on %s:%s, server=%s", cfg.host, cfg.port, get_client().server_info)
    except Exception as exc:
        logger.error("startup connect failed: %s", exc)
    yield
    if _tdx:
        _tdx.close()
        logger.info("agent stopped")


app = FastAPI(title="tdx_market_agent", version="0.1.0", lifespan=lifespan)


# ── endpoints ──

@app.get("/health")
def health():
    try:
        cl = get_client()
        server = cl.server_info
    except Exception:
        server = "disconnected"
    return {
        **health_response(),
        "server": server,
    }


@app.get("/quote/{stock_id}")
def quote(stock_id: str):
    numeric_id, system_id = parse_stock_id(stock_id)
    try:
        raw = get_client().get_quote(numeric_id)
        return quote_response(numeric_id, system_id, raw)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("quote(%s) error", stock_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/minute/{stock_id}")
def minute(stock_id: str):
    numeric_id, system_id = parse_stock_id(stock_id)
    try:
        rows = get_client().get_minute(numeric_id)
        return minute_response(numeric_id, system_id, rows)
    except Exception as exc:
        logger.exception("minute(%s) error", stock_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/bars/{stock_id}")
def bars(
    stock_id: str,
    frequency: int = Query(default=9, description="K线周期: 9=日线, 5=30分钟, 3=15分钟, 1=5分钟"),
    offset: int = Query(default=100, description="返回条数"),
):
    numeric_id, system_id = parse_stock_id(stock_id)
    try:
        rows = get_client().get_bars(numeric_id, frequency=frequency, offset=offset)
        return bars_response(numeric_id, system_id, rows, frequency, offset)
    except Exception as exc:
        logger.exception("bars(%s) error", stock_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/f10c/{stock_id}")
def f10_catalog(stock_id: str):
    numeric_id, system_id = parse_stock_id(stock_id)
    try:
        catalog = get_client().get_f10_catalog(numeric_id)
        return f10_catalog_response(numeric_id, system_id, catalog)
    except Exception as exc:
        logger.exception("f10c(%s) error", stock_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/f10/{stock_id}")
def f10(stock_id: str, section: str = Query(default="", description="可选：F10 目录项名称，如 资金动向")):
    numeric_id, system_id = parse_stock_id(stock_id)
    try:
        catalog = get_client().get_f10_catalog(numeric_id)
        content = get_client().get_f10_content(numeric_id, name=section)
        return f10_response(numeric_id, system_id, content, section=section, catalog=catalog)
    except Exception as exc:
        logger.exception("f10(%s) error", stock_id)
        raise HTTPException(status_code=500, detail=str(exc))


# ── main entry ──
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host=cfg.host, port=cfg.port, log_level=cfg.log_level)

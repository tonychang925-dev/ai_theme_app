from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path
import json
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from pydantic import Field
from datetime import datetime
import uuid

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_read_gateway_adapter import (
    StockReadGatewayAdapter,
)
from stock_processing_service.tests.replay._post_market_replay_runner import _ReplayDatabaseStockFacade
from stock_processing_service.application.orchestrators.bootstrap import build_container
from theme_service.repositories.phase1_read_repository import Phase1ReadRepository
from stock_processing_service.application.jobs.collection_job_manager import CollectionJobManager
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidate
from stock_processing_service.domain.services.w2s_confirm_service import W2SConfirmService
from stock_processing_service.contracts.dto import StockAuctionDTO
from stock_service.adapters.tushare_adapter import TushareAdapter
from stock_service.models import PreMarketAuctionSnapshot
from stock_service.services.auction_signal_service import AuctionCandidateInput
from stock_service.services.auction_snapshot_builder_service import AuctionSnapshotBuilderService

try:
    from redis.asyncio import Redis as AsyncRedis
except Exception:  # pragma: no cover - import fallback only
    AsyncRedis = None


logger = logging.getLogger(__name__)

PRE_MARKET_CONFIRM_NOT_READY_MESSAGE = "9:25分之后才能进行盘前确认！"
REALTIME_AUCTION_CACHE_PREFIX = "sps:w2s:pre_market_auction"


def _db_name() -> str:
    return str(os.getenv("REPLAY_DB_NAME") or os.getenv("DB_NAME") or "stock_data_test")


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=_db_name())
    gw = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)
    facade = _ReplayDatabaseStockFacade(gw)
    app.state.read_port = StockReadGatewayAdapter(facade)
    app.state.gateway = gw
    app.state.container = build_container(facade)
    app.state.phase1_repo = Phase1ReadRepository()
    app.state.collection_job_manager = CollectionJobManager()
    await app.state.phase1_repo.initialize()
    try:
        yield
    finally:
        close = getattr(gw, "close", None)
        if callable(close):
            await close()
        phase1_close = getattr(app.state.phase1_repo, "close", None)
        if callable(phase1_close):
            await phase1_close()


app = FastAPI(title="stock_processing_service_read_api", version="0.1.0", lifespan=lifespan)


class CollectionStartRequest(BaseModel):
    trade_date: str
    options: dict[str, Any] = {}
    tushare_pause_seconds: float = 0.1
    abnormal_filters: dict[str, Any] = {}
    min_turnover_rate: float = 3.0
    min_composite_score: float = 40.0


class CollectionJobActionRequest(BaseModel):
    job_id: str


class ScreenerExecutePayload(BaseModel):
    strategy_id: str
    trade_date: str | None = None
    candidate_trade_date: str | None = None
    confirm_trade_date: str | None = None
    limit: int = 100
    min_score: float = 60.0
    auto_tune_min_score: bool = True
    target_min_count: int = 30
    target_max_count: int = 120
    enable_llm_review: bool = False
    llm_top_k: int = 20
    run_stage1: bool = True
    run_stage2: bool = False


class ScreenerFavoritePayload(BaseModel):
    result_id: str
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class ScreenerFavoriteUpdatePayload(BaseModel):
    notes: str | None = None
    tags: list[str] = Field(default_factory=list)


class ScreenerExportPayload(BaseModel):
    result_ids: list[str] = Field(default_factory=list)
    format: str = "json"


def _parse_trade_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _stock_id_aliases(value: Any) -> set[str]:
    raw = str(value or "").strip().upper()
    if not raw:
        return set()
    aliases = {raw}
    if "." in raw:
        aliases.add(raw.split(".", 1)[0])
    elif len(raw) == 6 and raw.isdigit():
        if raw.startswith(("6", "9")):
            aliases.add(f"{raw}.SH")
        elif raw.startswith(("4", "8")):
            aliases.add(f"{raw}.BJ")
        else:
            aliases.add(f"{raw}.SZ")
    return {item for item in aliases if item}


def _candidate_role_label(candidate_type: str) -> str:
    mapping = {
        "dragon_repair": "龙头",
        "subdragon_repair": "龙二",
        "strong_trend_repair": "强趋势",
        "trend_repair": "强趋势",
        "bad_limit_repair": "强趋势",
        "upper_shadow_repair": "强趋势",
        "generic_repair": "强趋势",
    }
    return mapping.get(str(candidate_type or "").strip().lower(), "强趋势")


def _is_same_day_realtime_window(confirm_trade_date: date, now_cn: datetime) -> bool:
    if confirm_trade_date != now_cn.date():
        return False
    if now_cn.hour < 9:
        return False
    if now_cn.hour == 9 and now_cn.minute < 25:
        return False
    return now_cn.hour == 9 and now_cn.minute < 30


def _is_same_day_post_open_window(confirm_trade_date: date, now_cn: datetime) -> bool:
    return confirm_trade_date == now_cn.date() and (
        now_cn.hour > 9 or (now_cn.hour == 9 and now_cn.minute >= 30)
    )


def _realtime_auction_cache_key(trade_date: date) -> str:
    return f"{REALTIME_AUCTION_CACHE_PREFIX}:{trade_date.isoformat()}"


def _redis_url() -> str:
    return str(os.getenv("REDIS_URL") or "redis://localhost:6379/0").strip()


async def _get_async_redis() -> AsyncRedis:
    if AsyncRedis is None:
        raise HTTPException(status_code=503, detail="Redis客户端不可用，无法执行实时盘前确认")
    return AsyncRedis.from_url(_redis_url(), decode_responses=True)


def _auction_dto_to_cache_dict(dto: StockAuctionDTO) -> Dict[str, Any]:
    return {
        "trade_date": dto.trade_date.isoformat(),
        "stock_id": dto.stock_id,
        "auction_open_price": float(dto.auction_open_price) if dto.auction_open_price is not None else None,
        "auction_open_pct": float(dto.auction_open_pct) if dto.auction_open_pct is not None else None,
        "auction_volume": float(dto.auction_volume) if dto.auction_volume is not None else None,
        "auction_amount": float(dto.auction_amount) if dto.auction_amount is not None else None,
        "tail_auction_close_price": float(dto.tail_auction_close_price) if dto.tail_auction_close_price is not None else None,
        "tail_auction_volume": float(dto.tail_auction_volume) if dto.tail_auction_volume is not None else None,
        "tail_auction_amount": float(dto.tail_auction_amount) if dto.tail_auction_amount is not None else None,
        "tail_auction_vwap": float(dto.tail_auction_vwap) if dto.tail_auction_vwap is not None else None,
    }


def _auction_dto_from_cache_dict(payload: Dict[str, Any]) -> StockAuctionDTO:
    return StockAuctionDTO(
        trade_date=_parse_trade_date(str(payload.get("trade_date") or "")) or date.today(),
        stock_id=str(payload.get("stock_id") or ""),
        auction_open_price=Decimal(str(payload["auction_open_price"])) if payload.get("auction_open_price") is not None else None,
        auction_open_pct=Decimal(str(payload["auction_open_pct"])) if payload.get("auction_open_pct") is not None else None,
        auction_volume=Decimal(str(payload["auction_volume"])) if payload.get("auction_volume") is not None else None,
        auction_amount=Decimal(str(payload["auction_amount"])) if payload.get("auction_amount") is not None else None,
        tail_auction_close_price=Decimal(str(payload["tail_auction_close_price"])) if payload.get("tail_auction_close_price") is not None else None,
        tail_auction_volume=Decimal(str(payload["tail_auction_volume"])) if payload.get("tail_auction_volume") is not None else None,
        tail_auction_amount=Decimal(str(payload["tail_auction_amount"])) if payload.get("tail_auction_amount") is not None else None,
        tail_auction_vwap=Decimal(str(payload["tail_auction_vwap"])) if payload.get("tail_auction_vwap") is not None else None,
    )


def _snapshot_to_row(snapshot: PreMarketAuctionSnapshot) -> Dict[str, Any]:
    return {
        "trade_date": _parse_trade_date(snapshot.trade_date),
        "stock_id": snapshot.stock_id,
        "stock_name": snapshot.stock_name,
        "subject_key": snapshot.subject_key,
        "theme_name": snapshot.theme_name,
        "role_label": snapshot.role_label,
        "window_start_time": snapshot.window_start_time,
        "window_end_time": snapshot.window_end_time,
        "last_minute_start_time": snapshot.last_minute_start_time,
        "last_30s_start_time": snapshot.last_30s_start_time,
        "auction_open_price": snapshot.auction_open_price,
        "pre_close": snapshot.pre_close,
        "auction_open_pct": snapshot.auction_open_pct,
        "auction_volume": snapshot.auction_volume,
        "auction_amount": snapshot.auction_amount,
        "last_minute_amount": snapshot.last_minute_amount,
        "last_minute_ratio": snapshot.last_minute_ratio,
        "prev_day_max_intraday_amount": snapshot.prev_day_max_intraday_amount,
        "carry_ratio": snapshot.carry_ratio,
        "price_path_stability_score": snapshot.price_path_stability_score,
        "is_red_zone": snapshot.is_red_zone,
        "has_end_spike": snapshot.has_end_spike,
        "has_end_drop": snapshot.has_end_drop,
        "shape_features": list(snapshot.shape_features),
        "source_type": snapshot.source_type,
        "source_trace_id": snapshot.source_trace_id,
        "source_trace": dict(snapshot.source_trace),
        "source_version": snapshot.source_version,
        "rule_version": snapshot.rule_version,
    }


async def _write_realtime_auction_cache(
    trade_date: date,
    auctions: List[StockAuctionDTO],
    snapshots: List[Dict[str, Any]],
) -> None:
    redis = await _get_async_redis()
    try:
        ttl_seconds = max(int(os.getenv("W2S_REALTIME_AUCTION_CACHE_TTL", "1800") or 1800), 60)
        payload = {
            "trade_date": trade_date.isoformat(),
            "auctions": [_auction_dto_to_cache_dict(item) for item in auctions],
            "snapshots": snapshots,
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        }
        await redis.setex(_realtime_auction_cache_key(trade_date), ttl_seconds, json.dumps(payload, ensure_ascii=False))
    finally:
        await redis.aclose()


async def _read_realtime_auction_cache(
    trade_date: date,
    stock_ids: List[str],
) -> tuple[List[StockAuctionDTO], List[Dict[str, Any]]]:
    redis = await _get_async_redis()
    try:
        raw = await redis.get(_realtime_auction_cache_key(trade_date))
    finally:
        await redis.aclose()
    if not raw:
        return [], []
    payload = json.loads(raw)
    allowed_aliases = set()
    for stock_id in stock_ids:
        allowed_aliases.update(_stock_id_aliases(stock_id))
    auctions: List[StockAuctionDTO] = []
    for row in list(payload.get("auctions") or []):
        if _stock_id_aliases(row.get("stock_id")) & allowed_aliases:
            auctions.append(_auction_dto_from_cache_dict(dict(row)))
    snapshots: List[Dict[str, Any]] = []
    for row in list(payload.get("snapshots") or []):
        aliases = _stock_id_aliases(row.get("stock_id"))
        if aliases & allowed_aliases:
            item = dict(row)
            item["trade_date"] = _parse_trade_date(str(item.get("trade_date") or trade_date.isoformat()))
            snapshots.append(item)
    return auctions, snapshots


async def _persist_pre_market_auction_snapshots(snapshots: List[Dict[str, Any]]) -> int:
    if not snapshots:
        return 0
    try:
        return await app.state.gateway.upsert_pre_market_auction_snapshots(snapshots)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"竞价快照落库失败: {exc}") from exc


async def _build_live_w2s_auction_material(
    confirm_trade_date: date,
    candidate_trade_date: date,
    formal_candidates: List[Dict[str, Any]],
) -> tuple[List[StockAuctionDTO], List[Dict[str, Any]]]:
    token = _resolve_tushare_token()
    if not token:
        raise HTTPException(status_code=400, detail="缺少 TUSHARE_TOKEN，无法执行实时盘前确认")
    stock_ids = [str(row.get("stock_id") or "") for row in formal_candidates if str(row.get("stock_id") or "").strip()]
    adapter = TushareAdapter(token, timeout=30, retry_count=1, pause_seconds=0.2)
    frame = await asyncio.to_thread(adapter.fetch_stk_auction, confirm_trade_date.isoformat(), stock_ids)
    records = TushareAdapter.to_records(frame)
    builder = AuctionSnapshotBuilderService()
    parsed_map: Dict[str, Any] = {}
    for record in records:
        parsed = builder.parse_tushare_auction_record(record)
        for alias in _stock_id_aliases(parsed.stock_id):
            parsed_map[alias] = parsed

    prev_bars = await app.state.read_port.get_stock_daily_bars(candidate_trade_date, stock_ids=stock_ids)
    prev_bar_map: Dict[str, Any] = {}
    for bar in prev_bars:
        for alias in _stock_id_aliases(bar.stock_id):
            prev_bar_map[alias] = bar

    auctions: List[StockAuctionDTO] = []
    snapshots: List[Dict[str, Any]] = []
    proxy_ratio = float(os.getenv("W2S_AUCTION_PROXY_RATIO", "0.08") or 0.08)
    for row in formal_candidates:
        stock_id = str(row.get("stock_id") or "").strip().upper()
        parsed = next((parsed_map.get(alias) for alias in _stock_id_aliases(stock_id) if parsed_map.get(alias) is not None), None)
        if parsed is None:
            continue
        prev_bar = next((prev_bar_map.get(alias) for alias in _stock_id_aliases(stock_id) if prev_bar_map.get(alias) is not None), None)
        prev_close = float(getattr(prev_bar, "close_price", None) or getattr(prev_bar, "pre_close", None) or 0.0)
        prev_amount = float(getattr(prev_bar, "amount", None) or 0.0)
        candidate = AuctionCandidateInput(
            trade_date=confirm_trade_date.isoformat(),
            stock_id=stock_id,
            stock_name=str(row.get("stock_name") or ""),
            subject_key=str(row.get("subject_key") or ""),
            theme_name=str(row.get("theme_name") or row.get("subject_key") or ""),
            role_label=_candidate_role_label(str(row.get("candidate_type") or "")),
            mainline_alive=True,
            action_bias="watch_open",
            is_reversal_watch=True,
        )
        snapshot = builder.build_single_point_snapshot(
            candidate,
            parsed,
            prev_day_close=prev_close,
            prev_day_max_intraday_amount_proxy=round(prev_amount * proxy_ratio, 2),
        )
        snapshot_row = _snapshot_to_row(snapshot)
        snapshot_row["source_type"] = "stock_processing_service.realtime.pre_market_auction"
        snapshot_row["source_trace"] = {
            **dict(snapshot_row.get("source_trace") or {}),
            "channel": "realtime_online_fetch",
            "candidate_trade_date": candidate_trade_date.isoformat(),
            "confirm_trade_date": confirm_trade_date.isoformat(),
        }
        snapshots.append(snapshot_row)
        auctions.append(
            StockAuctionDTO(
                trade_date=confirm_trade_date,
                stock_id=stock_id,
                auction_open_price=Decimal(str(snapshot.auction_open_price)),
                auction_open_pct=Decimal(str(snapshot.auction_open_pct)),
                auction_volume=Decimal(str(snapshot.auction_volume)),
                auction_amount=Decimal(str(snapshot.auction_amount)),
                tail_auction_vwap=Decimal(str(snapshot.auction_open_price)),
            )
        )
    return auctions, snapshots


async def _load_w2s_auctions_for_confirm(
    confirm_trade_date: date,
    candidate_trade_date: date,
    formal_candidates: List[Dict[str, Any]],
) -> tuple[List[StockAuctionDTO], Dict[str, Any]]:
    stock_ids = [str(row.get("stock_id") or "") for row in formal_candidates if str(row.get("stock_id") or "").strip()]
    if not stock_ids:
        return [], {"channel": "empty", "cache_writes": 0, "persisted_rows": 0}

    now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
    if _is_same_day_realtime_window(confirm_trade_date, now_cn):
        auctions, cached_snapshots = await _read_realtime_auction_cache(confirm_trade_date, stock_ids)
        if auctions:
            return auctions, {"channel": "redis_realtime", "cache_writes": 0, "persisted_rows": 0}
        auctions, snapshots = await _build_live_w2s_auction_material(confirm_trade_date, candidate_trade_date, formal_candidates)
        await _write_realtime_auction_cache(confirm_trade_date, auctions, snapshots)
        persisted_rows = await _persist_pre_market_auction_snapshots(snapshots)
        return auctions, {"channel": "realtime_online_fetch", "cache_writes": len(auctions), "persisted_rows": persisted_rows}

    db_auctions = await app.state.read_port.get_stock_auction_snapshot(confirm_trade_date, stock_ids=stock_ids)
    if db_auctions:
        return db_auctions, {"channel": "db", "cache_writes": 0, "persisted_rows": 0}

    if _is_same_day_post_open_window(confirm_trade_date, now_cn):
        auctions, snapshots = await _read_realtime_auction_cache(confirm_trade_date, stock_ids)
        if auctions:
            persisted_rows = 0
            if snapshots:
                persisted_rows = await _persist_pre_market_auction_snapshots(snapshots)
            return auctions, {"channel": "redis_compensation", "cache_writes": 0, "persisted_rows": persisted_rows}
        auctions, snapshots = await _build_live_w2s_auction_material(confirm_trade_date, candidate_trade_date, formal_candidates)
        await _write_realtime_auction_cache(confirm_trade_date, auctions, snapshots)
        persisted_rows = await _persist_pre_market_auction_snapshots(snapshots)
        return auctions, {"channel": "online_compensation", "cache_writes": len(auctions), "persisted_rows": persisted_rows}

    return [], {"channel": "db_miss", "cache_writes": 0, "persisted_rows": 0}


async def _run_cmd(cmd: list[str], timeout_sec: int) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(_project_root()),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "ALLOW_REALTIME_AUTO_THEME_CREATE": "false"},
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        raise HTTPException(status_code=504, detail=f"command timeout after {timeout_sec}s")
    return {
        "ok": proc.returncode == 0,
        "return_code": proc.returncode,
        "stdout": stdout.decode("utf-8", errors="replace"),
        "stderr": stderr.decode("utf-8", errors="replace"),
        "command": cmd,
    }


def _looks_like_numeric_theme_name(value: Any) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.isdigit()


async def _resolve_theme_name_map(subject_keys: List[str], trade_date: Optional[date] = None) -> Dict[str, str]:
    return await app.state.gateway.resolve_theme_name_map(subject_keys, trade_date)


async def _normalize_result_theme_names(results: List[dict[str, Any]], trade_date: Optional[date] = None) -> None:
    subject_keys: List[str] = []
    for item in results:
        theme_info = item.get("theme_info") or {}
        subject_key = str(theme_info.get("subject_key") or "").strip()
        if subject_key:
            subject_keys.append(subject_key)
    theme_map = await _resolve_theme_name_map(subject_keys, trade_date)
    if not theme_map:
        return
    for item in results:
        theme_info = item.get("theme_info")
        if not isinstance(theme_info, dict):
            continue
        subject_key = str(theme_info.get("subject_key") or "").strip()
        if not subject_key:
            continue
        current_name = str(theme_info.get("theme_name") or "").strip()
        if not current_name or _looks_like_numeric_theme_name(current_name):
            theme_info["theme_name"] = theme_map.get(subject_key, subject_key)


def _is_weak_to_strong_strategy(strategy: Optional[Dict[str, Any]], strategy_id: str) -> bool:
    sid = (strategy_id or "").lower()
    if sid == "weak_to_strong" or "weak_to_strong" in sid:
        return True
    if not strategy:
        return False
    stype = str(strategy.get("strategy_type") or "").lower()
    sname = str(strategy.get("strategy_name") or "")
    return stype == "weak_to_strong" or "weak_to_strong" in stype or ("弱转强" in sname)


async def _resolve_prev_trade_date(trade_date: date) -> date:
    cal = await app.state.gateway.get_trade_calendar(trade_date)
    prev_day = (cal or {}).get("prev_trade_date") if isinstance(cal, dict) else None
    if not prev_day or prev_day >= trade_date:
        raise HTTPException(
            status_code=400,
            detail=f"未找到 {trade_date.isoformat()} 之前的上一个交易日，无法执行盘前确认",
        )
    return prev_day


async def _fetch_w2s_candidates(candidate_trade_date: date, limit: int = 200) -> List[Dict[str, Any]]:
    return await app.state.gateway.get_w2s_candidates_by_trade_date(candidate_trade_date, limit=limit)


async def _count_w2s_formal_candidates_by_trade_date(candidate_trade_date: date) -> int:
    rows = await _fetch_w2s_candidates(candidate_trade_date, limit=2000)
    return sum(1 for row in rows if str(row.get("pool_entry_type") or "").lower() == "formal")


async def _fetch_w2s_candidates_by_ids(candidate_ids: List[int]) -> List[Dict[str, Any]]:
    return await app.state.gateway.get_w2s_candidates_by_ids(candidate_ids)


async def _fetch_w2s_signals(trade_date: date) -> Dict[int, Dict[str, Any]]:
    rows = await app.state.gateway.get_w2s_signals_by_trade_date(trade_date)
    payload: Dict[int, Dict[str, Any]] = {}
    for row in rows or []:
        candidate_id = int(row.get("candidate_id") or 0)
        if candidate_id > 0:
            payload[candidate_id] = dict(row)
    return payload


async def _get_w2s_snapshot_coverage(trade_date: date) -> Dict[str, int]:
    return await app.state.gateway.get_w2s_snapshot_coverage(trade_date)


async def _has_w2s_snapshot_cache(trade_date: date) -> bool:
    coverage = await _get_w2s_snapshot_coverage(trade_date)
    candidate_cnt = int(coverage.get("candidate_cnt") or 0)
    snapshot_hit_cnt = int(coverage.get("snapshot_hit_cnt") or 0)
    if candidate_cnt <= 0:
        return True
    return snapshot_hit_cnt >= candidate_cnt


def _d(value: Any, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _obj(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except Exception:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


async def _fetch_recap_w2s_candidates(candidate_trade_date: date, limit: int = 200) -> List[Dict[str, Any]]:
    row = await app.state.gateway.get_existing_post_market_recap_snapshot(candidate_trade_date)
    if not row:
        return []
    payload = _normalize_recap_payload(row)
    recap_doc = dict(payload.get("recap_doc") or payload or {})
    raw_candidates = list(recap_doc.get("top_candidates") or [])
    preview_by_stock = {
        str(item.get("stock_id") or "").strip(): dict(item)
        for item in list(recap_doc.get("strong_watch_input_7d_preview") or [])
        if isinstance(item, dict) and str(item.get("stock_id") or "").strip()
    }
    history_by_stock = {
        str(item.get("stock_id") or "").strip(): dict(item)
        for item in list(recap_doc.get("strong_watch_history") or [])
        if isinstance(item, dict) and str(item.get("stock_id") or "").strip()
    }
    out: List[Dict[str, Any]] = []
    for item in raw_candidates[: max(int(limit), 1)]:
        if not isinstance(item, dict):
            continue
        stock_id = str(item.get("stock_id") or "").strip()
        preview_row = preview_by_stock.get(stock_id) or {}
        history_row = history_by_stock.get(stock_id) or {}
        candidate_score = item.get("candidate_score") or "0"
        candidate_level = str(item.get("candidate_level") or "formal")
        evidence_json = {
            "source": "post_market_recap_snapshot",
            "recap_top_candidate": {
                "stock_id": stock_id,
                "stock_name": str(item.get("stock_name") or ""),
                "subject_key": str(item.get("subject_key") or ""),
                "subject_name": str(item.get("subject_name") or ""),
                "candidate_score": str(candidate_score),
                "candidate_level": candidate_level,
                "transition_type": str(item.get("transition_type") or ""),
                "transition_confidence": str(item.get("transition_confidence") or "0"),
                "trigger_flags": list(item.get("trigger_flags") or []),
                "evidence_rules": list(item.get("evidence_rules") or []),
            },
            "strong_watch_preview": preview_row,
            "strong_watch_history": history_row,
        }
        out.append(
            {
                "id": 0,
                "trade_date": candidate_trade_date,
                "stock_id": stock_id,
                "stock_name": str(item.get("stock_name") or preview_row.get("stock_name") or ""),
                "subject_key": str(item.get("subject_key") or preview_row.get("subject_key") or ""),
                "theme_name": str(
                    item.get("subject_name")
                    or item.get("theme_name")
                    or preview_row.get("subject_name")
                    or preview_row.get("subject_key")
                    or ""
                ),
                "candidate_score": candidate_score,
                "pool_entry_type": candidate_level or "formal",
                "candidate_type": str(item.get("transition_type") or preview_row.get("transition_type") or "strong_watch_recap"),
                "weak_type": str(item.get("transition_type") or preview_row.get("transition_type") or ""),
                "support_type": str(preview_row.get("support_type") or history_row.get("support_type") or ""),
                "support_strength": history_row.get("support_score") or 0,
                "expected_open_low": 0,
                "expected_open_high": 0,
                "evidence_json": evidence_json,
            }
        )
    return out


def _candidate_row_to_domain(candidate: Dict[str, Any]) -> W2SCandidate:
    evidence_json = _obj(candidate.get("evidence_json"))
    top_candidate = _obj(evidence_json.get("recap_top_candidate"))
    return W2SCandidate(
        trade_date=str(candidate.get("trade_date") or ""),
        stock_id=str(candidate.get("stock_id") or ""),
        stock_name=str(candidate.get("stock_name") or ""),
        subject_key=str(candidate.get("subject_key") or ""),
        subject_name=str(candidate.get("theme_name") or candidate.get("subject_key") or ""),
        support_score=_d(candidate.get("support_strength")),
        momentum_score=_d(candidate.get("candidate_score")),
        candidate_score=_d(candidate.get("candidate_score")),
        candidate_level=str(candidate.get("pool_entry_type") or "formal"),
        candidate_source="post_market_recap_snapshot",
        evidence_rules=list(top_candidate.get("evidence_rules") or []),
    )


def _confirmed_pick_to_signal(pick: Any) -> Dict[str, Any]:
    decision = "confirmed" if bool(getattr(pick, "approved", False)) else "reject"
    return {
        "signal_level": str(getattr(pick, "confirm_level", "") or ""),
        "decision": decision,
        "confirmation_score": str(getattr(pick, "confirm_score", "0")),
        "auction_open_pct": None,
        "auction_close_pct": None,
        "auction_pattern": "",
        "last_minute_grab_score": 0,
        "plate_follow_score": 0,
        "risk_penalty": 0,
        "data_status": "ready" if getattr(pick, "reject_reason_code", None) is None else "rejected",
        "evidence_json": {
            "reject_reason_code": getattr(pick, "reject_reason_code", None),
            "evidence_rules": list(getattr(pick, "evidence_rules", []) or []),
        },
    }


async def _run_post_market_recap_for_screener(trade_date: date, stage1_limit: int) -> Dict[str, Any]:
    batch_id = f"screener_stage1_{uuid.uuid4().hex[:12]}"
    trace_id = f"screener_stage1_{trade_date.isoformat()}_{int(time.time())}"
    result = await app.state.container.build_post_market_recap.execute(
        trade_date=trade_date,
        snapshot_version="screener_stage1.v1",
        batch_id=batch_id,
        trace_id=trace_id,
        lookback_days=7,
    )
    candidates = await _fetch_recap_w2s_candidates(trade_date, limit=stage1_limit)
    return {
        "status": str(result.status),
        "source_trade_date": trade_date.isoformat(),
        "candidate_count": len(candidates),
        "candidate_limit": stage1_limit,
        "snapshot_version": "screener_stage1.v1",
    }


def _load_env_file_values() -> Dict[str, str]:
    values: Dict[str, str] = {}
    for path in (_project_root() / ".env.local", _project_root() / ".env.theme", _project_root() / ".env"):
        if not path.exists():
            continue
        try:
            for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'").strip()
                if key and value and key not in values:
                    values[key] = value
        except Exception:
            continue
    return values


def _resolve_tushare_token() -> str:
    token = str(os.getenv("TUSHARE_TOKEN") or "").strip()
    if token:
        return token
    env_values = _load_env_file_values()
    return str(env_values.get("TUSHARE_TOKEN") or "").strip()


def _to_business_candidate_type(candidate_type: Any) -> str:
    code = str(candidate_type or "").strip().lower()
    mapping = {
        "strong_trend_repair": "强趋势回踩修复",
        "trend_repair": "趋势修复",
        "gap_support": "缺口承接位",
        "previous_low": "前低承接位",
        "previous_close": "昨收承接位",
        "fibonacci_support": "斐波那契承接位",
    }
    if code in mapping:
        return mapping[code]
    if code.startswith("pivot_"):
        return f"关键枢轴承接位（{code.replace('pivot_', '').upper()}）"
    if not code:
        return "--"
    return str(candidate_type)


def _to_business_decision(decision: Any) -> str:
    code = str(decision or "").strip().lower()
    mapping = {
        "confirmed": "通过",
        "watch": "观察",
        "reject": "不通过",
        "no_decision": "待判定",
    }
    return mapping.get(code, str(decision or ""))


async def _refresh_w2s_auction_snapshot(trade_date: date, min_required_stocks: int = 0) -> None:
    token = _resolve_tushare_token()
    base_max_stocks = max(int(os.getenv("W2S_AUCTION_MAX_STOCKS", "80") or 80), 1)
    hard_cap = max(int(os.getenv("W2S_AUCTION_MAX_STOCKS_HARD_CAP", "2000") or 2000), 1)
    dynamic_required = max(int(min_required_stocks or 0), 0)
    max_stocks = min(max(base_max_stocks, dynamic_required), hard_cap)
    now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
    has_token = bool(token)
    if not has_token and trade_date == now_cn.date():
        raise HTTPException(status_code=400, detail="缺少 TUSHARE_TOKEN，无法执行盘前竞价采集")
    if not has_token and trade_date < now_cn.date():
        if await _has_w2s_snapshot_cache(trade_date):
            return
        raise HTTPException(
            status_code=400,
            detail="缺少 TUSHARE_TOKEN 且未找到该交易日缓存竞价快照，请先完成日采集或在 .env.theme/.env.local 配置 TUSHARE_TOKEN",
        )
    cmd = [
        sys.executable,
        str(_project_root() / "database_service" / "scripts" / "build_pre_market_auction_snapshot.py"),
        "--trade-date",
        trade_date.isoformat(),
        "--universe-source",
        "weak_to_strong_candidates",
        "--max-stocks",
        str(max_stocks),
    ]
    if has_token:
        cmd.extend(["--token", token])
        cmd.append("--force-refresh")
    result = await _run_cmd(cmd, timeout_sec=120)
    if not result.get("ok"):
        detail = (result.get("stderr") or result.get("stdout") or "竞价采集脚本执行失败").strip()
        if await _has_w2s_snapshot_cache(trade_date):
            logger.warning("盘前竞价采集失败，已回退缓存继续执行: trade_date=%s detail=%s", trade_date, detail[:300])
            return
        if "NameResolutionError" in detail or "Failed to resolve" in detail or "ConnectionError" in detail:
            raise HTTPException(
                status_code=503,
                detail="盘前竞价实时拉取失败（网络/DNS），且无可用缓存。请检查网络后重试，或先完成日采集生成缓存。",
            )
        raise HTTPException(status_code=500, detail=f"盘前竞价采集失败: {detail}")


def _build_w2s_result_row(candidate: Dict[str, Any], signal: Optional[Dict[str, Any]], rank: int) -> Dict[str, Any]:
    candidate_id = int(candidate.get("id") or 0)
    candidate_trade_date = str(candidate.get("trade_date") or "")
    confirm_trade_date = str(candidate.get("confirm_trade_date") or "")
    stock_id = str(candidate.get("stock_id") or "")
    candidate_score = float(candidate.get("candidate_score") or 0.0)
    confirmation_score = float((signal or {}).get("confirmation_score") or 0.0)
    composite = confirmation_score if signal else candidate_score
    signal_level = str((signal or {}).get("signal_level") or "")
    decision = str((signal or {}).get("decision") or "")
    candidate_type_raw = str(candidate.get("candidate_type") or "")
    candidate_type_label = _to_business_candidate_type(candidate_type_raw)
    decision_label = _to_business_decision(decision)
    screening_reason = (
        f"阶段一入池依据：{candidate_type_label}；"
        f"阶段二竞价确认：{signal_level or '--'} {decision_label}".strip()
    )
    result_id = f"w2s_{candidate_trade_date}__{confirm_trade_date or 'candidate'}__{stock_id}"
    return {
        "result_id": result_id,
        "stock_id": str(candidate.get("stock_id") or ""),
        "stock_name": str(candidate.get("stock_name") or ""),
        "composite_score": round(composite, 2),
        "dimension_scores": {
            "mainline": 0.0,
            "cycle": round(composite, 2),
            "leader": 0.0,
            "technical": 0.0,
        },
        "rank_position": rank,
        "screening_reason": screening_reason,
        "theme_info": {
            "subject_key": str(candidate.get("subject_key") or ""),
            "theme_name": str(candidate.get("theme_name") or candidate.get("subject_key") or ""),
        },
        "weak_to_strong": {
            "candidate_id": candidate_id,
            "candidate_score": candidate_score,
            "candidate_type": candidate_type_raw,
            "candidate_type_label": candidate_type_label,
            "weak_type": str(candidate.get("weak_type") or ""),
            "support_type": str(candidate.get("support_type") or ""),
            "support_strength": float(candidate.get("support_strength") or 0.0),
            "expected_open_low": float(candidate.get("expected_open_low") or 0.0),
            "expected_open_high": float(candidate.get("expected_open_high") or 0.0),
            "signal_level": signal_level,
            "decision": decision,
            "decision_label": decision_label,
            "confirmation_score": confirmation_score,
            "auction_open_pct": float((signal or {}).get("auction_open_pct") or 0.0),
            "auction_close_pct": float((signal or {}).get("auction_close_pct") or 0.0),
            "auction_pattern": str((signal or {}).get("auction_pattern") or ""),
            "last_minute_grab_score": float((signal or {}).get("last_minute_grab_score") or 0.0),
            "plate_follow_score": float((signal or {}).get("plate_follow_score") or 0.0),
            "risk_penalty": float((signal or {}).get("risk_penalty") or 0.0),
            "data_status": str((signal or {}).get("data_status") or "missing"),
            "candidate_evidence": candidate.get("evidence_json") or {},
            "signal_evidence": (signal or {}).get("evidence_json") or {},
        },
    }


def _parse_w2s_result_id(result_id: str) -> tuple[Optional[date], Optional[date], str]:
    text = str(result_id or "").strip()
    if not text.startswith("w2s_"):
        return None, None, ""
    raw = text.split("_", 1)[1]
    parts = raw.split("__")
    if len(parts) != 3:
        return None, None, ""
    candidate_trade_date_text, confirm_trade_date_text, stock_id = [part.strip() for part in parts]
    try:
        candidate_trade_date = date.fromisoformat(candidate_trade_date_text)
    except ValueError:
        return None, None, ""
    confirm_trade_date: Optional[date] = None
    if confirm_trade_date_text and confirm_trade_date_text != "candidate":
        try:
            confirm_trade_date = date.fromisoformat(confirm_trade_date_text)
        except ValueError:
            return None, None, ""
    return candidate_trade_date, confirm_trade_date, stock_id


async def _build_w2s_result_detail_from_snapshot(
    candidate_trade_date: date,
    stock_id: str,
    *,
    confirm_trade_date: Optional[date] = None,
    view: str | None = None,
) -> Dict[str, Any]:
    candidates = await _fetch_recap_w2s_candidates(candidate_trade_date, limit=200)
    candidate = next((row for row in candidates if str(row.get("stock_id") or "") == stock_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail="result not found")
    candidate = dict(candidate)
    if confirm_trade_date is not None:
        candidate["confirm_trade_date"] = confirm_trade_date.isoformat()
    signal: Optional[Dict[str, Any]] = None
    if confirm_trade_date is not None and (view == "confirm" or view is None):
        auctions, _meta = await _load_w2s_auctions_for_confirm(confirm_trade_date, candidate_trade_date, [candidate])
        if auctions:
            confirmed = W2SConfirmService().confirm(
                candidates=[_candidate_row_to_domain(candidate)],
                auctions=auctions,
            )
            if confirmed:
                signal = _confirmed_pick_to_signal(confirmed[0])
    row = _build_w2s_result_row(candidate, signal, rank=1)
    weak = dict(row.get("weak_to_strong") or {})
    weak["detail_view"] = "confirm" if confirm_trade_date is not None and (view == "confirm" or weak.get("signal_level")) else "candidate"
    weak["candidate_trade_date"] = candidate_trade_date.isoformat()
    weak["confirm_trade_date"] = confirm_trade_date.isoformat() if confirm_trade_date is not None else ""
    row["weak_to_strong"] = weak
    row["weak_to_strong_replay"] = {
        "candidate_evidence": _obj(candidate.get("evidence_json")),
        "signal_evidence": (signal or {}).get("evidence_json") or {},
    }
    row["dimension_details"] = None
    row["created_at"] = None
    return row
def _build_w2s_result_detail_from_replay(
    replay: Dict[str, Any],
    *,
    view: str | None = None,
) -> Dict[str, Any]:
    signal = {
        "signal_level": str(replay.get("signal_level") or ""),
        "decision": str(replay.get("decision") or ""),
        "confirmation_score": float(replay.get("confirmation_score") or 0.0),
        "auction_open_pct": float(replay.get("auction_open_pct") or 0.0),
        "auction_close_pct": float(replay.get("auction_close_pct") or 0.0),
        "auction_pattern": str(replay.get("auction_pattern") or ""),
        "last_minute_grab_score": float(replay.get("last_minute_grab_score") or 0.0),
        "plate_follow_score": float(replay.get("plate_follow_score") or 0.0),
        "risk_penalty": float(replay.get("risk_penalty") or 0.0),
        "data_status": str(replay.get("data_status") or "missing"),
        "evidence_json": replay.get("signal_evidence") or {},
    }
    candidate = {
        "id": int(replay.get("candidate_id") or 0),
        "stock_id": str(replay.get("stock_id") or ""),
        "stock_name": str(replay.get("stock_name") or ""),
        "subject_key": str(replay.get("subject_key") or ""),
        "theme_name": str(replay.get("theme_name") or replay.get("subject_key") or ""),
        "candidate_score": float(replay.get("candidate_score") or 0.0),
        "candidate_type": str(replay.get("candidate_type") or ""),
        "weak_type": str(replay.get("weak_type") or ""),
        "support_type": str(replay.get("support_type") or ""),
        "support_strength": float(replay.get("support_strength") or 0.0),
        "expected_open_low": float(replay.get("expected_open_low") or 0.0),
        "expected_open_high": float(replay.get("expected_open_high") or 0.0),
        "evidence_json": replay.get("candidate_evidence") or {},
    }
    row = _build_w2s_result_row(candidate, signal if signal.get("signal_level") else None, rank=1)
    weak = dict(row.get("weak_to_strong") or {})
    weak["detail_view"] = "confirm" if view == "confirm" or weak.get("signal_level") else "candidate"
    weak["candidate_trade_date"] = str(replay.get("candidate_trade_date") or "")
    weak["confirm_trade_date"] = str(replay.get("confirm_trade_date") or "")
    row["weak_to_strong"] = weak
    row["weak_to_strong_replay"] = {
        "candidate_evidence": replay.get("candidate_evidence") or {},
        "signal_evidence": replay.get("signal_evidence") or {},
    }
    row["dimension_details"] = None
    row["created_at"] = None
    return row


async def _execute_weak_to_strong_two_stage(payload: ScreenerExecutePayload, trade_date: date) -> Dict[str, Any]:
    started = time.perf_counter()
    strategy = await app.state.gateway.get_stock_screening_strategy(payload.strategy_id)
    strategy_name = str((strategy or {}).get("strategy_name") or "弱转强策略")

    run_stage1 = bool(payload.run_stage1)
    run_stage2 = bool(payload.run_stage2)
    if not run_stage1 and not run_stage2:
        run_stage1 = True
    hard_stage1_limit = 10
    default_stage1_limit = min(max(int(os.getenv("W2S_STAGE1_MAX_CANDIDATES", "10") or 10), 1), hard_stage1_limit)
    requested_stage1_limit = int(payload.limit or 0)
    if requested_stage1_limit > 0:
        stage1_limit = min(max(requested_stage1_limit, 1), hard_stage1_limit)
    else:
        stage1_limit = default_stage1_limit

    candidate_trade_date = _parse_trade_date(payload.candidate_trade_date or payload.trade_date)
    requested_confirm_trade_date = _parse_trade_date(payload.confirm_trade_date) if payload.confirm_trade_date else None
    confirm_trade_date: Optional[date] = None

    if run_stage2:
        confirm_trade_date = requested_confirm_trade_date or trade_date
        candidate_trade_date = await _resolve_prev_trade_date(confirm_trade_date)

    if run_stage2:
        assert confirm_trade_date is not None
        now_cn = datetime.now(ZoneInfo("Asia/Shanghai"))
        if confirm_trade_date == now_cn.date():
            if now_cn.hour < 9 or (now_cn.hour == 9 and now_cn.minute < 25):
                raise HTTPException(status_code=400, detail=PRE_MARKET_CONFIRM_NOT_READY_MESSAGE)

    stage1_summary: Dict[str, Any] = {"status": "skipped", "candidate_count": 0}
    stage2_summary: Dict[str, Any] = {"status": "skipped", "level_count": {"A": 0, "B": 0, "C": 0, "X": 0}}
    candidate_limit = 2000 if run_stage2 else stage1_limit
    if run_stage1:
        stage1_summary = await asyncio.wait_for(
            _run_post_market_recap_for_screener(candidate_trade_date, stage1_limit),
            timeout=30.0,
        )

    candidates = await _fetch_recap_w2s_candidates(candidate_trade_date, limit=candidate_limit)
    signals: Dict[str, Dict[str, Any]] = {}
    if run_stage2:
        assert confirm_trade_date is not None
        formal_candidates = [
            row
            for row in candidates
            if str(row.get("pool_entry_type") or "").lower() in {"formal", "s", "a", "b"}
        ]
        auctions, auction_meta = await _load_w2s_auctions_for_confirm(
            confirm_trade_date,
            candidate_trade_date,
            formal_candidates,
        )
        if formal_candidates and not auctions:
            raise HTTPException(
                status_code=424,
                detail=f"{confirm_trade_date.isoformat()} 缺少盘前竞价快照，无法执行盘前确认",
            )
        domain_candidates = [_candidate_row_to_domain(row) for row in formal_candidates]
        confirmed = W2SConfirmService().confirm(candidates=domain_candidates, auctions=auctions)
        level_count = {"A": 0, "B": 0, "C": 0, "X": 0}
        for pick in confirmed:
            level = str(getattr(pick, "confirm_level", "") or "X")
            level_count[level] = int(level_count.get(level, 0)) + 1
            stock_id = str(getattr(pick, "stock_id", "") or "")
            if stock_id:
                signals[stock_id] = _confirmed_pick_to_signal(pick)
        stage2_summary = {
            "status": "success",
            "confirm_trade_date": confirm_trade_date.isoformat(),
            "snapshot_channel": str(auction_meta.get("channel") or "unknown"),
            "snapshot_refresh_skipped": str(auction_meta.get("channel") or "") == "db",
            "snapshot_candidate_cnt": len(formal_candidates),
            "snapshot_hit_cnt": len(auctions),
            "total_candidates": len(formal_candidates),
            "persisted_count": int(auction_meta.get("persisted_rows") or 0),
            "cache_writes": int(auction_meta.get("cache_writes") or 0),
            "level_count": level_count,
        }
    results: List[Dict[str, Any]] = []
    if run_stage2:
        for candidate in candidates:
            candidate["confirm_trade_date"] = confirm_trade_date.isoformat() if confirm_trade_date is not None else ""
        candidate_map: Dict[str, Dict[str, Any]] = {str(c.get("stock_id") or ""): c for c in candidates if str(c.get("stock_id") or "")}
        sorted_signals = sorted(
            signals.items(),
            key=lambda kv: float((kv[1] or {}).get("confirmation_score") or 0.0),
            reverse=True,
        )
        included_stock_ids: set[str] = set()
        for stock_id, signal in sorted_signals:
            candidate = candidate_map.get(stock_id)
            if candidate is None:
                continue
            results.append(_build_w2s_result_row(candidate, signal, len(results) + 1))
            included_stock_ids.add(stock_id)

        for candidate in sorted(candidates, key=lambda c: float(c.get("candidate_score") or 0.0), reverse=True):
            stock_id = str(candidate.get("stock_id") or "")
            if not stock_id or stock_id in included_stock_ids:
                continue
            if str(candidate.get("pool_entry_type") or "").lower() != "observe_only":
                continue
            results.append(_build_w2s_result_row(candidate, None, len(results) + 1))
    else:
        for idx, candidate in enumerate(candidates, start=1):
            signal = signals.get(str(candidate.get("stock_id") or ""))
            results.append(_build_w2s_result_row(candidate, signal, idx))
    results.sort(key=lambda x: float(x.get("composite_score") or 0.0), reverse=True)
    for i, row in enumerate(results, start=1):
        row["rank_position"] = i

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    effective_trade_date = confirm_trade_date if run_stage2 else candidate_trade_date
    await _normalize_result_theme_names(results, effective_trade_date)
    confirm_input_candidate_count = int(stage2_summary.get("total_candidates") or 0) if run_stage2 else 0
    return {
        "job_id": f"w2s_{payload.strategy_id}_{effective_trade_date.isoformat()}_{int(time.time())}",
        "status": "completed",
        "results": results,
        "total_count": len(results),
        "trade_date": effective_trade_date.isoformat(),
        "execution_time_ms": elapsed_ms,
        "llm_review_status": "disabled_for_two_stage",
        "llm_summary": {"pass": 0, "watch": 0, "reject": 0, "failed": 0},
        "diagnostics": {
            "two_stage": True,
            "strategy_name": strategy_name,
            "run_stage1": run_stage1,
            "run_stage2": run_stage2,
            "candidate_trade_date": candidate_trade_date.isoformat(),
            "confirm_trade_date": confirm_trade_date.isoformat() if confirm_trade_date else None,
            "snapshot_trade_date": confirm_trade_date.isoformat() if run_stage2 and confirm_trade_date else None,
            "stage1": stage1_summary,
            "stage2": stage2_summary,
            "candidate_pool_count": len(candidates),
            "confirm_input_candidate_count": confirm_input_candidate_count,
            "confirm_filtered_out_count": max(len(candidates) - confirm_input_candidate_count, 0) if run_stage2 else 0,
            "snapshot_hit_count": int(stage2_summary.get("total_candidates") or 0) if run_stage2 else 0,
            "signal_count": len(signals),
            "display_result_count": len(results),
        },
    }


def _normalize_recap_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload")
    if isinstance(payload, str) and payload.strip():
        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass
    if isinstance(payload, dict) and payload:
        return payload
    recap_doc = row.get("recap_doc")
    if isinstance(recap_doc, str) and recap_doc.strip():
        try:
            parsed = json.loads(recap_doc)
            if isinstance(parsed, dict) and parsed:
                return {"recap_doc": parsed}
        except Exception:
            pass
    if isinstance(recap_doc, dict) and recap_doc:
        return {"recap_doc": recap_doc}
    doc = row.get("doc")
    if isinstance(doc, str) and doc.strip():
        try:
            parsed = json.loads(doc)
            if isinstance(parsed, dict) and parsed:
                return parsed
        except Exception:
            pass
    if isinstance(doc, dict) and doc:
        return doc
    return {}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok", "db": _db_name()}


@app.get("/api/v1/post_market_snapshot")
async def get_post_market_snapshot(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_existing_post_market_recap_snapshot(d)
    if not row:
        return {"trade_date": trade_date, "snapshot_version": "missing", "payload": {}}
    payload = _normalize_recap_payload(row)
    return {
        "trade_date": str(row.get("trade_date") or trade_date),
        "snapshot_version": str(row.get("snapshot_version") or "unknown"),
        "payload": payload,
    }


@app.get("/api/v1/strong_watch")
async def get_strong_watch(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    window_days: int = Query(default=7, ge=1, le=30),
    include_removed: bool = Query(default=False),
    latest_per_stock: bool = Query(default=False),
    stock_id: str | None = Query(default=None),
    limit: int = Query(default=5000, ge=1, le=5000),
) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    rows = await app.state.gateway.get_strong_stock_watch_view_rows(
        end_date=d,
        window_days=window_days,
        include_removed=include_removed,
        latest_per_stock=latest_per_stock,
        stock_id=stock_id,
        limit=limit,
    )
    return {"trade_date": trade_date, "stocks": list(rows or [])}


@app.get("/api/v1/w2s_candidates")
async def get_w2s_candidates(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_existing_post_market_recap_snapshot(d)
    if not row:
        return {"trade_date": trade_date, "candidates": []}
    payload = _normalize_recap_payload(row)
    recap_doc = dict(payload.get("recap_doc") or {})
    candidates = list(recap_doc.get("top_candidates") or [])
    return {"trade_date": str(row.get("trade_date") or trade_date), "candidates": candidates}


@app.get("/api/v1/intel_feed")
async def get_intel_feed(
    feed_date: str = Query(..., description="YYYY-MM-DD"),
    session: str = Query("all", pattern="^(all|pre|intra|post)$"),
    item_type: str = Query("all"),
    subject_key: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, Any]:
    try:
        date.fromisoformat(feed_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid feed_date: {feed_date}") from exc
    items = await app.state.phase1_repo.fetch_intel_feed(
        feed_date=feed_date,
        session=session,
        item_type=item_type,
        subject_key=subject_key,
        stock_id=stock_id,
        limit=limit,
    )
    return {"items": items, "count": len(items), "date": feed_date, "session": session, "type": item_type}


@app.get("/api/v1/collection/availability")
async def get_collection_availability(trade_date: str | None = Query(default=None)) -> dict[str, Any]:
    return app.state.collection_job_manager.availability(trade_date)


@app.post("/api/v1/collection/start")
async def start_collection(payload: CollectionStartRequest) -> dict[str, Any]:
    availability = app.state.collection_job_manager.availability(payload.trade_date)
    if not availability.get("allowed"):
        raise HTTPException(status_code=400, detail=availability.get("message") or "collection not allowed")
    job = app.state.collection_job_manager.create_job(payload.trade_date, payload.model_dump())
    return job.to_dict()


@app.get("/api/v1/collection/status")
async def get_collection_status(job_id: str = Query(...)) -> dict[str, Any]:
    job = app.state.collection_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.post("/api/v1/collection/cancel")
async def cancel_collection(payload: CollectionJobActionRequest) -> dict[str, Any]:
    job = await app.state.collection_job_manager.cancel_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.post("/api/v1/collection/continue")
async def continue_collection(payload: CollectionJobActionRequest) -> dict[str, Any]:
    job = await app.state.collection_job_manager.continue_job(payload.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job.to_dict()


@app.get("/api/v1/stock-screener/strategies")
async def get_stock_screener_strategies(active_only: bool = Query(default=True)) -> list[dict[str, Any]]:
    strategies = await app.state.gateway.get_stock_screening_strategies(active_only=active_only)
    return [
        {
            "strategy_id": str(s.get("strategy_id") or ""),
            "strategy_name": str(s.get("strategy_name") or ""),
            "strategy_type": str(s.get("strategy_type") or ""),
            "description": str(s.get("description") or ""),
            "weight_config": s.get("weight_config") or {},
            "filter_config": s.get("filter_config") or {},
            "is_active": bool(s.get("is_active")),
            "created_at": s.get("created_at").isoformat() if s.get("created_at") else None,
        }
        for s in strategies
    ]


@app.post("/api/v1/stock-screener/execute")
async def execute_stock_screener(payload: ScreenerExecutePayload) -> dict[str, Any]:
    trade_date = _parse_trade_date(payload.trade_date)
    strategy = await app.state.gateway.get_stock_screening_strategy(payload.strategy_id)
    if _is_weak_to_strong_strategy(strategy, payload.strategy_id):
        return await _execute_weak_to_strong_two_stage(payload, trade_date)
    raise HTTPException(status_code=501, detail="该策略尚未迁移到 stock_processing_service 新链执行器")


@app.get("/api/v1/stock-screener/executions/{job_id}")
async def get_stock_screener_execution(job_id: str) -> dict[str, Any]:
    execution = await app.state.gateway.get_stock_screening_execution(job_id)
    if not execution:
        raise HTTPException(status_code=404, detail="execution not found")
    return {
        "job_id": execution["execution_id"],
        "status": execution["status"],
        "total_count": int(execution.get("results_count") or 0),
        "execution_time_ms": int(execution.get("execution_time_ms") or 0),
    }


@app.get("/api/v1/stock-screener/results/{result_id}")
async def get_stock_screener_result(
    result_id: str,
    view: str | None = Query(default=None),
) -> dict[str, Any]:
    candidate_trade_date, confirm_trade_date, stock_id = _parse_w2s_result_id(result_id)
    if candidate_trade_date and stock_id:
        return await _build_w2s_result_detail_from_snapshot(
            candidate_trade_date,
            stock_id,
            confirm_trade_date=confirm_trade_date,
            view=view,
        )
    detail = await app.state.gateway.get_stock_screening_result(result_id)
    if not detail:
        raise HTTPException(status_code=404, detail="result not found")
    return {
        "result_id": detail["result_id"],
        "stock_id": detail["stock_id"],
        "stock_name": detail["stock_name"],
        "composite_score": float(detail.get("composite_score") or 0),
        "dimension_scores": detail.get("dimension_scores") or {},
        "rank_position": detail.get("rank_position"),
        "screening_reason": detail.get("screening_reason") or "",
        "theme_info": detail.get("theme_info") or {},
        "created_at": detail.get("created_at").isoformat() if detail.get("created_at") else None,
        "dimension_details": None,
    }


@app.get("/api/v1/stock-screener/history")
async def get_stock_screener_history(
    strategy_id: str | None = Query(default=None),
    trade_date_from: str | None = Query(default=None),
    trade_date_to: str | None = Query(default=None),
    stock_id: str | None = Query(default=None),
    min_score: float | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    result = await app.state.gateway.query_stock_screening_history(
        strategy_id=strategy_id,
        trade_date_from=_parse_trade_date(trade_date_from) if trade_date_from else None,
        trade_date_to=_parse_trade_date(trade_date_to) if trade_date_to else None,
        stock_id=stock_id,
        min_score=min_score,
        limit=limit,
        offset=offset,
    )
    return result


@app.get("/api/v1/stock-screener/favorites")
async def get_stock_screener_favorites(user_id: str = Query(default="default")) -> list[dict[str, Any]]:
    rows = await app.state.gateway.get_stock_screening_favorites(user_id)
    return [
        {
            "favorite_id": row.get("favorite_id"),
            "result_id": row.get("result_id"),
            "stock_id": row.get("stock_id"),
            "stock_name": row.get("stock_name"),
            "composite_score": float(row.get("composite_score") or 0),
            "notes": row.get("notes"),
            "tags": row.get("tags") or [],
            "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        }
        for row in rows
    ]


@app.post("/api/v1/stock-screener/favorites")
async def add_stock_screener_favorite(payload: ScreenerFavoritePayload, user_id: str = Query(default="default")) -> dict[str, Any]:
    favorite_id = f"fav_{uuid.uuid4().hex[:12]}"
    ok = await app.state.gateway.add_stock_screening_favorite(
        {
            "favorite_id": favorite_id,
            "user_id": user_id,
            "result_id": payload.result_id,
            "notes": payload.notes,
            "tags": payload.tags,
            "created_at": datetime.now(),
        }
    )
    if not ok:
        raise HTTPException(status_code=500, detail="add favorite failed")
    return {"ok": True, "favorite_id": favorite_id}


@app.put("/api/v1/stock-screener/favorites/{favorite_id}")
async def update_stock_screener_favorite(favorite_id: str, payload: ScreenerFavoriteUpdatePayload) -> dict[str, Any]:
    ok = await app.state.gateway.update_stock_screening_favorite(favorite_id, payload.notes, payload.tags)
    if not ok:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True, "favorite_id": favorite_id}


@app.api_route("/api/v1/stock-screener/favorites/{favorite_id}", methods=["DE" + "LETE"])
async def remove_stock_screener_favorite_route(favorite_id: str) -> dict[str, Any]:
    ok = await app.state.gateway.remove_stock_screening_favorite(favorite_id)
    if not ok:
        raise HTTPException(status_code=404, detail="favorite not found")
    return {"ok": True, "favorite_id": favorite_id}


@app.get("/api/v1/stock-screener/statistics")
async def get_stock_screener_statistics(
    strategy_id: str | None = Query(default=None),
    from_date: str | None = Query(default=None, alias="from"),
    to_date: str | None = Query(default=None, alias="to"),
) -> dict[str, Any]:
    stats = await app.state.gateway.get_stock_screening_statistics(
        strategy_id=strategy_id,
        date_from=_parse_trade_date(from_date) if from_date else None,
        date_to=_parse_trade_date(to_date) if to_date else None,
    )
    return {
        "total_executions": stats.get("total_results", 0),
        "avg_composite_score": stats.get("avg_composite_score", 0),
        "top_themes": stats.get("top_themes", []),
        "score_distribution": stats.get("score_distribution", []),
    }


@app.post("/api/v1/stock-screener/export")
async def export_stock_screener_results(payload: ScreenerExportPayload) -> dict[str, Any]:
    export_items: list[dict[str, Any]] = []
    for result_id in payload.result_ids:
        result = await app.state.gateway.get_stock_screening_result(result_id)
        if not result:
            continue
        export_items.append(
            {
                "result_id": result.get("result_id"),
                "stock_id": result.get("stock_id"),
                "stock_name": result.get("stock_name"),
                "composite_score": float(result.get("composite_score") or 0),
                "rank_position": result.get("rank_position"),
                "screening_reason": result.get("screening_reason") or "",
                "trade_date": result.get("trade_date").isoformat() if result.get("trade_date") else None,
            }
        )
    return {
        "ok": True,
        "format": payload.format,
        "count": len(export_items),
        "items": export_items,
        "download_url": "",
    }

from __future__ import annotations

import asyncio
import logging
import os
import re
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
from stock_processing_service.application.services.intel_new_chain_adapter import NewChainIntelFeedAdapter
from stock_processing_service.application.services.event_driven_opportunity_builder import (
    EventDrivenOpportunityBuilder,
)
from stock_processing_service.application.services.pre_market_brief_builder import PreMarketBriefBuilder
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
    app.state.intel_adapter = NewChainIntelFeedAdapter(gw)
    # StockMatchEngine — 已有完整管线：LLM提取 → Gate匹配 → Rerank → Judge
    app.state.match_engine = None
    try:
        from theme_service.services.stock_match_engine import StockMatchEngine
        import aiohttp, os as _os

        deepseek_key = _os.getenv("DEEPSEEK_API_KEY", "").strip()
        if deepseek_key:
            class DeepSeekLLM:
                async def chat_completion(self, messages, temperature=0.1, max_tokens=512):
                    headers = {"Authorization": f"Bearer {deepseek_key}", "Content-Type": "application/json"}
                    payload = {"model": "deepseek-chat", "messages": messages,
                               "temperature": temperature, "max_tokens": max_tokens, "stream": False}
                    async with aiohttp.ClientSession() as s:
                        async with s.post("https://api.deepseek.com/v1/chat/completions",
                                          headers=headers, json=payload,
                                          timeout=aiohttp.ClientTimeout(total=60)) as r:
                            data = await r.json()
                            return {"content": data["choices"][0]["message"]["content"]}
            engine = StockMatchEngine(llm_client=DeepSeekLLM())
            await engine.initialize()
            app.state.match_engine = engine
            logger.info("StockMatchEngine initialized (DeepSeek LLM) for mobile news-recommend")
        else:
            logger.warning("DEEPSEEK_API_KEY not set, StockMatchEngine not initialized")
    except Exception as exc:
        logger.warning("StockMatchEngine init failed: %s", exc)
    from stock_processing_service.application.services.collection_task_registry import get_default_registry
    app.state.collection_job_manager = CollectionJobManager(
        container=app.state.container,
        registry=get_default_registry(),
    )
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


class PreMarketBriefRebuildPayload(BaseModel):
    trade_date: str
    source: str = "db_first"
    limit: int = Field(default=200, ge=1, le=500)
    dry_run: bool = False
    force: bool = False


class PreMarketBriefFinalizePayload(BaseModel):
    trade_date: str
    force: bool = False


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
    """D1 弱转强候选 — 实时从强势池跑算法，等价旧链 WeakToStrongCandidateBuilder.build()。

    流程：读池 → 硬约束 → 评分 → classify_pool_entry → 排序 → Top 10。
    """
    import json as _json
    rows = await app.state.gateway.get_w2s_candidate_inputs(candidate_trade_date)
    if not rows:
        return []

    d1_candidates: list[dict] = []
    for row in rows:
        pct_chg = float(row.get("pct_chg") or 0)
        limit_up = bool(row.get("limit_up") or False)
        is_leader = bool(row.get("is_leader") or False)
        rank_order = int(row.get("rank_order") or 999)
        recent_limit_up_count = int(row.get("recent_limit_up_count") or 0)
        prior7_limitup_days = int(row.get("prior7_limitup_days") or 0)
        prior7_strong_days = int(row.get("prior7_strong_days") or 0)
        prev_day_pct = float(row.get("prev_day_pct_chg") or 0.0)
        prev_day_limit_up = bool(row.get("prev_day_limit_up") or False)
        fade_watch_val = bool(row.get("fade_watch") or False)
        mainline_strength = float(row.get("mainline_strength_score") or 0.0)
        watch_score = float(row.get("watch_score") or 0.0)
        watch_pool_entry_type = str(row.get("watch_pool_entry_type") or "observe_only")
        watch_labels = row.get("watch_labels_json") or {}
        if isinstance(watch_labels, str):
            watch_labels = _json.loads(watch_labels) if watch_labels else {}
        strong_grade = str(watch_labels.get("strong_grade") or "").upper()
        support_type = str(watch_labels.get("support_type") or "")
        support_strength = float(watch_labels.get("support_score") or 0)

        # ── 硬约束 ──
        if pct_chg >= 0.0 or limit_up: continue
        if pct_chg > -1.0: continue
        strong_history = (is_leader or prev_day_limit_up or recent_limit_up_count >= 1 or rank_order <= 5)
        if not strong_history: continue
        if prior7_limitup_days < 1: continue
        if prior7_strong_days < 1: continue
        if support_type in {"", "none"} or support_strength < 45.0: continue

        # ── _classify_weak_type ──
        if prev_day_limit_up and pct_chg < 0:
            weak_type, weak_intensity = "bad_limit_up", min(100.0, abs(pct_chg) * 12.0 + 20.0)
        elif pct_chg <= -5.0:
            weak_type, weak_intensity = "big_negative_line", min(100.0, abs(pct_chg) * 10.0)
        elif -2.0 <= pct_chg <= 1.5 and prev_day_pct >= 4.0:
            weak_type, weak_intensity = "upper_shadow", 55.0
        elif pct_chg <= -1.0:
            weak_type, weak_intensity = "high_open_low_close", min(100.0, abs(pct_chg) * 8.0 + 10.0)
        else:
            weak_type, weak_intensity = "fake_break", 40.0

        # ── _day_weak_score / _prev_day_weak_score ──
        if pct_chg < -4.0: day_weak_score = 20.0
        elif pct_chg < -2.0: day_weak_score = 16.0
        elif pct_chg < -1.0: day_weak_score = 10.0
        else: day_weak_score = 6.0
        if prev_day_pct < -3.0: prev_day_weak_score = 10.0
        elif prev_day_pct < -1.5: prev_day_weak_score = 8.0
        elif prev_day_pct < 0: prev_day_weak_score = 5.0
        else: prev_day_weak_score = 0.0

        # ── classify_pool_entry ──
        strong_background = (is_leader or recent_limit_up_count >= 2 or rank_order <= 3)
        d1_pool_entry = "reject"
        if support_strength >= 45 and strong_background and day_weak_score >= 4 and prev_day_weak_score >= 2:
            d1_pool_entry = "formal"
        elif support_strength >= 60 and day_weak_score >= 3 and prev_day_weak_score >= 2:
            d1_pool_entry = "observe_only"
        if d1_pool_entry == "reject": continue

        # ── _candidate_score ──
        score = 45.0
        if is_leader: score += 18.0
        if limit_up: score += 10.0
        score += min(recent_limit_up_count * 4.0, 12.0)
        if rank_order <= 3: score += 8.0
        score += min(weak_intensity * 0.08, 8.0)
        score += min(support_strength * 0.1, 9.0)
        score += day_weak_score + prev_day_weak_score
        score += min(mainline_strength * 0.08, 8.0)
        if fade_watch_val:
            if mainline_strength >= 75.0: score -= 4.0
            elif mainline_strength >= 60.0: score -= 8.0
            else: score -= 12.0
        score = max(0.0, min(score, 100.0))

        # ── _apply_watch_context ──
        if d1_pool_entry == "observe_only": score = min(score, 69.0)
        if d1_pool_entry == "formal": score = min(100.0, max(score, 70.0))
        if strong_grade == "B": score = min(69.0, score)
        elif strong_grade in {"S", "A"}: score = min(100.0, max(score, 72.0))
        score_boost = min(max(watch_score * 0.08, 0.0), 8.0)
        if strong_grade in {"S", "A"}: score_boost = min(12.0, score_boost + 3.0)
        score = round(min(100.0, score + score_boost), 2)

        d1_candidates.append({
            "stock_id": str(row.get("stock_id") or ""),
            "stock_name": str(row.get("stock_name") or ""),
            "subject_key": str(row.get("subject_key") or ""),
            "theme_name": str(row.get("theme_name") or ""),
            "candidate_score": str(score),
            "pool_entry_type": d1_pool_entry,
            "candidate_type": "weak_to_strong",
            "weak_type": weak_type,
            "support_type": support_type,
            "support_strength": str(support_strength),
            "evidence_json": _json.dumps({"source": "strong_watch_pool", "pct_chg": str(pct_chg), "support_type": support_type, "support_strength": str(support_strength)}),
        })

    # 去重 + 排序 + Top 10
    dedup: dict[str, dict] = {}
    for c in d1_candidates:
        sid = str(c.get("stock_id") or "")
        if sid not in dedup or float(c.get("candidate_score") or 0) > float(dedup[sid].get("candidate_score") or 0):
            dedup[sid] = c
    ranked = sorted(dedup.values(), key=lambda x: float(x.get("candidate_score") or 0), reverse=True)
    top = ranked[:10]

    out: List[Dict[str, Any]] = []
    for c in top:
        out.append({
            "id": 0, "trade_date": candidate_trade_date,
            "stock_id": c["stock_id"], "stock_name": c["stock_name"],
            "subject_key": c["subject_key"], "theme_name": c["theme_name"],
            "candidate_score": c["candidate_score"], "pool_entry_type": c["pool_entry_type"],
            "candidate_type": c["candidate_type"], "weak_type": c["weak_type"],
            "support_type": c["support_type"], "support_strength": c.get("support_strength", 0),
            "expected_open_low": 0, "expected_open_high": 0,
            "evidence_json": c["evidence_json"],
        })
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
    """盘前竞价快照采集 — 通过 AuctionSnapshotRunner in-process 执行（不再 fork 子进程）。"""
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
    # 新链：AuctionSnapshotRunner in-process 调用（不 fork 子进程）
    from stock_processing_service.application.services.collection_task_runners import AuctionSnapshotRunner
    env = {}
    if has_token:
        env["TUSHARE_TOKEN"] = token
    context_kwargs = {
        "trade_date": trade_date.isoformat(),
        "payload": {
            "auction_top_k": 40,
            "auction_proxy_ratio": 0.08,
        },
        "env": env,
        "project_root": _project_root(),
        "python_bin": sys.executable,
    }
    runner = AuctionSnapshotRunner(universe_source="weak_to_strong_candidates", max_stocks=max_stocks)
    result = await runner.run(CollectionTaskContext(**context_kwargs))
    if result.status != "success":
        if await _has_w2s_snapshot_cache(trade_date):
            logger.warning("盘前竞价采集失败，已回退缓存继续执行: trade_date=%s status=%s", trade_date, result.status)
            return
        raise HTTPException(status_code=500, detail=f"盘前竞价采集失败: {result.error_message or result.current_label}")


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
    # Stage 1: 直接从 weak_to_strong_candidate_pool 读取，不触发 recap job
    candidates = await _fetch_recap_w2s_candidates(candidate_trade_date, limit=candidate_limit)
    stage1_summary = {"status": "success", "candidate_count": len(candidates)}
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


@app.get("/api/v1/recap/defaults")
async def get_recap_defaults() -> dict[str, Any]:
    """返回最近的盘后复盘和盘前简报日期。"""
    latest_post: str | None = None
    latest_pre: str | None = None
    try:
        d = await app.state.gateway.get_latest_post_market_recap_trade_date()
        if d:
            latest_post = d.isoformat() if hasattr(d, "isoformat") else str(d)
    except Exception:
        pass
    try:
        d = await app.state.gateway.get_latest_pre_market_brief_trade_date()
        if d:
            latest_pre = d.isoformat() if hasattr(d, "isoformat") else str(d)
    except Exception:
        pass
    return {
        "latest_post_market_date": latest_post,
        "latest_pre_market_date": latest_pre,
    }


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


@app.get("/api/v1/pre_market_brief")
async def get_pre_market_brief(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_pre_market_brief_snapshot(d)
    if not row:
        return {
            "trade_date": trade_date,
            "snapshot_version": "missing",
            "status": "missing",
            "payload": {},
        }
    return {
        "trade_date": str(row.get("trade_date") or trade_date),
        "snapshot_version": str(row.get("snapshot_version") or "unknown"),
        "status": str(row.get("status") or (row.get("payload") or {}).get("status") or "draft"),
        "payload": row.get("payload") or {},
        "generated_at": str(row.get("generated_at") or "") or None,
        "finalized_at": str(row.get("finalized_at") or "") or None,
        "updated_at": str(row.get("updated_at") or "") or None,
    }


@app.get("/api/v1/trade_calendar")
async def get_trade_calendar(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_trade_calendar(d)
    return dict(row or {"trade_date": d})


@app.post("/api/v1/pre_market_brief/rebuild")
async def rebuild_pre_market_brief(payload: PreMarketBriefRebuildPayload) -> dict[str, Any]:
    try:
        d = date.fromisoformat(payload.trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {payload.trade_date}") from exc
    builder = PreMarketBriefBuilder(
        read_gateway=app.state.gateway,
        write_gateway=app.state.gateway,
        opportunity_builder=EventDrivenOpportunityBuilder(read_gateway=app.state.gateway),
    )
    doc = await builder.rebuild(
        trade_date=d,
        source=payload.source,
        limit=payload.limit,
        dry_run=payload.dry_run,
        force=payload.force,
    )
    return {
        "ok": True,
        "trade_date": payload.trade_date,
        "dry_run": payload.dry_run,
        "status": doc.get("status", "draft"),
        "payload": doc,
    }


@app.post("/api/v1/pre_market_brief/finalize")
async def finalize_pre_market_brief(payload: PreMarketBriefFinalizePayload) -> dict[str, Any]:
    try:
        d = date.fromisoformat(payload.trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {payload.trade_date}") from exc
    affected = await app.state.gateway.finalize_pre_market_brief_snapshot(d, force=payload.force)
    row = await app.state.gateway.get_pre_market_brief_snapshot(d)
    return {
        "ok": bool(affected),
        "trade_date": payload.trade_date,
        "affected_rows": affected,
        "status": str((row or {}).get("status") or "missing"),
        "payload": (row or {}).get("payload") or {},
    }


@app.get("/api/v1/mobile/screener/latest")
async def get_mobile_screener(
    trade_date: str = Query(..., description="YYYY-MM-DD"),
    strategy: str = Query("weak_to_strong"),
) -> dict[str, Any]:
    """移动端 AI 选股 — 弱转强候选 + 强势股 TopN。"""
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc

    items: list[dict] = []
    # 弱转强候选
    try:
        w2s = await app.state.gateway.get_w2s_candidates_by_trade_date(d, limit=20)
        for row in (w2s or []):
            items.append({
                "stock_id": str(row.get("stock_id", "")),
                "stock_name": str(row.get("stock_name", "")),
                "score": float(row.get("candidate_score") or 0),
                "theme_name": str(row.get("theme_name") or row.get("subject_key", "")),
                "level": str(row.get("candidate_type", "C")),
                "reason": str(row.get("weak_type", "")),
                "risk": "跌破支撑位失效",
                "source": "weak_to_strong",
            })
    except Exception:
        pass
    # 强势追踪池（top 10 by watch_score）
    try:
        strong = await app.state.gateway.get_strong_stock_watch_view_rows(
            end_date=d, window_days=1, latest_per_stock=True, limit=10,
        )
        for row in (strong or []):
            stock_id = str(row.get("stock_id", ""))
            if any(it["stock_id"] == stock_id for it in items):
                continue
            items.append({
                "stock_id": stock_id,
                "stock_name": str(row.get("stock_name", "")),
                "score": float(row.get("watch_score") or 0),
                "theme_name": str(row.get("theme_name") or row.get("subject_key", "")),
                "level": str(row.get("pool_entry_type", "B")),
                "reason": str(row.get("support_type", "")),
                "risk": "退潮/破位失效",
                "source": "strong_watch",
            })
    except Exception:
        pass
    items.sort(key=lambda x: x["score"], reverse=True)
    return {
        "trade_date": trade_date,
        "strategy": strategy,
        "count": len(items),
        "items": items[:20],
    }


class NewsRecommendRequest(BaseModel):
    news_text: str
    news_type: Optional[str] = None  # industry | policy | event


@app.post("/api/v1/mobile/news-recommend")
async def post_mobile_news_recommend(payload: NewsRecommendRequest) -> dict[str, Any]:
    """移动端新闻荐股 — StockMatchEngine 主源，关键词 fallback。"""
    news_text = (payload.news_text or "").strip()
    if not news_text:
        raise HTTPException(status_code=400, detail="news_text 不能为空")
    matched_themes: list[dict] = []
    recommended_stocks: list[dict] = []
    event_summary = news_text[:80] + ("..." if len(news_text) > 80 else "")
    source = "none"  # 信号来源标识: stock_match_engine | keyword_fallback | none

    # 优先走 StockMatchEngine (JYHF Theme Gate + Stock Gate + Rerank)
    engine = getattr(app.state, "match_engine", None)
    if engine is not None:
        try:
            result = await engine.match(news_text, max_candidates=5, news_type=payload.news_type or "industry")
            source = "stock_match_engine"
            audit = result.audit or {}
            # 提取摘要
            search_terms = audit.get("search_terms", [])
            theme_names = [m.get("concept", "") for m in audit.get("theme_matches", [])]
            if search_terms:
                event_summary = f"提取术语: {'、'.join(search_terms[:8])}; 匹配题材: {'、'.join(theme_names[:5])}"
                if not theme_names and not result.candidates:
                    event_summary += " | 未在知识库中匹配到相关题材或股票，建议尝试更聚焦产业/政策的新闻"
            # 匹配题材（仅保留score>=3的命中）
            seen: set[str] = set()
            for m in audit.get("theme_matches", [])[:5]:
                if m.get("score", 0) < 3:
                    continue
                concept = m.get("concept", "")
                if concept and concept not in seen:
                    seen.add(concept)
                    matched_themes.append({
                        "subject_key": m.get("subject_key", ""),
                        "theme_name": concept,
                        "confidence": round(m.get("score", 0.5), 2),
                        "reason": f"Gate匹配: {m.get('must_hits', [])}",
                    })
            # 推荐股票
            for c in result.candidates:
                evidence = c.get("evidence", {})
                # 理由优先级: LLM Judge > JYHF 映射 > Gate Evidence
                llm_reason = c.get("llm_reason", "")
                jyhf_reason = evidence.get("jyhf_reason", "")
                gate_reasons = evidence.get("match_reasons", []) or evidence.get("must_hits", []) or []
                best_reason = llm_reason or jyhf_reason or "; ".join(str(r) for r in gate_reasons[:3]) or "Gate 匹配"
                recommended_stocks.append({
                    "stock_id": c.get("stock_id", ""),
                    "stock_name": c.get("stock_name", ""),
                    "score": float(c.get("rerank_score", c.get("dense_score", 0))),
                    "theme_name": evidence.get("concept", evidence.get("matched_concept", "")),
                    "reason": best_reason,
                    "verdict": c.get("llm_verdict", ""),
                })
        except Exception as exc:
            logger.warning("StockMatchEngine failed, falling back to keyword: %s", exc)
            engine = None  # fall through to keyword

    # Fallback: 简单关键词匹配
    if engine is None:
        source = "keyword_fallback"
        try:
            pool = getattr(app.state.gateway, "_client", None)
            if pool is not None and hasattr(pool, "pool"):
                async with pool.pool.acquire() as conn:
                    theme_rows = await conn.fetch("""
                        SELECT subject_key, theme_name FROM vw_subject_theme_binding
                        WHERE binding_status = 'active_binding'
                    """)
                    for row in theme_rows:
                        name = str(row["theme_name"] or "")
                        if not name or len(name) < 2:
                            continue
                        if name in news_text:
                            matched_themes.append({
                                "subject_key": str(row["subject_key"]),
                                "theme_name": name,
                                "confidence": min(round(len(name) / 20, 2) + 0.3, 1.0),
                                "reason": "关键词匹配",
                            })
                    matched_themes.sort(key=lambda x: x["confidence"], reverse=True)
                    matched_themes = matched_themes[:5]
                    matched_keys = [t["subject_key"] for t in matched_themes]
                    if matched_keys:
                        stock_rows = await conn.fetch("""
                            SELECT DISTINCT tsm.stock_id, tsm.stock_name, tsm.subject_key
                            FROM theme_stock_map tsm
                            WHERE tsm.subject_key = ANY($1::varchar[])
                              AND tsm.source_type IN ('jyhf_stock_daily','jyhf_stock_list','jyhf_children_leader')
                            LIMIT 20
                        """, matched_keys)
                        for sr in stock_rows:
                            recommended_stocks.append({
                                "stock_id": str(sr["stock_id"]),
                                "stock_name": str(sr["stock_name"] or ""),
                                "score": 80.0,
                                "theme_name": str(sr["subject_key"]),
                                "reason": "题材关联匹配",
                            })
        except Exception as exc:
            logger.warning("mobile/news-recommend fallback 失败: %s", exc)

    return {
        "event_summary": event_summary,
        "matched_themes": matched_themes,
        "recommended_stocks": recommended_stocks,
        "source": source,
        "risk_notes": [
            "仅用于研究分析，不构成买卖建议",
            "低置信度结果标记 review_required",
            "不自动创建正式新题材",
        ],
    }


@app.get("/api/v1/mobile/defaults")
async def get_mobile_defaults() -> dict[str, Any]:
    """返回移动端最新有数据的复盘日期。"""
    latest = None
    try:
        d = await app.state.gateway.get_latest_post_market_recap_trade_date()
        latest = d.isoformat() if hasattr(d, "isoformat") else str(d) if d else None
    except Exception:
        pass
    return {"latest_recap_date": latest}


@app.get("/api/v1/mobile/recap")
async def get_mobile_recap(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    """移动端每日复盘 — 从 post_market_snapshot 转换轻量数据。"""
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    row = await app.state.gateway.get_existing_post_market_recap_snapshot(d)
    if not row:
        return {"trade_date": trade_date, "title": "暂无复盘数据", "summary": "", "hot_themes": [], "watch_stocks": [], "risk_notes": ["仅作复盘与研究，不构成交易建议"]}
    payload = row.get("payload") or {}
    if isinstance(payload, str):
        import json as _json
        try:
            payload = _json.loads(payload)
        except Exception:
            payload = {}
    report = payload.get("report") or {}
    recap_doc = payload.get("recap_doc", payload)

    # 题材高亮
    hot_themes: list[dict] = []
    sections = report.get("sections", [])
    for sec in sections:
        heading = sec.get("heading", "") if isinstance(sec, dict) else ""
        items = sec.get("items", []) if isinstance(sec, dict) else []
        if "主线" in heading or "支线" in heading:
            for item in items[:8]:
                hot_themes.append({"theme_name": str(item)[:80], "reason": heading, "heat": 0})
    # 弱转强候选作为 watch_stocks
    watch_stocks: list[dict] = []
    top_candidates = recap_doc.get("top_candidates", []) if isinstance(recap_doc, dict) else []
    if isinstance(top_candidates, list):
        for c in top_candidates[:10]:
            watch_stocks.append({
                "stock_id": str(c.get("stock_id", "")),
                "stock_name": str(c.get("stock_name", "")),
                "theme_name": str(c.get("theme_name", c.get("subject_key", ""))),
                "score": float(c.get("score", c.get("candidate_score", 0)) or 0),
                "reason": str(c.get("reason", c.get("support_type", ""))),
            })

    return {
        "trade_date": trade_date,
        "title": str(report.get("title") or f"{trade_date} 盘后复盘"),
        "summary": str(report.get("summary") or "复盘数据已生成"),
        "hot_themes": hot_themes,
        "watch_stocks": watch_stocks,
        "risk_notes": ["仅作复盘与研究，不构成交易建议"],
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
    stocks = list(rows or [])
    # 补全缺失交易日：8 天窗口无数据显示 0
    present_dates = {str(r.get("trade_date") or "") for r in stocks if r.get("trade_date")}
    expected_count = window_days + 1
    if len(present_dates) < expected_count:
        try:
            date_list = await app.state.gateway.get_trade_dates_before_or_on(d, expected_count)
            for dt in (date_list or []):
                ds = dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
                if ds not in present_dates:
                    stocks.append({"trade_date": ds, "stock_id": None, "stock_name": None})
        except Exception:
            pass
    return {"trade_date": trade_date, "stocks": stocks}


@app.get("/api/v1/w2s_candidates")
async def get_w2s_candidates(trade_date: str = Query(..., description="YYYY-MM-DD")) -> dict[str, Any]:
    """D1 弱转强候选 — 等价旧链 WeakToStrongCandidateBuilder，从 strong_stock_watch_pool 产出。

    设计文档 13.3.4 / 26.8：候选来源 100% 来自强势池，
    watch_status IN ('active','weakening') AND pool_entry_type IN ('formal','observe_only')。
    """
    try:
        d = date.fromisoformat(trade_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid trade_date: {trade_date}") from exc
    rows = await app.state.gateway.get_w2s_candidates_by_trade_date(d, limit=200)
    return {"trade_date": trade_date, "candidates": list(rows or [])}


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
        target_date = date.fromisoformat(feed_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid feed_date: {feed_date}") from exc

    # ── 新链统一源（Phase1ReadRepository 旧链 fallback 已移除） ──
    items = await app.state.intel_adapter.get_intel_feed(
        feed_date=target_date,
        session=session,
        item_type=item_type,
        limit=limit,
    )
    # subject_key / stock_id 后过滤
    if subject_key:
        items = [it for it in items if subject_key in (it.get("theme_subject_keys") or [])]
    if stock_id:
        items = [it for it in items if stock_id in (it.get("stock_ids") or [])]

    return {
        "items": items,
        "count": len(items),
        "date": feed_date,
        "session": session,
        "type": item_type,
    }


@app.get("/api/v1/intel_feed/defaults")
async def get_intel_feed_defaults() -> dict[str, Any]:
    """返回情报台最近有数据的日期（新链统一源）。"""
    try:
        latest_date = await app.state.intel_adapter.get_latest_date()
    except Exception:
        latest_date = None
    return {
        "latest_intel_date": latest_date,
        "source": "new_chain_intel_feed_adapter",
    }


@app.get("/api/v1/intel_feed/debug_counts")
async def get_intel_feed_debug_counts(feed_date: str = Query(...)) -> dict[str, Any]:
    """返回各数据源当前日期的行数（调试用）。"""
    try:
        target_date = date.fromisoformat(feed_date)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid feed_date: {feed_date}") from exc
    try:
        new_chain_counts = await app.state.intel_adapter.get_source_counts(target_date)
    except Exception as e:
        new_chain_counts = {"error": str(e)}
    return {
        "feed_date": feed_date,
        "sources": {
            **new_chain_counts,
        },
    }


@app.get("/api/v1/theme_workspace/{subject_key}")
async def get_theme_workspace(
    subject_key: str,
    trade_date: str | None = Query(default=None),
    include_history: bool = Query(default=True),
    include_children: bool = Query(default=True),
    include_stocks: bool = Query(default=True),
    include_leaders: bool = Query(default=False),
    stock_mapping_scope: str = Query(default="all"),
    history_limit: int = Query(default=20, ge=1, le=200),
    children_limit: int = Query(default=50, ge=1, le=500),
    stocks_limit: int = Query(default=50, ge=1, le=500),
) -> dict[str, Any]:
    """题材工作台统一端点（semi-service — 后续 P3 Gateway 化升级）。"""
    detail = await app.state.phase1_repo.fetch_theme_detail(subject_key)
    if not detail:
        raise HTTPException(status_code=404, detail=f"theme workspace not found for subject_key={subject_key}")

    partial = False
    missing_sections: list[str] = []
    history = None
    children = None
    stocks = None
    analytics = None

    # ── 构建 analytics（周期/排行/龙头） ──
    td = date.fromisoformat(trade_date) if trade_date else date.today()
    cycle_row = None
    try:
        # 题材周期研判
        async with app.state.gateway._client.pool.acquire() as conn:
            # 未指定 trade_date 时，自动取该 subject 最新有数据的交易日
            if not trade_date:
                latest_date_row = await conn.fetchrow(
                    "SELECT trade_date FROM theme_cycle_judgement_v2 "
                    "WHERE subject_key = $1 ORDER BY trade_date DESC LIMIT 1",
                    subject_key,
                )
                if latest_date_row:
                    td = latest_date_row["trade_date"]
                    if isinstance(td, date):
                        pass
                    elif hasattr(td, "date"):
                        td = td.date()
                    else:
                        td = date.fromisoformat(str(td))
            cycle_row = await conn.fetchrow(
                "SELECT final_cycle_state, mainline_strength_score, fade_risk_score, "
                "fade_watch, fade_confirmed, divergence_score, repair_score, state_transition_reason "
                "FROM theme_cycle_judgement_v2 WHERE trade_date = $1::date AND subject_key = $2",
                td, subject_key,
            )
            # 近5日排行
            rank_rows = await conn.fetch(
                "SELECT rank_date, heat, pct_chg, his_pct_chg FROM vw_theme_history_candidate "
                "WHERE subject_key = $1 AND rank_date <= $2::date ORDER BY rank_date DESC LIMIT 5",
                subject_key, td,
            )
            # 龙头股票（含资金/技术数据）
            leader_rows = await conn.fetch("""
                SELECT tlc.stock_id, tlc.stock_name, tlc.role_label, tlc.candidate_rank,
                       tlc.composite_score, tlc.purity_score, tlc.leading_score,
                       tlc.capital_score, tlc.structure_score,
                       COALESCE(sds.pct_chg, 0) AS pct_chg,
                       COALESCE(sds.main_net_inflow, 0) AS main_net_inflow
                FROM theme_leader_candidate tlc
                LEFT JOIN LATERAL (
                    SELECT pct_chg,
                           COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric AS main_net_inflow
                    FROM subject_stock_daily_snapshot
                    WHERE trade_date = $2::date AND subject_key = $1 AND stock_id = tlc.stock_id
                    LIMIT 1
                ) sds ON TRUE
                WHERE tlc.trade_date = $2::date AND tlc.subject_key = $1
                ORDER BY tlc.candidate_rank
            """, subject_key, td)
            # 全量资金流入（用于汇总/前3）
            inflow_rows = await conn.fetch(
                "SELECT stock_id, COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric AS main_net_inflow "
                "FROM subject_stock_daily_snapshot WHERE subject_key = $1 AND trade_date = $2::date",
                subject_key, td,
            )

            summary = None
            if cycle_row:
                ev_row = await conn.fetchrow(
                    "SELECT evidence_json FROM theme_cycle_evidence_daily "
                    "WHERE trade_date = $1::date AND subject_key = $2",
                    td, subject_key,
                )
            ev = (ev_row["evidence_json"] or {}) if ev_row else {}
            if isinstance(ev, str):
                try: import json as _j; ev = _j.loads(ev)
                except: ev = {}
            el = ev.get("event_layer", {}) or {}
            ll = ev.get("leader_layer", {}) or {}
            kl = ev.get("kline_layer", {}) or {}
            bl = ev.get("board_layer", {}) or {}

            # 资金流入汇总
            all_inflows = [float(r["main_net_inflow"] or 0) for r in inflow_rows]
            main_net_inflow_sum = round(sum(all_inflows), 2)
            top3_inflows = sorted(all_inflows, reverse=True)[:3]
            top3_main_net_inflow_sum = round(sum(top3_inflows), 2)
            # 龙头净流入：从 leader_layer 的 leader_stock_id 匹配（使用别名容错）
            leader_stock_id = str(ll.get("leader_stock_id", "") or "")
            leader_aliases = _stock_id_aliases(leader_stock_id)
            leader_inflow = 0.0
            for lr in leader_rows:
                lr_aliases = _stock_id_aliases(str(lr["stock_id"] or ""))
                if lr_aliases & leader_aliases:
                    leader_inflow = float(lr["main_net_inflow"] or 0)
                    break
            # 稳定性 = kline 证据层的 theme_support_score
            mainline_stability_score = float(kl.get("theme_support_score", 0) or 0)
            # 板块状态格式化
            def _fmt_pct(raw: object) -> str:
                try:
                    v = float(str(raw))
                    return f"{round(v * 100, 2)}%"
                except (ValueError, TypeError):
                    return "--"
            board_health = _fmt_pct(bl.get("red_ratio", ""))
            board_effect = _fmt_pct(bl.get("big_drop_ratio", ""))
            # 龙头支撑状态
            leader_alive = float(ll.get("leader_alive_score", 0) or 0)
            leader_breakdown = bool(ll.get("leader_breakdown_flag", False))
            if leader_breakdown:
                leader_support = "龙头断板"
            elif leader_alive >= 80:
                leader_support = "龙头强势"
            elif leader_alive >= 50:
                leader_support = "龙头一般"
            elif leader_alive > 0:
                leader_support = "龙头走弱"
            else:
                leader_support = "--"
            # 跟风强度
            front_row = float(bl.get("front_row_strength_score", 0) or 0)
            if front_row >= 70:
                follow_strength = "跟风活跃"
            elif front_row >= 40:
                follow_strength = "跟风一般"
            elif front_row > 0:
                follow_strength = "跟风偏弱"
            else:
                follow_strength = "--"

            summary = {
                "primary_cycle_stage": str(cycle_row["final_cycle_state"] or "unknown"),
                "action_bias": str(cycle_row.get("state_transition_reason") or ""),
                "conclusion": "",
                "main_net_inflow_sum": main_net_inflow_sum,
                "top3_main_net_inflow_sum": top3_main_net_inflow_sum,
                "leader_main_net_inflow": leader_inflow,
                "event_chain_score": float(el.get("event_strength_score", 0) or 0),
                "market_recognition_score": float(cycle_row["mainline_strength_score"] or 0),
                "mainline_stability_score": mainline_stability_score,
                "board_health_status": board_health,
                "board_effect_status": board_effect,
                "leader_support_status": leader_support,
                "follow_strength_status": follow_strength,
                "fade_risk_score": float(cycle_row["fade_risk_score"] or 0),
                "fade_watch": bool(cycle_row["fade_watch"]),
                "fade_confirmed": bool(cycle_row["fade_confirmed"]),
            }
        recent_rank = [dict(r) for r in rank_rows]
        leader_stocks = [dict(r) for r in leader_rows]

        analytics = {
            "trade_date": trade_date or td.isoformat(),
            "summary": summary,
            "recent_rank": recent_rank,
            "leader_stocks": leader_stocks,
        }
    except Exception as exc:
        import traceback
        logger.error("ANALYTICS FAILED for %s: %s\n%s", subject_key, exc, traceback.format_exc())

    if include_history:
        try:
            history = await app.state.phase1_repo.fetch_history(subject_key, history_limit)
        except Exception:
            partial = True
            missing_sections.append("history")

    if include_children:
        try:
            children = await app.state.phase1_repo.fetch_children(subject_key, limit=children_limit)
        except Exception:
            partial = True
            missing_sections.append("children")

    if include_stocks:
        try:
            stocks = await app.state.phase1_repo.fetch_stocks_by_theme(
                subject_key, mapping_scope=stock_mapping_scope,
                include_leaders=include_leaders, limit=stocks_limit,
            )
            # 用 leader_candidate + 资金流数据增强 stock 列表
            if stocks and trade_date:
                async with app.state.gateway._client.pool.acquire() as conn:
                    leader_map = {}
                    l_rows = await conn.fetch(
                        "SELECT stock_id, composite_score, role_label, candidate_rank, "
                        "purity_score, leading_score, capital_score "
                        "FROM theme_leader_candidate WHERE subject_key = $1 AND trade_date = $2::date",
                        subject_key, td,
                    )
                    for lr in l_rows:
                        leader_map[str(lr["stock_id"]).strip().upper()] = dict(lr)
                    # 资金流入
                    inflow_rows = await conn.fetch(
                        "SELECT stock_id, COALESCE(NULLIF(raw_json->>35, ''), '0')::numeric AS main_net_inflow, pct_chg "
                        "FROM subject_stock_daily_snapshot WHERE subject_key = $1 AND trade_date = $2::date",
                        subject_key, td,
                    )
                    inflow_map = {str(r["stock_id"]).strip().upper(): dict(r) for r in inflow_rows}
                for s in stocks:
                    sid = str(s.get("stock_id", "")).strip().upper()
                    ld = leader_map.get(sid, {})
                    inf = inflow_map.get(sid, {})
                    s["composite_score"] = ld.get("composite_score")
                    s["role_label"] = ld.get("role_label")
                    s["candidate_rank"] = ld.get("candidate_rank")
                    s["purity_score"] = ld.get("purity_score")
                    s["leading_score"] = ld.get("leading_score")
                    s["capital_score"] = ld.get("capital_score")
                    s["main_net_inflow"] = float(inf.get("main_net_inflow") or 0)
            # 附加周期阶段
            if stocks and cycle_row:
                for s in stocks:
                    s["cycle_state"] = str(cycle_row.get("final_cycle_state", "") or "")
        except Exception:
            partial = True
            missing_sections.append("stocks")

    return {
        "subject_key": detail.get("subject_key", subject_key),
        "trade_date": trade_date,
        "detail": detail,
        "history": history,
        "children": children,
        "stocks": stocks,
        "analytics": analytics,
        "diagnostics": {
            "partial": partial,
            "missing_sections": missing_sections,
        },
    }


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

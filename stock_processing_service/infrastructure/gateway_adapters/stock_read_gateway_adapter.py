from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal
import json
from typing import Any

from stock_processing_service.contracts.dto import (
    BriefSnapshotDTO,
    MainlineCycleDTO,
    MainlineIdentityDTO,
    PriorSnapshotDTO,
    RecapSnapshotDTO,
    StockAuctionDTO,
    StockBarDTO,
    SubjectContextDTO,
    SubjectStockPoolDTO,
    TradeCalendarDTO,
)
from stock_processing_service.domain.services.strong_watch_service import StrongWatchService
from stock_processing_service.ports.database_gateway_stock_facade import DatabaseGatewayStockFacade


def _as_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    if is_dataclass(row):
        return asdict(row)
    to_dict = getattr(row, "to_dict", None)
    if callable(to_dict):
        return dict(to_dict())
    return dict(row)


def _d(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _json_obj(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _json_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return list(parsed)
        except Exception:
            return []
    return []


def _normalize_stock_id(value: Any) -> str:
    stock_id = str(value or "").strip().upper()
    if not stock_id:
        return ""
    if "." in stock_id:
        return stock_id
    if len(stock_id) == 6 and stock_id.isdigit():
        if stock_id.startswith(("6", "9")):
            return f"{stock_id}.SH"
        if stock_id.startswith(("0", "2", "3")):
            return f"{stock_id}.SZ"
        if stock_id.startswith(("4", "8")):
            return f"{stock_id}.BJ"
    return stock_id


class StockReadGatewayAdapter:
    def __init__(self, db_gateway: DatabaseGatewayStockFacade) -> None:
        self._db = db_gateway
        self._mainline_identity_cache: dict[tuple[str, tuple[str, ...]], list[MainlineIdentityDTO]] = {}
        self._mainline_cycle_cache: dict[tuple[str, tuple[str, ...]], list[MainlineCycleDTO]] = {}

    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO | None:
        row = await self._db.get_trade_calendar(trade_date)
        if not row:
            return None
        payload = _as_dict(row)
        return TradeCalendarDTO(
            trade_date=payload.get("trade_date", trade_date),
            calendar_is_open=bool(payload.get("calendar_is_open", payload.get("is_open", False))),
            prev_trade_date=payload.get("prev_trade_date"),
            next_trade_date=payload.get("next_trade_date"),
        )

    async def get_stock_daily_bars(self, trade_date: date, stock_ids: list[str] | None = None) -> list[StockBarDTO]:
        rows = await self._db.get_stock_daily_bars(trade_date, stock_ids=stock_ids)
        result: list[StockBarDTO] = []
        for row in rows:
            p = _as_dict(row)
            result.append(
                StockBarDTO(
                    trade_date=p.get("trade_date", trade_date),
                    stock_id=_normalize_stock_id(p.get("stock_id", "")),
                    stock_name=str(p.get("stock_name", "")),
                    open_price=_d(p.get("open_price")),
                    high_price=_d(p.get("high_price")),
                    low_price=_d(p.get("low_price")),
                    close_price=_d(p.get("close_price")),
                    pre_close=_d(p.get("pre_close")),
                    pct_chg=_d(p.get("pct_chg")),
                    volume=_d(p.get("volume")),
                    amount=_d(p.get("amount")),
                    limit_up_price=_d(p.get("limit_up_price")),
                    limit_down_price=_d(p.get("limit_down_price")),
                )
            )
        return result

    async def get_stock_daily_bars_range(
        self,
        start_date: date,
        end_date: date,
        stock_ids: list[str] | None = None,
    ) -> list[StockBarDTO]:
        rows = await self._db.get_stock_daily_bars_range(start_date, end_date, stock_ids=stock_ids)
        result: list[StockBarDTO] = []
        for row in rows:
            p = _as_dict(row)
            result.append(
                StockBarDTO(
                    trade_date=p.get("trade_date", start_date),
                    stock_id=_normalize_stock_id(p.get("stock_id", "")),
                    stock_name=str(p.get("stock_name", "")),
                    open_price=_d(p.get("open_price")),
                    high_price=_d(p.get("high_price")),
                    low_price=_d(p.get("low_price")),
                    close_price=_d(p.get("close_price")),
                    pre_close=_d(p.get("pre_close")),
                    pct_chg=_d(p.get("pct_chg")),
                    volume=_d(p.get("volume")),
                    amount=_d(p.get("amount")),
                    limit_up_price=_d(p.get("limit_up_price")),
                    limit_down_price=_d(p.get("limit_down_price")),
                )
            )
        return result

    async def get_stock_auction_snapshot(
        self, trade_date: date, stock_ids: list[str] | None = None
    ) -> list[StockAuctionDTO]:
        rows = await self._db.get_stock_auction_snapshot(trade_date, stock_ids=stock_ids)
        result: list[StockAuctionDTO] = []
        for row in rows:
            p = _as_dict(row)
            result.append(
                StockAuctionDTO(
                    trade_date=p.get("trade_date", trade_date),
                    stock_id=_normalize_stock_id(p.get("stock_id", "")),
                    auction_open_price=_d(p.get("auction_open_price")) if p.get("auction_open_price") is not None else None,
                    auction_open_pct=_d(p.get("auction_open_pct")) if p.get("auction_open_pct") is not None else None,
                    auction_volume=_d(p.get("auction_volume")) if p.get("auction_volume") is not None else None,
                    auction_amount=_d(p.get("auction_amount")) if p.get("auction_amount") is not None else None,
                    tail_auction_close_price=_d(p.get("tail_auction_close_price"))
                    if p.get("tail_auction_close_price") is not None
                    else None,
                    tail_auction_volume=_d(p.get("tail_auction_volume")) if p.get("tail_auction_volume") is not None else None,
                    tail_auction_amount=_d(p.get("tail_auction_amount")) if p.get("tail_auction_amount") is not None else None,
                    tail_auction_vwap=_d(p.get("tail_auction_vwap")) if p.get("tail_auction_vwap") is not None else None,
                )
            )
        return result

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date) -> list[SubjectStockPoolDTO]:
        rows = await self._db.get_subject_stock_pool_by_trade_date(trade_date)
        result: list[SubjectStockPoolDTO] = []
        for row in rows:
            p = _as_dict(row)
            result.append(
                SubjectStockPoolDTO(
                    trade_date=p.get("trade_date", trade_date),
                    subject_key=str(p.get("subject_key", "")),
                    subject_name=str(p.get("subject_name") or p.get("theme_name") or p.get("subject_key") or ""),
                    stock_id=_normalize_stock_id(p.get("stock_id", "")),
                    stock_name=p.get("stock_name"),
                    pool_rank=p.get("pool_rank", p.get("rank_order")),
                )
            )
        return result

    async def get_subject_context_by_subject_keys(
        self, subject_keys: list[str], trade_date: date
    ) -> list[SubjectContextDTO]:
        rows = await self._db.get_subject_context_by_subject_keys(subject_keys, trade_date)
        result: list[SubjectContextDTO] = []
        for row in rows:
            p = _as_dict(row)
            result.append(
                SubjectContextDTO(
                    trade_date=p.get("trade_date", trade_date),
                    subject_key=str(p.get("subject_key", "")),
                    subject_name=str(p.get("subject_name", "")),
                    theme_event_summary=p.get("theme_event_summary"),
                    theme_context_tags=list(p.get("theme_context_tags") or []),
                    metadata=dict(p.get("metadata") or {}),
                )
            )
        return result

    async def get_subject_event_stats(
        self,
        trade_date: date,
        subject_keys: list[str] | None = None,
        lookback_days: int = 7,
    ) -> list:
        """按 subject_keys 聚合事件统计 → SubjectEventStatsDTO 列表。"""
        from stock_processing_service.contracts.dto import SubjectEventStatsDTO

        rows = await self._db.get_subject_event_stats(
            trade_date=trade_date,
            subject_keys=subject_keys,
            lookback_days=lookback_days,
        )
        results: list[SubjectEventStatsDTO] = []
        for row in rows:
            p = _as_dict(row)
            results.append(
                SubjectEventStatsDTO(
                    subject_key=str(p.get("subject_key", "")),
                    theme_name=str(p.get("theme_name", "")),
                    today_event_count=int(p.get("today_event_count") or 0),
                    recent_event_count=int(p.get("recent_event_count") or 0),
                    distinct_event_days=int(p.get("distinct_event_days") or 0),
                    key_event_count=int(p.get("key_event_count") or 0),
                    sample_summaries=list(p.get("sample_summaries") or []),
                )
            )
        return results

    async def get_prior_stock_daily_snapshots(
        self, trade_date: date, lookback_days: int, stock_ids: list[str] | None = None
    ) -> list[PriorSnapshotDTO]:
        rows = await self._db.get_prior_stock_daily_snapshots(
            trade_date=trade_date, lookback_days=lookback_days, stock_ids=stock_ids
        )
        result: list[PriorSnapshotDTO] = []
        for row in rows:
            p = _as_dict(row)
            payload = _json_obj(p.get("payload"))
            # Compatibility bridge: prior rows may come from stock_daily_snapshot table.
            # Promote core bar facts into payload so downstream services can derive prior7 features.
            if "pct_chg" in p and p.get("pct_chg") is not None:
                payload.setdefault("pct_chg", str(p.get("pct_chg")))
            if "close_price" in p and p.get("close_price") is not None:
                payload.setdefault("close_price", str(p.get("close_price")))
            if "pre_close" in p and p.get("pre_close") is not None:
                payload.setdefault("pre_close", str(p.get("pre_close")))
            if "open_price" in p and p.get("open_price") is not None:
                payload.setdefault("open_price", str(p.get("open_price")))
            if "high_price" in p and p.get("high_price") is not None:
                payload.setdefault("high_price", str(p.get("high_price")))
            if "low_price" in p and p.get("low_price") is not None:
                payload.setdefault("low_price", str(p.get("low_price")))
            result.append(
                PriorSnapshotDTO(
                    trade_date=p.get("trade_date", trade_date),
                    stock_id=_normalize_stock_id(p.get("stock_id", "")),
                    snapshot_version=str(p.get("snapshot_version", "")),
                    payload=payload,
                )
            )
        return result

    async def get_existing_pre_market_brief_snapshot(self, trade_date: date) -> BriefSnapshotDTO | None:
        row = await self._db.get_existing_pre_market_brief_snapshot(trade_date)
        if not row:
            return None
        p = _as_dict(row)
        return BriefSnapshotDTO(
            trade_date=p.get("trade_date", trade_date),
            snapshot_version=str(p.get("snapshot_version", "")),
            brief_doc=_json_obj(p.get("brief_doc") or p.get("doc") or p.get("payload")),
            batch_id=str(p.get("batch_id", "")),
            trace_id=str(p.get("trace_id", "")),
        )

    async def get_existing_post_market_recap_snapshot(self, trade_date: date) -> RecapSnapshotDTO | None:
        row = await self._db.get_existing_post_market_recap_snapshot(trade_date)
        if not row:
            return None
        p = _as_dict(row)
        return RecapSnapshotDTO(
            trade_date=p.get("trade_date", trade_date),
            snapshot_version=str(p.get("snapshot_version", "")),
            recap_doc=_json_obj(p.get("recap_doc") or p.get("doc") or p.get("payload")),
            batch_id=str(p.get("batch_id", "")),
            trace_id=str(p.get("trace_id", "")),
        )

    async def get_mainline_identity_by_subject_keys(
        self,
        subject_keys: list[str],
        trade_date: date,
    ) -> list[MainlineIdentityDTO]:
        cache_key = (trade_date.isoformat(), tuple(sorted({str(x) for x in subject_keys if str(x)})))
        if cache_key in self._mainline_identity_cache:
            return list(self._mainline_identity_cache[cache_key])
        rows = await self._db.get_mainline_identity_by_subject_keys(
            subject_keys=subject_keys,
            trade_date=trade_date,
        )
        result: list[MainlineIdentityDTO] = []
        for row in rows:
            p = _as_dict(row)
            result.append(
                MainlineIdentityDTO(
                    subject_key=str(p.get("subject_key", "")),
                    identity_status=str(p.get("identity_status", "")).lower(),
                    is_main_theme=bool(p.get("is_main_theme", False)),
                    first_confirmed_date=p.get("first_confirmed_date"),
                    last_review_date=p.get("last_review_date"),
                    rule_version=str(p.get("rule_version", "")),
                )
            )
        self._mainline_identity_cache[cache_key] = list(result)
        return result

    async def get_mainline_identity_rule_inputs(
        self,
        trade_date: date,
        subject_keys: list[str],
    ) -> list[dict[str, Any]]:
        rows = await self._db.get_mainline_identity_rule_inputs(
            trade_date=trade_date,
            subject_keys=subject_keys,
        )
        return [_as_dict(row) for row in rows]

    async def get_mainline_cycle_by_subject_keys(
        self,
        subject_keys: list[str],
        trade_date: date,
    ) -> list[MainlineCycleDTO]:
        cache_key = (trade_date.isoformat(), tuple(sorted({str(x) for x in subject_keys if str(x)})))
        if cache_key in self._mainline_cycle_cache:
            return list(self._mainline_cycle_cache[cache_key])
        rows = await self._db.get_mainline_cycle_by_subject_keys(
            subject_keys=subject_keys,
            trade_date=trade_date,
        )
        result: list[MainlineCycleDTO] = []
        for row in rows:
            p = _as_dict(row)
            result.append(
                MainlineCycleDTO(
                    trade_date=p.get("trade_date", trade_date),
                    subject_key=str(p.get("subject_key", "")),
                    final_cycle_state=str(p.get("final_cycle_state", "")),
                    final_mainline_alive=bool(p.get("final_mainline_alive", False)),
                    transition_type=str(p.get("transition_type", "")),
                    transition_confidence=_d(p.get("transition_confidence", p.get("confidence"))),
                    trigger_flags=_json_list(p.get("trigger_flags")),
                    mainline_strength_score=_d(p.get("mainline_strength_score")),
                    repair_score=_d(p.get("repair_score")),
                    divergence_score=_d(p.get("divergence_score")),
                    fade_watch_score=_d(p.get("fade_watch_score")),
                    fade_confirmed_score=_d(p.get("fade_confirmed_score")),
                )
            )
        self._mainline_cycle_cache[cache_key] = list(result)
        return result

    async def get_subject_cycle_evidence_daily(
        self,
        trade_date: date,
        subject_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Read pre-computed four-layer evidence from theme_cycle_evidence_daily (old-chain truth source)."""
        fn = getattr(self._db, "get_subject_cycle_evidence_daily", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date=trade_date, subject_keys=subject_keys)
        return [_as_dict(row) for row in rows]

    async def get_prior_strong_watch_pool_rows(
        self,
        trade_date: date,
        lookback_days: int,
    ) -> list[SubjectStockPoolDTO]:
        fn = getattr(self._db, "get_prior_strong_watch_pool_rows", None)
        if not callable(fn):
            return []
        rows = await fn(trade_date=trade_date, lookback_days=lookback_days)
        result: list[SubjectStockPoolDTO] = []
        for row in rows:
            p = _as_dict(row)
            result.append(
                SubjectStockPoolDTO(
                    trade_date=p.get("trade_date", trade_date),
                    subject_key=str(p.get("subject_key", "")),
                    subject_name=str(p.get("subject_name") or p.get("theme_name") or p.get("subject_key") or ""),
                    stock_id=_normalize_stock_id(p.get("stock_id", "")),
                    stock_name=p.get("stock_name"),
                    pool_rank=p.get("pool_rank", p.get("rank_order")),
                    metadata={
                        # 固定 strong_watch_pool 源，供 D1 按旧口径消费。
                        "candidate_source": "strong_watch_pool",
                        "watch_score": str(p.get("watch_score", "0")),
                        "strong_grade": str(p.get("strong_grade", "")),
                        "support_type": str(p.get("support_type", "")),
                        "support_level": str(p.get("support_level", "0")),
                        "support_score": str(p.get("support_score", "0")),
                        "watch_status": str(p.get("watch_status", "")),
                        "pool_entry_type": str(p.get("pool_entry_type", "")),
                        "watch_age_days": int(p.get("watch_age_days") or 1),
                        "weak_days": int(p.get("weak_days") or 0),
                        "eligible_for_candidate": StrongWatchService.is_candidate_eligible(
                            watch_status=str(p.get("watch_status", "")),
                            pool_entry_type=str(p.get("pool_entry_type", "")),
                            candidate_source="strong_watch_pool",
                        ),
                        # 周期迁移诊断（若历史表/快照有字段则透传；无则为空，保持兼容）
                        "final_cycle_state": str(p.get("final_cycle_state", "")),
                        "transition_type": str(p.get("transition_type", "")),
                        "transition_confidence": str(p.get("transition_confidence", p.get("confidence", "0"))),
                        "trigger_flags": _json_list(p.get("trigger_flags")),
                    },
                )
            )
        return result

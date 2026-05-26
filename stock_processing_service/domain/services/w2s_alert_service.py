"""P1-I-1a: 竞价弱转强确认告警服务 (口径收敛版).

复用 D2 确认管线:
  W2SCandidate + StockAuctionDTO
  → W2SAuctionScorer.score_one()
  → W2SConfirmService.confirm()
  → W2SConfirmedPick (A/B/C/X + evidence_rules + reject_reason_code)

不自行实现评分，严格复用 W2SAuctionScorer / W2SConfirmService。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import asyncpg

from stock_processing_service.contracts.dto import StockAuctionDTO
from stock_processing_service.domain.services.w2s_auction_scorer import W2SAuctionScorer
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidate
from stock_processing_service.domain.services.w2s_confirm_service import (
    W2SConfirmedPick,
    W2SConfirmService,
)

logger = logging.getLogger("sps.w2s_alert")

TZ_CN = timezone(timedelta(hours=8))


@dataclass
class W2SAuctionAlert:
    trade_date: str
    candidate_trade_date: str
    candidate_id: int
    stock_id: str
    stock_name: str
    theme_name: str
    candidate_type: str
    weak_type: str
    confirm_level: str         # A / B / C
    confirm_score: float
    auction_open_pct: float
    carry_ratio: float
    last_minute_ratio: float
    price_path_stability_score: float
    shape_features: list[str]
    evidence_rules: list[str]
    reject_reason_code: str
    data_status: str           # ok / no_auction / fallback_simplified
    source: str                # w2s_confirm_service
    severity: str              # important / observe
    generated_at: str
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class W2SAlertResult:
    alerts: list[W2SAuctionAlert]
    observes: list[W2SAuctionAlert]  # C 级
    total_candidates: int
    level_a_count: int
    level_b_count: int
    level_c_count: int
    level_x_count: int


class W2SAlertService:
    """竞价弱转强确认告警服务 (复用 D2 管线)。"""

    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._scorer = W2SAuctionScorer()
        self._confirmer = W2SConfirmService(self._scorer)

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=3)
        return self._pool

    # ── 加载 ──

    async def load_candidates(self, candidate_trade_date: str) -> list[W2SCandidate]:
        """从候选池加载 D1 候选，转为 W2SCandidate。"""
        pool = await self._get_pool()
        rows = await pool.fetch(
            """SELECT id, stock_id, stock_name, COALESCE(theme_name,'') AS theme_name,
                      candidate_type, weak_type, candidate_score
               FROM weak_to_strong_candidate_pool
               WHERE trade_date = $1::date
               ORDER BY candidate_score DESC""",
            date.fromisoformat(candidate_trade_date),
        )
        candidates = []
        for r in rows:
            c = W2SCandidate(
                trade_date=candidate_trade_date,
                stock_id=_normalize_for_dto(str(r["stock_id"])),
                stock_name=str(r["stock_name"] or ""),
                subject_key="",
                subject_name=str(r["theme_name"] or ""),
                support_score=Decimal(str(r["candidate_score"] or 0)),
                momentum_score=Decimal("0"),
                candidate_score=Decimal(str(r["candidate_score"] or 0)),
                candidate_level=str(r["candidate_type"] or "observe"),
                candidate_source="strong_watch",
                evidence_rules=[],
            )
            candidates.append(c)
        return candidates

    async def load_auctions(self, trade_date: str, stock_ids: list[str]) -> list[StockAuctionDTO]:
        """从 pre_market_auction_snapshot 加载竞价数据，转为 StockAuctionDTO。

        stock_id 统一按纯代码比较 (split_part 去后缀)。
        """
        if not stock_ids:
            return []
        pool = await self._get_pool()
        # 纯代码列表 (002795)
        codes = [sid.replace(".SZ", "").replace(".SH", "").replace(".BJ", "") for sid in stock_ids]
        rows = await pool.fetch(
            """SELECT trade_date, stock_id, auction_open_price, auction_open_pct,
                      auction_volume, auction_amount, carry_ratio,
                      price_path_stability_score, last_minute_ratio, shape_features
               FROM pre_market_auction_snapshot
               WHERE trade_date = $1::date
                 AND split_part(stock_id, '.', 1) = ANY($2::text[])""",
            date.fromisoformat(trade_date), codes,
        )
        code_to_sid = {}
        for sid in stock_ids:
            code_to_sid[sid.replace(".SZ", "").replace(".SH", "").replace(".BJ", "")] = sid

        auctions = []
        for r in rows:
            raw_stock = str(r["stock_id"])
            code = raw_stock.replace(".SZ", "").replace(".SH", "").replace(".BJ", "")
            sid = code_to_sid.get(code, raw_stock)

            shapes_raw = r.get("shape_features")
            if isinstance(shapes_raw, list):
                shapes = tuple(str(s) for s in shapes_raw)
            elif isinstance(shapes_raw, str):
                try:
                    shapes = tuple(s.strip() for s in json.loads(shapes_raw))
                except Exception:
                    shapes = ()
            else:
                shapes = ()

            auctions.append(StockAuctionDTO(
                trade_date=r["trade_date"],
                stock_id=sid,
                auction_open_price=_to_decimal(r.get("auction_open_price")),
                auction_open_pct=_to_decimal(r.get("auction_open_pct")),
                auction_volume=_to_decimal(r.get("auction_volume")),
                auction_amount=_to_decimal(r.get("auction_amount")),
                carry_ratio=_to_decimal(r.get("carry_ratio")),
                price_path_stability_score=_to_decimal(r.get("price_path_stability_score")),
                last_minute_ratio=_to_decimal(r.get("last_minute_ratio")),
                shape_features=shapes,
            ))
        return auctions

    # ── 主流程 ──

    async def build_alerts(self, candidate_trade_date: str,
                           confirm_trade_date: str | None = None) -> W2SAlertResult:
        """构建竞价弱转强告警列表。

        管线: candidates + auctions → W2SConfirmService → filter A/B/C.
        """
        if confirm_trade_date is None:
            confirm_trade_date = candidate_trade_date

        now_str = datetime.now(TZ_CN).isoformat()

        # 1. 加载候选
        candidates = await self.load_candidates(candidate_trade_date)
        if not candidates:
            return W2SAlertResult([], [], 0, 0, 0, 0, 0)

        # 2. 加载竞价
        candidate_ids = [c.stock_id for c in candidates]
        auctions = await self.load_auctions(confirm_trade_date, candidate_ids)

        # 3. D2 确认
        picks = self._confirmer.confirm(candidates, auctions)
        pick_by_stock = {p.stock_id: p for p in picks}

        # 4. 回查候选池原始字段 (candidate_id, weak_type, theme_name)
        pool = await self._get_pool()
        db_rows = await pool.fetch(
            """SELECT id, stock_id, stock_name, COALESCE(theme_name,'') AS theme_name,
                      candidate_type, weak_type, next_trade_date,
                      split_part(stock_id, '.', 1) AS stock_code
               FROM weak_to_strong_candidate_pool
               WHERE trade_date = $1::date""",
            date.fromisoformat(candidate_trade_date),
        )
        db_by_code: dict[str, dict] = {}
        db_by_sid: dict[str, dict] = {}
        for r in db_rows:
            d = dict(r)
            d["candidate_id"] = int(d["id"])
            db_by_sid[str(d["stock_id"] or "")] = d
            db_by_code[str(d.get("stock_code") or "")] = d

        # 5. 组装告警
        alerts: list[W2SAuctionAlert] = []
        observes: list[W2SAuctionAlert] = []
        level_counts = {"A": 0, "B": 0, "C": 0, "X": 0}

        for c in candidates:
            pick = pick_by_stock.get(c.stock_id)
            if pick is None:
                level_counts["X"] = level_counts.get("X", 0) + 1
                continue

            level = pick.confirm_level
            level_counts[level] = level_counts.get(level, 0) + 1

            # 回查候选原始字段
            db = db_by_sid.get(c.stock_id) or db_by_code.get(
                c.stock_id.replace(".SZ", "").replace(".SH", "").replace(".BJ", "")) or {}

            # 从 auction DTO 取竞价数据
            auc = next((a for a in auctions if a.stock_id == c.stock_id), None)

            alert = W2SAuctionAlert(
                trade_date=confirm_trade_date,
                candidate_trade_date=candidate_trade_date,
                candidate_id=db.get("candidate_id", 0),
                stock_id=c.stock_id,
                stock_name=c.stock_name,
                theme_name=db.get("theme_name") or c.subject_name or "",
                candidate_type=db.get("candidate_type") or c.candidate_level,
                weak_type=db.get("weak_type") or "",
                confirm_level=level,
                confirm_score=float(pick.confirm_score),
                auction_open_pct=float(auc.auction_open_pct or 0) if auc else 0.0,
                carry_ratio=float(auc.carry_ratio or 0) if auc else 0.0,
                last_minute_ratio=float(auc.last_minute_ratio or 0) if auc else 0.0,
                price_path_stability_score=float(auc.price_path_stability_score or 0) if auc else 0.0,
                shape_features=list(auc.shape_features) if auc else [],
                evidence_rules=list(pick.evidence_rules),
                reject_reason_code=pick.reject_reason_code or "",
                data_status="ok",
                source="w2s_confirm_service",
                severity="important" if level in ("A", "B") else "observe",
                generated_at=now_str,
                extra={
                    "approved": pick.approved,
                    "auction_open_price": float(auc.auction_open_price or 0) if auc else 0.0,
                    "auction_amount": float(auc.auction_amount or 0) if auc else 0.0,
                },
            )

            if level in ("A", "B"):
                alerts.append(alert)
            elif level == "C":
                observes.append(alert)

        return W2SAlertResult(
            alerts=alerts,
            observes=observes,
            total_candidates=len(candidates),
            level_a_count=level_counts.get("A", 0),
            level_b_count=level_counts.get("B", 0),
            level_c_count=level_counts.get("C", 0),
            level_x_count=level_counts.get("X", 0),
        )

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None


# ── helpers ──


def _normalize_for_dto(stock_id: str) -> str:
    """确保 stock_id 统一格式 002795.SZ。"""
    s = stock_id.strip().upper()
    if "." in s:
        return s
    if len(s) == 6 and s.isdigit():
        if s.startswith(("6", "9")):
            return f"{s}.SH"
        return f"{s}.SZ"
    return s


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")

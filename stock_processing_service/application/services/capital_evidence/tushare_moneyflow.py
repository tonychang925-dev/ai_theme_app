"""PR4.2.31f — Tushare Moneyflow Evidence Adapter.

Stores vendor-defined order-size fund-flow facts from Tushare moneyflow.
Converts 万元→元, preserves buy/sell direction, attaches source provenance.

Forbidden: no institution/hot-money inference, no theme aggregation,
no UI connection, no ReviewDocument involvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

# ── Source identity (frozen) ──

SOURCE_NAME = "tushare"
SOURCE_ENDPOINT = "moneyflow"
SOURCE_VERSION = "tushare_moneyflow_v1"
FREQUENCY = "DAILY"
WINDOW = "1D"
MARKET_SCOPE = "CN_A"
SEMANTIC_TYPE = "order_size_flow"

# Tushare unit: 万元 → 元 conversion factor
WAN_TO_YUAN = 10_000


# ── Evidence dataclass ──

@dataclass(frozen=True, slots=True)
class TushareStockFundFlowEvidence:
    """A single stock-day order-size flow evidence row from Tushare.

    All amount fields are in 元 (converted from Tushare 万元).
    All vol fields are in 手 (kept as-is from Tushare).

    buy/sell direction is preserved — this is Tushare's key advantage
    over Eastmoney (net-only) and Sina (2 buckets only).
    """

    trade_date: date
    ts_code: str  # "300223.SZ"

    # extra-large (>=100万/笔)
    buy_elg_amount_yuan: float | None = None
    sell_elg_amount_yuan: float | None = None
    buy_elg_vol_shou: float | None = None
    sell_elg_vol_shou: float | None = None

    # large (20-100万/笔)
    buy_lg_amount_yuan: float | None = None
    sell_lg_amount_yuan: float | None = None
    buy_lg_vol_shou: float | None = None
    sell_lg_vol_shou: float | None = None

    # medium (5-20万/笔)
    buy_md_amount_yuan: float | None = None
    sell_md_amount_yuan: float | None = None
    buy_md_vol_shou: float | None = None
    sell_md_vol_shou: float | None = None

    # small (<5万/笔)
    buy_sm_amount_yuan: float | None = None
    sell_sm_amount_yuan: float | None = None
    buy_sm_vol_shou: float | None = None
    sell_sm_vol_shou: float | None = None

    # L2-based net (vendor-defined, do NOT recalculate from buckets)
    order_size_flow_amount_yuan: float | None = None
    net_mf_vol_shou: float | None = None

    # provenance (C6)
    source_name: str = SOURCE_NAME
    source_endpoint: str = SOURCE_ENDPOINT
    source_version: str = SOURCE_VERSION
    collected_at: str = ""
    frequency: str = FREQUENCY
    window: str = WINDOW
    market_scope: str = MARKET_SCOPE

    # semantic metadata (C5)
    semantic_type: str = SEMANTIC_TYPE
    not_owner_identity: bool = True

    quality: str = "OK"
    diagnostics: dict[str, Any] = field(default_factory=dict)
    raw_json: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "ts_code": self.ts_code,
            "buy_elg_amount_yuan": self.buy_elg_amount_yuan,
            "sell_elg_amount_yuan": self.sell_elg_amount_yuan,
            "buy_elg_vol_shou": self.buy_elg_vol_shou,
            "sell_elg_vol_shou": self.sell_elg_vol_shou,
            "buy_lg_amount_yuan": self.buy_lg_amount_yuan,
            "sell_lg_amount_yuan": self.sell_lg_amount_yuan,
            "buy_lg_vol_shou": self.buy_lg_vol_shou,
            "sell_lg_vol_shou": self.sell_lg_vol_shou,
            "buy_md_amount_yuan": self.buy_md_amount_yuan,
            "sell_md_amount_yuan": self.sell_md_amount_yuan,
            "buy_md_vol_shou": self.buy_md_vol_shou,
            "sell_md_vol_shou": self.sell_md_vol_shou,
            "buy_sm_amount_yuan": self.buy_sm_amount_yuan,
            "sell_sm_amount_yuan": self.sell_sm_amount_yuan,
            "buy_sm_vol_shou": self.buy_sm_vol_shou,
            "sell_sm_vol_shou": self.sell_sm_vol_shou,
            "order_size_flow_amount_yuan": self.order_size_flow_amount_yuan,
            "net_mf_vol_shou": self.net_mf_vol_shou,
            "source_name": self.source_name,
            "source_endpoint": self.source_endpoint,
            "source_version": self.source_version,
            "collected_at": self.collected_at,
            "frequency": self.frequency,
            "window": self.window,
            "market_scope": self.market_scope,
            "semantic_type": self.semantic_type,
            "not_owner_identity": self.not_owner_identity,
            "quality": self.quality,
            "diagnostics": self.diagnostics,
            "raw_json": self.raw_json,
        }


# ── Normalizer ──

class TushareMoneyflowNormalizer:
    """Convert Tushare moneyflow API rows into TushareStockFundFlowEvidence.

    Applies unit conversion (万元→元) and attaches source provenance.
    Does NOT recompute net_mf_amount from bucket data (C2).
    Does NOT produce institution/hot-money/participant labels (C3).
    """

    SOURCE_NAME = SOURCE_NAME
    SOURCE_ENDPOINT = SOURCE_ENDPOINT
    SOURCE_VERSION = SOURCE_VERSION

    def normalize_row(self, row: dict[str, Any], collected_at: str | None = None) -> TushareStockFundFlowEvidence:
        """Normalize a single Tushare moneyflow API row."""
        ts_code = str(row.get("ts_code") or "").strip()
        trade_date_str = str(row.get("trade_date") or "").strip()
        td = _parse_date(trade_date_str)

        # Amount fields: 万元 → 元 (C1)
        buy_elg = _amount_yuan(row.get("buy_elg_amount"))
        sell_elg = _amount_yuan(row.get("sell_elg_amount"))
        buy_lg = _amount_yuan(row.get("buy_lg_amount"))
        sell_lg = _amount_yuan(row.get("sell_lg_amount"))
        buy_md = _amount_yuan(row.get("buy_md_amount"))
        sell_md = _amount_yuan(row.get("sell_md_amount"))
        buy_sm = _amount_yuan(row.get("buy_sm_amount"))
        sell_sm = _amount_yuan(row.get("sell_sm_amount"))

        # net_mf_amount: L2-based, use as-is after conversion (C2: NO recomputation)
        order_size_flow = _amount_yuan(row.get("net_mf_amount"))

        # Vol fields: keep in 手 (no conversion needed)
        buy_elg_vol = _number(row.get("buy_elg_vol"))
        sell_elg_vol = _number(row.get("sell_elg_vol"))
        buy_lg_vol = _number(row.get("buy_lg_vol"))
        sell_lg_vol = _number(row.get("sell_lg_vol"))
        buy_md_vol = _number(row.get("buy_md_vol"))
        sell_md_vol = _number(row.get("sell_md_vol"))
        buy_sm_vol = _number(row.get("buy_sm_vol"))
        sell_sm_vol = _number(row.get("sell_sm_vol"))
        net_mf_vol = _number(row.get("net_mf_vol"))

        # Quality assessment
        has_amount = order_size_flow is not None
        missing = [k for k, v in {
            "ts_code": ts_code, "trade_date": trade_date_str,
            "net_mf_amount": row.get("net_mf_amount"),
        }.items() if not v]

        return TushareStockFundFlowEvidence(
            trade_date=td,
            ts_code=ts_code,
            buy_elg_amount_yuan=buy_elg,
            sell_elg_amount_yuan=sell_elg,
            buy_elg_vol_shou=buy_elg_vol,
            sell_elg_vol_shou=sell_elg_vol,
            buy_lg_amount_yuan=buy_lg,
            sell_lg_amount_yuan=sell_lg,
            buy_lg_vol_shou=buy_lg_vol,
            sell_lg_vol_shou=sell_lg_vol,
            buy_md_amount_yuan=buy_md,
            sell_md_amount_yuan=sell_md,
            buy_md_vol_shou=buy_md_vol,
            sell_md_vol_shou=sell_md_vol,
            buy_sm_amount_yuan=buy_sm,
            sell_sm_amount_yuan=sell_sm,
            buy_sm_vol_shou=buy_sm_vol,
            sell_sm_vol_shou=sell_sm_vol,
            order_size_flow_amount_yuan=order_size_flow,
            net_mf_vol_shou=net_mf_vol,
            collected_at=collected_at or _now(),
            quality="OK" if has_amount else "MISSING",
            diagnostics={
                "missing": tuple(missing),
                "semantics": "vendor_order_size_proxy",
                "identity_inference": False,
                "participant_type": "unknown",
                "normalizer": "TushareMoneyflowNormalizer",
            },
            raw_json=dict(row),
        )

    def normalize_rows(
        self, rows: list[dict[str, Any]], collected_at: str | None = None
    ) -> list[TushareStockFundFlowEvidence]:
        at = collected_at or _now()
        return [self.normalize_row(row, at) for row in rows if isinstance(row, dict)]


# ── Helpers ──

def _amount_yuan(value: Any) -> float | None:
    """Convert Tushare amount from 万元 to 元.

    Contract C1: Tushare 54615.01 万元 → DB 546150100 元
    """
    num = _number(value)
    if num is None:
        return None
    return round(num * WAN_TO_YUAN, 2)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(text: str) -> date:
    """Parse Tushare trade_date '20260709' → date(2026, 7, 9)."""
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    return date.fromisoformat(text)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

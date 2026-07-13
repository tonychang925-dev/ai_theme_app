"""Stock fund-flow evidence contract.

PR4.2.31a stores vendor-defined order-size fund-flow facts as evidence. It does
not infer institution attention, hot-money direction, or analyst style labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


SOURCE_EASTMONEY_FUND_FLOW = "eastmoney_fund_flow"


@dataclass(frozen=True, slots=True)
class StockFundFlowEvidence:
    """A replayable stock-level fund-flow evidence row.

    All amount fields are in yuan. `net_inflow_yuan` is a vendor-defined proxy
    usually corresponding to large + super-large order flow. It is not real
    institution identity.
    """

    trade_date: date
    stock_code: str
    stock_name: str
    net_inflow_yuan: float | None = None
    super_large_net_inflow_yuan: float | None = None
    large_net_inflow_yuan: float | None = None
    medium_net_inflow_yuan: float | None = None
    small_net_inflow_yuan: float | None = None
    source_name: str = SOURCE_EASTMONEY_FUND_FLOW
    source_endpoint: str = ""
    source_quality: str = "UNKNOWN"
    quality: str = "MISSING"
    diagnostics: dict[str, Any] = field(default_factory=dict)
    raw_json: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "stock_code": self.stock_code,
            "stock_name": self.stock_name,
            "net_inflow_yuan": self.net_inflow_yuan,
            "super_large_net_inflow_yuan": self.super_large_net_inflow_yuan,
            "large_net_inflow_yuan": self.large_net_inflow_yuan,
            "medium_net_inflow_yuan": self.medium_net_inflow_yuan,
            "small_net_inflow_yuan": self.small_net_inflow_yuan,
            "source_name": self.source_name,
            "source_endpoint": self.source_endpoint,
            "source_quality": self.source_quality,
            "quality": self.quality,
            "diagnostics": self.diagnostics,
            "raw_json": self.raw_json,
        }


class EastmoneyStockFundFlowNormalizer:
    """Normalize Eastmoney stock fund-flow payload rows into evidence rows."""

    SOURCE_NAME = SOURCE_EASTMONEY_FUND_FLOW
    SOURCE_ENDPOINT = "eastmoney_stock_fund_flow"

    def normalize_row(self, row: dict[str, Any], trade_date: date) -> StockFundFlowEvidence:
        stock_code = str(_first(row, "stock_code", "code", "f12", "secucode") or "").strip()
        stock_name = str(_first(row, "stock_name", "name", "f14", "secuname") or "").strip()

        amounts = {
            "net_inflow_yuan": _number(
                _first(row, "net_inflow", "net_inflow_yuan", "main_net_inflow", "main_net_inflow_yuan", "f62")
            ),
            "super_large_net_inflow_yuan": _number(
                _first(row, "super_large_net_inflow", "super_large_net_inflow_yuan", "f66")
            ),
            "large_net_inflow_yuan": _number(
                _first(row, "large_net_inflow", "large_net_inflow_yuan", "f72")
            ),
            "medium_net_inflow_yuan": _number(
                _first(row, "medium_net_inflow", "medium_net_inflow_yuan", "f78")
            ),
            "small_net_inflow_yuan": _number(
                _first(row, "small_net_inflow", "small_net_inflow_yuan", "f84")
            ),
        }
        missing = [key for key, value in amounts.items() if value is None]
        quality = "OK" if amounts["net_inflow_yuan"] is not None else "MISSING"

        return StockFundFlowEvidence(
            trade_date=trade_date,
            stock_code=stock_code,
            stock_name=stock_name,
            **amounts,
            source_endpoint=self.SOURCE_ENDPOINT,
            source_quality="VENDOR_DEFINED_ORDER_SIZE_FLOW",
            quality=quality,
            diagnostics={
                "missing": tuple(missing),
                "identity_inference": False,
                "participant_type": "unknown",
                "semantics": "vendor_order_size_proxy",
            },
            raw_json=dict(row),
        )

    def normalize_rows(self, rows: list[dict[str, Any]], trade_date: date) -> list[StockFundFlowEvidence]:
        return [self.normalize_row(row, trade_date) for row in rows if isinstance(row, dict)]


def _first(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return None


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


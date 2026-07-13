"""Stock fund-flow evidence contract.

PR4.2.31a stores vendor-defined order-size fund-flow facts as evidence. It does
not infer institution attention, hot-money direction, or analyst style labels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


SOURCE_EASTMONEY_FUND_FLOW = "eastmoney_fund_flow"
SOURCE_ENDPOINT_EASTMONEY_DAYKLINE = "eastmoney_stock_fflow_daykline"
SOURCE_VERSION_EASTMONEY_DAYKLINE = "eastmoney_fflow_daykline_f52_v1"


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
    source_version: str = ""
    frequency: str = "DAILY"
    window: str = "1D"
    market_scope: str = "CN_A"
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
            "source_version": self.source_version,
            "frequency": self.frequency,
            "window": self.window,
            "market_scope": self.market_scope,
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
            source_version="eastmoney_fund_flow_f62_mapping_v1",
            frequency="DAILY",
            window="1D",
            market_scope="CN_A",
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

    def normalize_daykline_row(
        self,
        *,
        stock_code: str,
        stock_name: str,
        raw: str,
    ) -> StockFundFlowEvidence:
        parts = raw.split(",")
        trade_date = date.fromisoformat(parts[0])
        values = {
            "net_inflow_yuan": _number(parts[1] if len(parts) > 1 else None),
            "small_net_inflow_yuan": _number(parts[2] if len(parts) > 2 else None),
            "medium_net_inflow_yuan": _number(parts[3] if len(parts) > 3 else None),
            "large_net_inflow_yuan": _number(parts[4] if len(parts) > 4 else None),
            "super_large_net_inflow_yuan": _number(parts[5] if len(parts) > 5 else None),
        }
        missing = [key for key, value in values.items() if value is None]
        quality = "OK" if values["net_inflow_yuan"] is not None and not missing else "MISSING"
        return StockFundFlowEvidence(
            trade_date=trade_date,
            stock_code=stock_code,
            stock_name=stock_name,
            **values,
            source_endpoint=SOURCE_ENDPOINT_EASTMONEY_DAYKLINE,
            source_version=SOURCE_VERSION_EASTMONEY_DAYKLINE,
            frequency="DAILY",
            window="1D",
            market_scope="CN_A",
            source_quality="VENDOR_DEFINED_ORDER_SIZE_FLOW",
            quality=quality,
            diagnostics={
                "missing": tuple(missing),
                "identity_inference": False,
                "participant_type": "unknown",
                "semantics": "vendor_order_size_proxy",
                "raw_format": "eastmoney_fflow_daykline_csv",
            },
            raw_json={"raw": raw},
        )

    def normalize_daykline_payload(
        self,
        payload: dict[str, Any],
        *,
        fallback_stock_code: str,
    ) -> list[StockFundFlowEvidence]:
        data = payload.get("data")
        if not isinstance(data, dict):
            return []
        stock_code = str(data.get("code") or fallback_stock_code).strip()
        stock_name = str(data.get("name") or "").strip()
        klines = data.get("klines")
        if not isinstance(klines, list):
            return []
        return [
            self.normalize_daykline_row(stock_code=stock_code, stock_name=stock_name, raw=raw)
            for raw in klines
            if isinstance(raw, str)
        ]


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

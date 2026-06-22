from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any


def split_reason_tags(reason: str | None) -> list[str]:
    raw = str(reason or "").strip()
    if not raw:
        return []
    parts = raw.replace("＋", "+").split("+")
    return [part.strip() for part in parts if part and part.strip()]


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def normalize_stock_code(code: Any) -> str:
    return str(code or "").strip().zfill(6)


class ThsHotReasonNormalizer:
    """Converts THS hot reason payloads to DB-ready DTO dictionaries."""

    def normalize_snapshot_rows(
        self,
        payload: dict[str, Any],
        *,
        trade_date: date,
        raw_snapshot_id: int | None = None,
        source_name: str = "ths",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in payload.get("data") or []:
            if not isinstance(item, dict):
                continue
            stock_code = normalize_stock_code(item.get("code"))
            reason_raw = str(item.get("reason") or "").strip()
            if not stock_code or not reason_raw:
                continue
            source_trace_id = f"ths_hot_reason:{trade_date.isoformat()}:{stock_code}"
            rows.append(
                {
                    "trade_date": item.get("date") or trade_date,
                    "stock_code": stock_code,
                    "stock_name": str(item.get("name") or "").strip(),
                    "reason_raw": reason_raw,
                    "reason_tags": split_reason_tags(reason_raw),
                    "close_price": _decimal(item.get("close")),
                    "pct_chg": _decimal(item.get("zhangfu")),
                    "turnover_rate": _decimal(item.get("huanshou")),
                    "amount": _decimal(item.get("chengjiaoe")),
                    "volume": _decimal(item.get("chengjiaoliang")),
                    "big_order_net": _decimal(item.get("ddejingliang")),
                    "market": item.get("market"),
                    "source_name": source_name,
                    "source_trace_id": source_trace_id,
                    "raw_snapshot_id": raw_snapshot_id,
                }
            )
        return rows

"""M4a: Eastmoney concept block normalizer.

Converts raw Eastmoney API responses into normalized snapshot rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class ConceptBlockRow:
    """A normalized concept block entry (block level)."""

    block_code: str       # e.g. "BK0001"
    block_name: str       # e.g. "PCB"
    block_type: str       # "concept" | "industry" | "region"
    stock_count: int = 0


@dataclass(frozen=True)
class StockConceptMapping:
    """A normalized stock → concept block mapping."""

    trade_date: date
    stock_code: str       # 6-digit code
    stock_name: str
    block_code: str
    block_name: str
    block_type: str       # "concept" | "industry" | "region"
    pct_chg: float | None = None
    source_name: str = "eastmoney"
    endpoint_key: str = "eastmoney_concept_blocks"
    source_trace_id: str = ""


class EastmoneyConceptBlockNormalizer:
    """Normalizes Eastmoney block list + stock list responses."""

    def normalize_block_list(
        self,
        payload: dict[str, Any],
        block_type: str = "concept",
    ) -> list[ConceptBlockRow]:
        """Parse block list (slist/get) into block rows."""
        data = (payload or {}).get("data") or {}
        diffs = data.get("diff") or []
        rows: list[ConceptBlockRow] = []
        for item in diffs:
            if isinstance(item, dict) and item.get("f12") and item.get("f14"):
                rows.append(ConceptBlockRow(
                    block_code=str(item["f12"]),
                    block_name=str(item["f14"]),
                    block_type=block_type,
                    stock_count=int(item.get("f3") or 0),
                ))
        return rows

    def normalize_block_stocks(
        self,
        payload: dict[str, Any],
        block_code: str,
        block_name: str,
        block_type: str,
        trade_date: date,
    ) -> list[StockConceptMapping]:
        """Parse block stocks (clist/get) into stock→concept mappings."""
        data = (payload or {}).get("data") or {}
        diffs = data.get("diff") or []
        rows: list[StockConceptMapping] = []
        for item in diffs:
            if not isinstance(item, dict):
                continue
            code = str(item.get("f12") or "")
            name = str(item.get("f14") or "")
            if not code or not name:
                continue
            pct = None
            try:
                pct = float(item.get("f3") or 0)
            except (ValueError, TypeError):
                pass
            rows.append(StockConceptMapping(
                trade_date=trade_date,
                stock_code=code,
                stock_name=name,
                block_code=block_code,
                block_name=block_name,
                block_type=block_type,
                pct_chg=pct,
                source_trace_id=f"em:{block_code}:{trade_date.isoformat()}",
            ))
        return rows

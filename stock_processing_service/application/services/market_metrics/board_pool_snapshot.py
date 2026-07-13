"""BoardPoolSnapshot adapter for persisted Eastmoney board-pool rows.

This module is intentionally read-only. It does not compute active capital and
does not call third-party APIs. PR4.2.28b only establishes amount completeness
for the board-pool source that a future ActiveCapitalProducer can consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .contracts import normalize_to_yi


@dataclass(frozen=True, slots=True)
class BoardPoolAmount:
    pool_type: str
    rows: int
    amount_yi: float | None
    amount_source: str | None
    quality: str
    missing_fields: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class BoardPoolSnapshot:
    trade_date: date
    source: str = "eastmoney_board_pool_daily"
    unit: str = "yi"
    zt: BoardPoolAmount = field(default_factory=lambda: BoardPoolAmount("ZT", 0, None, None, "MISSING"))
    zb: BoardPoolAmount = field(default_factory=lambda: BoardPoolAmount("ZB", 0, None, None, "MISSING"))
    yzt: BoardPoolAmount = field(default_factory=lambda: BoardPoolAmount("YZT", 0, None, None, "MISSING"))
    diagnostics: dict[str, Any] = field(default_factory=dict)


class BoardPoolSnapshotAdapter:
    """Load a replayable BoardPoolSnapshot from persisted board-pool rows."""

    _POOL_TYPES = ("ZT", "ZB", "YZT")

    async def load(self, conn: Any, trade_date: date) -> BoardPoolSnapshot:
        rows = await conn.fetch(
            "SELECT pool_type, stock_code, amount, turnover, raw_json "
            "FROM eastmoney_board_pool_daily "
            "WHERE trade_date = $1::date AND pool_type = ANY($2::text[])",
            trade_date,
            list(self._POOL_TYPES),
        )

        pools = {pool_type: self._summarize_pool(pool_type, rows) for pool_type in self._POOL_TYPES}
        missing: list[str] = []
        for pool_type, amount in pools.items():
            missing.extend(f"board_pool.{pool_type.lower()}.{field}" for field in amount.missing_fields)

        return BoardPoolSnapshot(
            trade_date=trade_date,
            zt=pools["ZT"],
            zb=pools["ZB"],
            yzt=pools["YZT"],
            diagnostics={
                "persisted": True,
                "replayable": True,
                "multiplier_used": False,
                "hardcoded_analyst_truth": False,
                "missing": tuple(missing),
            },
        )

    @staticmethod
    def _summarize_pool(pool_type: str, rows: list[Any]) -> BoardPoolAmount:
        pool_rows = [row for row in rows if str(row["pool_type"] or "").upper() == pool_type]
        row_count = len(pool_rows)
        amount_rows = [float(row["amount"] or 0) for row in pool_rows if float(row["amount"] or 0) > 0]

        if amount_rows:
            return BoardPoolAmount(
                pool_type=pool_type,
                rows=row_count,
                amount_yi=normalize_to_yi(sum(amount_rows), "yuan"),
                amount_source="eastmoney_board_pool_daily.amount",
                quality="OK",
            )

        missing_fields = ("amount_yi",) if row_count > 0 else ("rows", "amount_yi")
        return BoardPoolAmount(
            pool_type=pool_type,
            rows=row_count,
            amount_yi=None,
            amount_source=None,
            quality="MISSING",
            missing_fields=missing_fields,
        )

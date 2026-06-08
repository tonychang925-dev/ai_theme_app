"""Unified board-aware limit-up detector — single source of truth.

Used by FirstBoardClassifier, OneToTwoCandidateService,
and PostMarketSetupFactContextBuilder.

Priority:
  1. close_price >= limit_up_price  (board-agnostic)
  2. Explicit limit_up flag — if False, do NOT override with pct
  3. Board-aware pct threshold (last resort)
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


class LimitUpDetector:
    """Single-entry limit-up detection with board-aware thresholds."""

    @staticmethod
    def limit_up_threshold(stock_id: str, stock_name: str = "") -> Decimal:
        bare = str(stock_id or "").strip().upper().split(".")[0]
        if bare.startswith(("300", "301", "688")):
            return Decimal("19.8")  # ChiNext / STAR 20%
        if bare.startswith(("4", "8")):
            return Decimal("29.8")  # Beijing 30%
        if "ST" in str(stock_name or "").upper():
            return Decimal("4.95")  # ST 5%
        return Decimal("9.8")  # Main board 10%

    @classmethod
    def is_limit_up(cls, row: dict[str, Any]) -> bool:
        # 1. Primary: close >= limit_up_price (board-agnostic)
        close_price = cls._decimal(row.get("close_price"))
        limit_up_price = cls._decimal(row.get("limit_up_price"))
        if (
            close_price is not None
            and limit_up_price is not None
            and limit_up_price > Decimal("0")
            and close_price >= limit_up_price
        ):
            return True

        # 2. Explicit limit_up flag — if False, do NOT override with pct
        if "limit_up" in row:
            return bool(row.get("limit_up"))

        # 3. Board-aware pct threshold (last resort)
        pct = cls._decimal(row.get("pct_chg"))
        if pct is not None:
            threshold = cls.limit_up_threshold(
                str(row.get("stock_id") or ""),
                str(row.get("stock_name") or ""),
            )
            if pct >= threshold:
                return True

        return False

    @staticmethod
    def _decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

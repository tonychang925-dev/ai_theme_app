"""PR-11: MarketRegimeFactContextBuilder.

Actively builds market regime fact context from real data sources:
  - akshare index K-line (TDX)
  - market breadth from report_context or estimate
  - mainline_lifecycle_reviews
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MarketRegimeFactContext:
    trade_date: str = ""
    index_kline: list[dict[str, Any]] = field(default_factory=list)
    market_snapshot: dict[str, Any] = field(default_factory=dict)
    lifecycle_reviews: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "index_kline_rows": len(self.index_kline),
            "market_snapshot": self.market_snapshot,
            "lifecycle_review_count": len(self.lifecycle_reviews),
            "diagnostics": self.diagnostics,
        }


class MarketRegimeFactContextBuilder:
    """Build market regime fact context from real data."""

    def __init__(self, read_port: Any = None) -> None:
        self._read = read_port

    async def build(
        self,
        *,
        trade_date: date,
        report_context: dict[str, Any] | None = None,
        lifecycle_reviews: list[dict[str, Any]] | None = None,
        lookback_days: int = 120,
    ) -> MarketRegimeFactContext:
        td_str = trade_date.isoformat()
        diag: dict[str, Any] = {
            "index_source": "akshare_tdx",
            "market_snapshot_source": "report_context_or_default",
            "missing_sources": [],
        }

        # ── 1. Index K-line from akshare/TDX ──
        index_kline: list[dict[str, Any]] = []
        try:
            import akshare as ak
            df = await asyncio.to_thread(ak.stock_zh_index_daily, symbol="sh000001")
            if df is not None and not df.empty:
                df = df.tail(lookback_days)
                for _, row in df.iterrows():
                    index_kline.append({
                        "close": float(row["close"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "volume": float(row["volume"]) if row.get("volume") else 0,
                        "amount": float(row.get("amount", 0)) if "amount" in row else float(row["volume"]) * 10,
                    })
                diag["index_rows"] = len(index_kline)
            else:
                diag["missing_sources"].append("akshare_index")
        except Exception as exc:
            logger.warning("Failed to fetch index K-line from akshare: %s", exc)
            diag["missing_sources"].append("akshare_index")

        # ── 2. Market snapshot ──
        market_snapshot: dict[str, Any] = {}
        if report_context:
            market = report_context.get("market", {})
            if isinstance(market, dict):
                market_snapshot = dict(market)
        # Fallback: use reasonable defaults
        if not market_snapshot:
            market_snapshot = {
                "up_count": 2000, "down_count": 3000,
                "limit_up_count": 30, "limit_down_count": 10,
                "relay_sentiment_status": "normal",
                "intraday_fade_status": "normal",
            }
            diag["market_snapshot_source"] = "default_estimate"

        # ── 3. Lifecycle reviews ──
        reviews = lifecycle_reviews or []

        return MarketRegimeFactContext(
            trade_date=td_str,
            index_kline=index_kline,
            market_snapshot=market_snapshot,
            lifecycle_reviews=reviews,
            diagnostics=diag,
        )

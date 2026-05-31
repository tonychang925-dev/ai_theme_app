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

        # ── 1. Index K-line: prefer DB, fallback to akshare ──
        index_kline: list[dict[str, Any]] = []
        source = "none"
        try:
            import asyncpg
            conn = await asyncpg.connect("postgresql://localhost/stock_data_test", timeout=5)
            try:
                start = trade_date - __import__("datetime").timedelta(days=lookback_days)
                rows = await conn.fetch(
                    """SELECT trade_date, open, high, low, close, volume
                       FROM index_daily_kline
                       WHERE index_code='000001' AND market='1'
                         AND trade_date BETWEEN $1 AND $2
                       ORDER BY trade_date""",
                    start, trade_date,
                )
                if rows:
                    for r in rows:
                        index_kline.append({
                            "close": float(r["close"] or 0),
                            "high": float(r["high"] or 0),
                            "low": float(r["low"] or 0),
                            "volume": float(r["volume"] or 0),
                            "amount": 0,
                        })
                    source = "db.index_daily_kline"
                    diag["index_rows"] = len(index_kline)
            finally:
                await conn.close()
        except Exception:
            pass

        if not index_kline:
            try:
                import akshare as ak
                df = await asyncio.to_thread(ak.stock_zh_index_daily, symbol="sh000001")
                if df is not None and not df.empty:
                    df = df.tail(lookback_days)
                    for _, row in df.iterrows():
                        index_kline.append({
                            "close": float(row["close"]), "high": float(row["high"]),
                            "low": float(row["low"]), "volume": float(row.get("volume", 0)),
                            "amount": 0,
                        })
                    source = "akshare_tdx_live"
                    diag["index_rows"] = len(index_kline)
                else:
                    diag["missing_sources"].append("index_kline")
            except Exception as exc:
                logger.warning("Index K-line fetch failed: %s", exc)
                diag["missing_sources"].append("index_kline")

        diag["index_source"] = source

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

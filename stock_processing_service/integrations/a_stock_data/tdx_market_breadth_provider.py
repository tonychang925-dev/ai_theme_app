"""Phase 4.5.6-P0 — TDX Market Breadth Provider.

Computes full A-share market up_count/down_count from TDX/mootdx
real-time quotes across the complete stock universe.

This is the authoritative source for MarketBreadthMetrics, replacing
the invalid subject_stock_daily_snapshot fallback which only covers
~5134/5450 stocks (stocks without subject assignments were missing).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any


@dataclass
class MarketBreadthSnapshot:
    trade_date: date
    up_count: int
    down_count: int
    flat_count: int
    total_count: int
    suspended_count: int
    source: str = "tdx_quotes"
    source_endpoint: str = "mootdx.quotes"
    universe_source: str = "tdx_security_list"
    as_of: str = ""
    coverage_ratio: float = 0.0
    quality_status: str = "OK"


class TdxMarketBreadthProvider:
    """Fetch full A-share market breadth via TDX/mootdx.

    Uses mootdx to get the complete security list, then batch-fetches
    quotes to compute up_count/down_count/flat_count from price vs prev_close.
    """

    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from mootdx.quotes import Quotes
                self._client = Quotes.factory(market="std", timeout=15)
            except Exception:
                raise RuntimeError("mootdx not available — install mootdx to use TDX provider")
        return self._client

    async def fetch(self, trade_date: date) -> MarketBreadthSnapshot | None:
        """Fetch full market breadth for a trading date.

        Returns None if TDX is unavailable or coverage is too low.
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._fetch_sync, trade_date)

    def _fetch_sync(self, trade_date: date) -> MarketBreadthSnapshot | None:
        try:
            client = self._get_client()
        except RuntimeError:
            return None

        # ── Get full A-share stock list ──
        # TDX market codes: 0=SZ, 1=SH
        try:
            sz_stocks = client.stocks(market=0)  # Shenzhen
            sh_stocks = client.stocks(market=1)  # Shanghai
            bj_stocks = client.stocks(market=2)  # Beijing (if available)
        except Exception:
            return None

        all_stocks: list[str] = []
        try:
            # Convert to [market_code, stock_code] format for quotes()
            for s in sz_stocks:
                code = s.get("code", "") if isinstance(s, dict) else str(s)
                if code:
                    all_stocks.append(f"0#{code}")
            for s in sh_stocks:
                code = s.get("code", "") if isinstance(s, dict) else str(s)
                if code:
                    all_stocks.append(f"1#{code}")
            for s in bj_stocks:
                code = s.get("code", "") if isinstance(s, dict) else str(s)
                if code:
                    all_stocks.append(f"2#{code}")
        except Exception:
            return None

        total_universe = len(all_stocks)
        if total_universe < 4000:
            return None  # insufficient universe coverage

        # ── Batch-fetch quotes in chunks of 80 (TDX limit) ──
        up = down = flat = suspended = 0
        valid_count = 0
        chunk_size = 80

        for i in range(0, len(all_stocks), chunk_size):
            chunk = all_stocks[i:i + chunk_size]
            try:
                quotes = client.quotes(symbol=chunk)
                if quotes is None:
                    continue
                for q in quotes:
                    price = _float(q, "price")
                    last_close = _float(q, "last_close")
                    if price is None or last_close is None or last_close <= 0:
                        suspended += 1
                        continue
                    valid_count += 1
                    if price > last_close:
                        up += 1
                    elif price < last_close:
                        down += 1
                    else:
                        flat += 1
            except Exception:
                continue

        total_computed = up + down + flat + suspended
        coverage = valid_count / max(total_universe, 1)

        if coverage < 0.95:
            return None  # insufficient coverage for authoritative metric

        return MarketBreadthSnapshot(
            trade_date=trade_date,
            up_count=up,
            down_count=down,
            flat_count=flat,
            total_count=up + down + flat,
            suspended_count=suspended,
            source="tdx_quotes",
            source_endpoint="mootdx.quotes",
            universe_source="tdx_security_list",
            as_of=datetime.now(timezone.utc).isoformat(),
            coverage_ratio=round(coverage, 4),
            quality_status="OK" if coverage >= 0.97 else "PARTIAL",
        )


def _float(q: dict, key: str) -> float | None:
    """Extract float from TDX quote dict, handling various field names."""
    for k in (key, key.replace("_", ""), f"_{key}"):
        v = q.get(k)
        if v is not None:
            try:
                return float(v)
            except (ValueError, TypeError):
                pass
    return None

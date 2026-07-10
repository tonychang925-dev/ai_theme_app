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

    def fetch(self, trade_date: date) -> MarketBreadthSnapshot | None:
        """Fetch full market breadth for a trading date (synchronous)."""
        return self._fetch_sync(trade_date)

    def _fetch_sync(self, trade_date: date) -> MarketBreadthSnapshot | None:
        try:
            client = self._get_client()
        except RuntimeError:
            return None

        import re

        # ── Get full A-share stock list (DataFrames from mootdx) ──
        try:
            sz_df = client.stocks(market=0)
            sh_df = client.stocks(market=1)
        except Exception:
            return None

        def is_ashare(code):
            code_s = str(code)
            if not re.match(r'^\d{6}$', code_s): return False
            c = int(code_s)
            if 0 <= c <= 3999: return True       # SZ主板
            if 300000 <= c <= 301999: return True  # 创业板
            if 600000 <= c <= 605999: return True  # SH主板
            if 688000 <= c <= 689999: return True  # 科创板
            return False

        try:
            all_codes = []
            for df in [sz_df, sh_df]:
                if 'code' in df.columns:
                    codes = [str(c) for c in df['code'].tolist() if is_ashare(c)]
                    all_codes.extend(codes)
        except Exception:
            return None

        total_universe = len(all_codes)
        if total_universe < 4000:
            return None

        # ── Batch-fetch quotes (DataFrame API) ──
        up = down = flat = suspended = 0
        chunk_size = 80
        for i in range(0, len(all_codes), chunk_size):
            chunk = all_codes[i:i + chunk_size]
            try:
                quotes = client.quotes(symbol=chunk)
                if quotes is None or len(quotes) == 0:
                    suspended += len(chunk)
                    continue
                for _, row in quotes.iterrows():
                    price = row.get('price')
                    last = row.get('last_close')
                    if price is None or last is None or last <= 0 or price <= 0:
                        suspended += 1
                        continue
                    if price > last:
                        up += 1
                    elif price < last:
                        down += 1
                    else:
                        flat += 1
            except Exception:
                suspended += len(chunk)

        total_computed = up + down + flat
        coverage = total_computed / max(total_universe, 1)

        if coverage < 0.95:
            return None

        return MarketBreadthSnapshot(
            trade_date=trade_date,
            up_count=up,
            down_count=down,
            flat_count=flat,
            total_count=total_computed,
            suspended_count=suspended,
            source="tdx_quotes",
            source_endpoint="mootdx.quotes",
            universe_source="tdx_security_list",
            as_of=datetime.now(timezone.utc).isoformat(),
            coverage_ratio=round(coverage, 4),
            quality_status="OK" if coverage >= 0.97 else "PARTIAL",
        )

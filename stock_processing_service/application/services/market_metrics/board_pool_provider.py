"""M2.5 — BoardPoolProvider (a-stock-data integration).

Real implementation of the Provider Protocols using EastmoneyBoardClient.
Replaces streak backtracking with actual board pool data from Eastmoney.

Key benefits over current streak backtracking:
  - limit_days from API (no computation needed)
  - yesterday's 连板数 from 昨涨停池 (precise 晋级率 JOIN)
  - real fried_board_count from 炸板池 (not pct_chg heuristic)
  - real limit_down_count from 跌停池 (not SDS heuristic)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .contracts import (
    LimitUpMetrics, RelayEcologyMetrics, LossEffectMetrics, MetricSource,
)
from .providers import (
    LimitUpStock, YesterdayLimitUpStock, FriedBoardStock, LimitDownStock,
)


class BoardPoolProvider:
    """Production board pool data provider using Eastmoney API."""

    def __init__(self, client=None):
        self._client = client  # EastmoneyBoardClient, injected by caller
        self._cache: dict[str, Any] = {}

    async def get_sentiment(self, trade_date: date) -> dict:
        """Get board sentiment snapshot for a trading day."""
        sent = await self._client.fetch_sentiment(trade_date)
        return {
            "trade_date": trade_date.isoformat(),
            "zt_count": sent.zt_count,
            "zb_count": sent.zb_count,
            "dt_count": sent.dt_count,
            "break_rate": sent.break_rate,
            "max_height": sent.max_height,
            "ladder": sent.ladder,
        }

    async def get_limit_up_pool(self, trade_date: date) -> list[dict]:
        """Get 涨停池 with per-stock board heights."""
        stocks = await self._client.fetch_zt_pool(trade_date)
        return [{
            "code": s.code, "name": s.name,
            "pct": s.pct, "limit_days": s.limit_days,
            "zt_stat": s.zt_stat, "break_times": s.break_times,
            "seal_fund": s.seal_fund, "turnover": s.turnover,
            "amount": s.amount, "first_seal": s.first_seal,
            "industry": s.industry,
        } for s in stocks]

    async def get_yesterday_pool(self, trade_date: date) -> list[dict]:
        """Get 昨涨停池 — yesterday's ZT stocks with today's performance."""
        stocks = await self._client.fetch_yzt_pool(trade_date)
        return [{
            "code": s.code, "name": s.name,
            "today_pct": s.today_pct,
            "y_limit_days": s.y_limit_days,
            "y_first_seal": s.y_first_seal,
            "today_turnover": s.today_turnover,
            "industry": s.industry,
        } for s in stocks]

    async def get_fried_pool(self, trade_date: date) -> list[dict]:
        """Get 炸板池."""
        stocks = await self._client.fetch_zb_pool(trade_date)
        return [{"code": s.code, "name": s.name, "pct": s.pct,
                  "break_times": s.break_times, "first_seal": s.first_seal,
                  "amplitude": s.amplitude, "turnover": s.turnover}
                for s in stocks]

    async def get_dt_pool(self, trade_date: date) -> list[dict]:
        """Get 跌停池."""
        stocks = await self._client.fetch_dt_pool(trade_date)
        return [{"code": s.code, "name": s.name, "pct": s.pct,
                  "dt_days": s.dt_days, "open_times": s.open_times,
                  "industry": s.industry} for s in stocks]

    async def close(self):
        if self._client:
            await self._client.close()


def create_board_provider():
    """Factory: creates BoardPoolProvider with Eastmoney client.

    Call this from API handlers where cross-package imports work.
    """
    from integrations.a_stock_data.clients.eastmoney_board_client import EastmoneyBoardClient
    return BoardPoolProvider(client=EastmoneyBoardClient())

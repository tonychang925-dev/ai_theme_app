"""PR4.2.28f MarketMetricsService active capital source contract."""

from __future__ import annotations

from datetime import date

from stock_processing_service.application.services.market_metrics.service import MarketMetricsService
from stock_processing_service.application.services.market_metrics.contracts import (
    MarketBreadthMetrics,
    MetricSource,
)


class FakeConn:
    async def fetch(self, query: str, *args):
        if "eastmoney_board_pool_daily" in query:
            return [
                {"pool_type": "ZT", "stock_code": "A", "amount": 247955000000.0, "turnover": 1, "raw_json": {}},
                {"pool_type": "ZB", "stock_code": "B", "amount": 18529000000.0, "turnover": 1, "raw_json": {}},
                {"pool_type": "YZT", "stock_code": "C", "amount": 0.0, "turnover": 0, "raw_json": {}},
            ]
        raise AssertionError(f"Unexpected query: {query}")


async def test_build_capital_uses_board_pool_snapshot_not_multiplier() -> None:
    """TC-ID: PR4.2.28f-market-metrics-active-capital-source."""
    breadth = MarketBreadthMetrics(
        up_count=1,
        down_count=1,
        limit_up_count=75,
        limit_down_count=0,
        up_ratio=0.5,
        turnover_yi=10000.0,
        source=MetricSource("test"),
    )

    capital = await MarketMetricsService()._build_capital(FakeConn(), date(2026, 7, 9), breadth, {})

    assert capital.active_limitup_amount_yi == 2664.84
    assert capital.active_ratio == 0.2665
    assert "board_pool_zt_zb_v1:PARTIAL" in capital.source.source_detail
    assert "board_pool.yzt.amount_yi" in capital.source.source_detail

from __future__ import annotations

from collections import namedtuple
from decimal import Decimal

from stock_processing_service.domain.services.theme_kline_evidence_builder import (
    ThemeKlineEvidenceBuilder,
)


class CountingStockIds(list):
    def __init__(self, values):
        super().__init__(values)
        self.iterations = 0

    def __iter__(self):
        self.iterations += 1
        return super().__iter__()


def test_build_composite_builds_stock_id_set_once_for_large_history() -> None:
    """TC-POSTMARKET-CPU: avoid rebuilding set(stock_ids) for every trade date."""

    bar_type = namedtuple("Bar", ["stock_id", "pct_chg", "volume"])
    stock_ids = CountingStockIds([f"{idx:06d}.SZ" for idx in range(200)])
    trade_dates = [f"2026-04-{day:02d}" for day in range(1, 31)]
    bars_by_date = {
        td: [
            bar_type(stock_id=f"{idx:06d}.SZ", pct_chg=Decimal("1"), volume=Decimal("100"))
            for idx in range(300)
        ]
        for td in trade_dates
    }

    result = ThemeKlineEvidenceBuilder()._build_composite(
        stock_ids=stock_ids,
        bars_by_date=bars_by_date,
        trade_dates=trade_dates,
    )

    assert len(result) == len(trade_dates)
    assert stock_ids.iterations == 1

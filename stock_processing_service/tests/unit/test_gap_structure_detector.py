from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd

from stock_processing_service.domain.services.gap_structure_detector import GapStructureDetector


def test_detect_breakaway_gap() -> None:
    detector = GapStructureDetector(strict_window_pct=Decimal("1.0"), soft_window_pct=Decimal("1.5"))
    df = pd.DataFrame(
        [
            {"trade_date": date(2026, 3, 30), "high_price": Decimal("15.00"), "low_price": Decimal("13.21")},
            {"trade_date": date(2026, 3, 31), "high_price": Decimal("16.50"), "low_price": Decimal("15.83")},
            {"trade_date": date(2026, 4, 7), "high_price": Decimal("16.47"), "low_price": Decimal("14.80")},
        ]
    )
    gaps = detector.detect(
        df=df,
        current_trade_date=date(2026, 4, 7),
        current_low=Decimal("14.80"),
        current_close=Decimal("15.25"),
        ma_levels={"sma10": Decimal("15.05")},
        prev_low_level=Decimal("14.80"),
    )
    assert len(gaps) >= 1
    g = gaps[0]
    assert g.gap_lower == Decimal("15.00")
    assert g.gap_upper == Decimal("15.83")
    assert g.soft_hit is True


from __future__ import annotations

from datetime import date
from decimal import Decimal

from stock_processing_service.domain.services.kline_support_scorer_types import (
    GapStructure,
    MAStructure,
    PreviousLowStructure,
)
from stock_processing_service.domain.services.support_structure_resolver import SupportStructureResolver


def test_resolver_prioritizes_strict_gap() -> None:
    gap = GapStructure(
        gap_id="2026-03-30->2026-03-31",
        gap_from_date=date(2026, 3, 30),
        gap_to_date=date(2026, 3, 31),
        age_days=8,
        gap_lower=Decimal("15.00"),
        gap_upper=Decimal("15.83"),
        gap_size_pct=Decimal("5.53"),
        gap_type="breakaway",
        fill_ratio=Decimal("0.2"),
        is_filled=False,
        current_distance_pct=Decimal("0.5"),
        strict_hit=True,
        soft_hit=True,
    )
    prev_low = PreviousLowStructure(level=Decimal("14.80"), distance_pct=Decimal("1.0"), is_valid=True)
    ma_structures = [MAStructure(level=Decimal("15.50"), ma_type="sma5", distance_pct=Decimal("2.0"), is_valid=True)]
    resolved = SupportStructureResolver().resolve(
        gap_structures=[gap],
        prev_low_structure=prev_low,
        ma_structures=ma_structures,
    )
    assert resolved.support_type == "gap_support"
    assert resolved.primary_reason == "strict_gap_hit"
    assert resolved.gap_hit is True
    assert resolved.gap_hit_mode == "strict"


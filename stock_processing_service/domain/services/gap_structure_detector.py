from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from stock_processing_service.domain.services.kline_support_scorer_types import GapStructure


class GapStructureDetector:
    def __init__(
        self,
        *,
        strict_window_pct: Decimal = Decimal("1.0"),
        soft_window_pct: Decimal = Decimal("1.5"),
        gap_threshold_pct: Decimal = Decimal("0.1"),
        lookback_bars: int = 40,
    ) -> None:
        self._strict_window_pct = strict_window_pct
        self._soft_window_pct = soft_window_pct
        self._gap_threshold_pct = gap_threshold_pct
        self._lookback_bars = lookback_bars

    @staticmethod
    def _d(value: Any, default: str = "0") -> Decimal:
        if value is None:
            return Decimal(default)
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except Exception:
            return Decimal(default)

    @staticmethod
    def _distance_pct(price: Decimal, level: Decimal) -> Decimal:
        if level <= 0:
            return Decimal("999")
        return (abs(price - level) / level) * Decimal("100")

    def detect(
        self,
        *,
        df: pd.DataFrame,
        current_trade_date: date,
        current_low: Decimal,
        current_close: Decimal,
        ma_levels: dict[str, Decimal] | None = None,
        prev_low_level: Decimal | None = None,
    ) -> list[GapStructure]:
        if df.empty or len(df) < 2:
            return []

        ma_levels = ma_levels or {}
        rows = df.tail(self._lookback_bars).reset_index(drop=True)

        results: list[GapStructure] = []
        gap_threshold = self._gap_threshold_pct / Decimal("100")
        strict_pct = self._strict_window_pct
        soft_pct = self._soft_window_pct

        for i in range(1, len(rows)):
            prev_row = rows.iloc[i - 1]
            cur_row = rows.iloc[i]

            prev_date = prev_row["trade_date"]
            cur_date = cur_row["trade_date"]
            prev_high = self._d(prev_row["high_price"])
            cur_low_at_gap_day = self._d(cur_row["low_price"])

            if prev_high <= 0 or cur_low_at_gap_day <= 0:
                continue

            has_up_gap = cur_low_at_gap_day > prev_high * (Decimal("1") + gap_threshold)
            if not has_up_gap:
                continue

            gap_lower = prev_high
            gap_upper = cur_low_at_gap_day
            gap_size_pct = ((gap_upper - gap_lower) / gap_lower) * Decimal("100")
            distance_pct = self._distance_pct(current_low, gap_lower)
            strict_hit = distance_pct <= strict_pct
            soft_hit = distance_pct <= soft_pct

            gap_range = gap_upper - gap_lower
            fill_ratio = (gap_upper - current_low) / gap_range if gap_range > 0 else Decimal("0")
            is_filled = current_low < gap_lower

            near_ma = any(
                (level > 0 and self._distance_pct(gap_lower, level) <= Decimal("1.0"))
                for level in ma_levels.values()
            )
            near_prev_low = bool(
                prev_low_level and prev_low_level > 0 and self._distance_pct(gap_lower, prev_low_level) <= Decimal("1.0")
            )
            resonance_score = Decimal("8") if near_ma else Decimal("0")
            if near_prev_low:
                resonance_score += Decimal("6")

            age_days = max(0, (current_trade_date - cur_date).days)
            gap_type = "breakaway" if gap_size_pct >= Decimal("1.0") else "common"

            results.append(
                GapStructure(
                    gap_id=f"{prev_date}->{cur_date}",
                    gap_from_date=prev_date,
                    gap_to_date=cur_date,
                    age_days=age_days,
                    gap_lower=gap_lower,
                    gap_upper=gap_upper,
                    gap_size_pct=gap_size_pct.quantize(Decimal("0.0001")),
                    gap_type=gap_type,
                    fill_ratio=fill_ratio.quantize(Decimal("0.0001")),
                    is_filled=is_filled,
                    current_distance_pct=distance_pct.quantize(Decimal("0.0001")),
                    strict_hit=strict_hit,
                    soft_hit=soft_hit,
                    near_ma=near_ma,
                    near_prev_low=near_prev_low,
                    resonance_score=resonance_score,
                    debug={
                        "prev_high": str(prev_high),
                        "cur_low_at_gap_day": str(cur_low_at_gap_day),
                        "current_low": str(current_low),
                        "current_close": str(current_close),
                    },
                )
            )
        return results


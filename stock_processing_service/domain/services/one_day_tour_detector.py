from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class OneDayTourSignal:
    one_day_tour_flag: bool
    continuity_signal: str


class OneDayTourDetector:
    def detect(self, avg_pct_chg: Decimal, stock_count: int) -> OneDayTourSignal:
        # High spike with very narrow breadth is treated as one-day-tour risk.
        flag = avg_pct_chg >= Decimal("8") and stock_count <= 2
        signal = "weak_continuity" if flag else "normal"
        return OneDayTourSignal(one_day_tour_flag=flag, continuity_signal=signal)

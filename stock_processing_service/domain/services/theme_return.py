"""M7a-lite: Theme Return Attribution — the "soul truth" of M7.

Computes realized market returns for themes and their leaders.
This provides the ground truth that anchors M7b/M7c calibration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from stock_processing_service.domain.services.leader_scoring import LeaderScore


@dataclass(frozen=True)
class ThemeReturn:
    trade_date: date
    theme_name: str
    return_1d: float | None        # avg leader 1-day pct_chg
    return_3d: float | None        # avg leader 3-day cumulative return
    return_5d: float | None        # avg leader 5-day cumulative return
    leader_return_1d: float | None  # top1 leader 1-day return
    leader_return_3d: float | None
    leader_return_5d: float | None
    leader_count: int = 0
    top_stocks: list[dict[str, Any]] = field(default_factory=list)
    source_trace_id: str = ""


@dataclass(frozen=True)
class MarketTruth:
    """Per-stock market truth for one day."""
    stock_code: str
    stock_name: str
    pct_chg: float | None
    is_limit_up: bool
    consecutive_boards: int
    amount: float | None
    close_price: float | None


class ThemeReturnAttributionEngine:
    """Compute theme-level realized returns from market truth data."""

    def compute(
        self,
        trade_date: date,
        leaders: list[LeaderScore],
        market_truths: dict[str, MarketTruth],
        top_k: int = 5,
    ) -> list[ThemeReturn]:
        """Compute theme returns by aggregating top-K leader returns.

        Args:
            trade_date: scoring date
            leaders: leader scores from M4e
            market_truths: {stock_code: MarketTruth} for this day
            top_k: number of top leaders to aggregate

        Returns:
            One ThemeReturn per theme, sorted by return_1d descending.
        """
        td_str = trade_date.isoformat()

        # Group leaders by theme
        by_theme: dict[str, list[LeaderScore]] = {}
        for ls in leaders:
            by_theme.setdefault(ls.theme_name, []).append(ls)

        results: list[ThemeReturn] = []
        for theme, theme_leaders in by_theme.items():
            # Sort by leader_score desc, take top K
            top = sorted(theme_leaders, key=lambda x: -x.leader_score)[:top_k]

            returns_1d: list[float] = []
            for ls in top:
                truth = market_truths.get(ls.stock_code)
                if truth and truth.pct_chg is not None:
                    returns_1d.append(truth.pct_chg)

            # Compute aggregates
            leader_count = len(returns_1d)
            return_1d = sum(returns_1d) / leader_count if leader_count > 0 else None
            top1_return = returns_1d[0] if returns_1d else None

            # 3d/5d require multi-day data — set as None for single-day
            # These will be populated when running rolling replay

            top_stocks = [
                {
                    "stock_code": ls.stock_code,
                    "stock_name": ls.stock_name,
                    "leader_score": ls.leader_score,
                    "pct_chg": market_truths.get(ls.stock_code).pct_chg
                    if market_truths.get(ls.stock_code) else None,
                }
                for ls in top
            ]

            results.append(ThemeReturn(
                trade_date=trade_date,
                theme_name=theme,
                return_1d=round(return_1d, 4) if return_1d is not None else None,
                return_3d=None,  # requires rolling data
                return_5d=None,
                leader_return_1d=round(top1_return, 4) if top1_return is not None else None,
                leader_return_3d=None,
                leader_return_5d=None,
                leader_count=leader_count,
                top_stocks=top_stocks,
                source_trace_id=f"theme_return:{td_str}:{theme}",
            ))

        results.sort(key=lambda x: -(x.return_1d or 0))
        return results

    def build_actual_strength_map(
        self, theme_returns: list[ThemeReturn],
    ) -> dict[str, dict[str, Any]]:
        """Convert ThemeReturns to the format M7b ErrorEngine expects.

        Returns: {theme_name: {strength, rank}}
        """
        result: dict[str, dict[str, Any]] = {}
        for rank, tr in enumerate(theme_returns, 1):
            # Normalize return_1d to 0-1 strength scale
            # -10% → 0.0, 0% → 0.33, +10% → 0.67, +20% → 1.0
            raw = tr.return_1d or 0
            normalized = max(0.0, min(1.0, (raw + 10.0) / 30.0))
            result[tr.theme_name] = {
                "strength": round(normalized, 4),
                "rank": rank,
            }
        return result

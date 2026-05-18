"""Bar-to-Support adapter: converts raw bar dicts to domain service inputs.

Thin adapter layer. No trading rules — delegates to GapStructureDetector,
SupportStructureResolver, KlineSupportScorer.

Used by backfill services to avoid re-implementing support detection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from stock_processing_service.domain.services.gap_structure_detector import GapStructureDetector
from stock_processing_service.domain.services.kline_support_scorer_types import (
    GapStructure,
    MAStructure,
    PreviousLowStructure,
    ResolvedSupport,
)
from stock_processing_service.domain.services.support_structure_resolver import SupportStructureResolver


@dataclass
class BarSupportResult:
    """Unified support result for backfill consumption."""
    support_type: str | None
    support_strength: Decimal | None
    gap_not_filled: bool
    ma_support_hit: bool
    support_valid: bool
    evidence: dict = field(default_factory=dict)
    source: str = "domain_services"
    rule_version: str = "support_v0.2"


class BarSupportAdapter:
    """Convert raw bar dicts to domain service calls for support detection.

    Thin adapter — delegates all logic to existing domain services.
    """

    def __init__(self) -> None:
        self._gap_detector = GapStructureDetector()
        self._resolver = SupportStructureResolver()

    def resolve(
        self,
        *,
        current_bar: dict[str, Any],
        prior_bars: list[dict[str, Any]],
        ma5: Decimal | None = None,
        ma10: Decimal | None = None,
        ma20: Decimal | None = None,
    ) -> BarSupportResult:
        """Resolve support for a single stock on a single date.

        Args:
            current_bar: today's bar dict (from stock_daily_snapshot)
            prior_bars: prior bar dicts (sorted by trade_date DESC, most recent first)
            ma5/ma10/ma20: pre-computed moving averages
        """
        try:
            return self._resolve_inner(
                current_bar=current_bar,
                prior_bars=prior_bars,
                ma5=ma5, ma10=ma10, ma20=ma20,
            )
        except Exception:
            # Fallback: return empty result on any error
            return BarSupportResult(
                support_type=None,
                support_strength=None,
                gap_not_filled=False,
                ma_support_hit=False,
                support_valid=False,
                evidence={"error": "support_resolution_failed"},
                source="fallback_error",
            )

    def _resolve_inner(
        self,
        *,
        current_bar: dict[str, Any],
        prior_bars: list[dict[str, Any]],
        ma5: Decimal | None,
        ma10: Decimal | None,
        ma20: Decimal | None,
    ) -> BarSupportResult:
        low = _d(current_bar.get("low_price"))
        close = _d(current_bar.get("close_price"))
        pre_close = _d(current_bar.get("pre_close"))
        td = current_bar.get("trade_date")

        # ── Gap detection ──
        gap_structures: list[GapStructure] = []
        if prior_bars:
            df = _bars_to_df(prior_bars)
            if not df.empty:
                ma_levels = {}
                if ma5 is not None: ma_levels["ma5"] = ma5
                if ma10 is not None: ma_levels["ma10"] = ma10
                if ma20 is not None: ma_levels["ma20"] = ma20

                prev_low = _d(prior_bars[0].get("low_price")) if prior_bars else None

                gap_structures = self._gap_detector.detect(
                    df=df,
                    current_trade_date=td if isinstance(td, date) else date.today(),
                    current_low=low,
                    current_close=close,
                    ma_levels=ma_levels,
                    prev_low_level=prev_low,
                )

        # ── Previous low ──
        prev_low_struct = None
        if prior_bars:
            prev_low_val = _d(prior_bars[0].get("low_price"))
            if prev_low_val > 0:
                dist = abs(low - prev_low_val) / prev_low_val
                prev_low_struct = PreviousLowStructure(
                    level=prev_low_val,
                    distance_pct=dist * Decimal("100"),
                )

        # ── MA structures ──
        ma_structures: list[MAStructure] = []
        for ma_label, ma_val in [("ma5", ma5), ("ma10", ma10), ("ma20", ma20)]:
            if ma_val and ma_val > 0:
                dist = abs(low - ma_val) / ma_val
                ma_structures.append(MAStructure(
                    ma_type=ma_label,
                    level=ma_val,
                    distance_pct=dist * Decimal("100"),
                ))

        # ── Resolve ──
        resolved: ResolvedSupport = self._resolver.resolve(
            gap_structures=gap_structures,
            prev_low_structure=prev_low_struct,
            ma_structures=ma_structures,
        )

        # ── Map to simple result ──
        support_type = _map_support_type(resolved)
        support_strength = resolved.support_score if resolved.support_score > 0 else None
        gap_not_filled = any(
            not g.is_filled and (g.strict_hit or g.soft_hit)
            for g in gap_structures
        )
        ma_support_hit = any(
            m.distance_pct <= Decimal("2.0")
            for m in ma_structures
        )

        return BarSupportResult(
            support_type=support_type,
            support_strength=support_strength,
            gap_not_filled=gap_not_filled,
            ma_support_hit=ma_support_hit,
            support_valid=support_strength is not None and support_strength >= Decimal("30"),
            evidence={
                "resolved_type": resolved.support_type,
                "resolved_score": str(resolved.support_score),
                "gap_count": len(gap_structures),
                "ma_count": len(ma_structures),
                "refs": resolved.support_refs[:5],
            },
            source="domain_services",
        )


def _d(value: Any, default: str = "0") -> Decimal:
    if value is None: return Decimal(default)
    if isinstance(value, Decimal): return value
    try: return Decimal(str(value))
    except: return Decimal(default)


def _bars_to_df(bars: list[dict[str, Any]]) -> pd.DataFrame:
    """Convert bar dicts to DataFrame expected by GapStructureDetector."""
    rows = []
    for b in bars:
        rows.append({
            "trade_date": b.get("trade_date"),
            "open_price": float(b.get("open_price") or 0),
            "high_price": float(b.get("high_price") or 0),
            "low_price": float(b.get("low_price") or 0),
            "close_price": float(b.get("close_price") or 0),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("trade_date").reset_index(drop=True)
    return df


def _map_support_type(resolved: ResolvedSupport) -> str | None:
    """Map ResolvedSupport.support_type to simple labels."""
    st = str(resolved.support_type or "").lower().strip()
    if not st or st == "none":
        return None
    if "gap" in st:
        return "gap_support"
    if "prev_low" in st or "previous_low" in st:
        return "previous_low"
    if "ma" in st:
        return "ma_support"
    if "bb_lower" in st:
        return "bb_lower_support"
    return st

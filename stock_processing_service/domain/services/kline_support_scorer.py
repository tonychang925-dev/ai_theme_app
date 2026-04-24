from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO
from stock_processing_service.domain.services.gap_structure_detector import GapStructureDetector
from stock_processing_service.domain.services.kline_support_scorer_types import (
    MAStructure,
    PreviousLowStructure,
    SupportScoreResult,
    SupportTypeScore,
)
from stock_processing_service.domain.services.support_structure_resolver import SupportStructureResolver


class KlineSupportScorer:
    def __init__(
        self,
        *,
        gap_detector: GapStructureDetector | None = None,
        resolver: SupportStructureResolver | None = None,
    ) -> None:
        self._gap_detector = gap_detector or GapStructureDetector()
        self._resolver = resolver or SupportStructureResolver()

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

    def _to_history_frame(
        self,
        stock_id: str,
        current_bar: StockBarDTO,
        prior_rows: list[PriorSnapshotDTO],
        history_bars: list[StockBarDTO] | None = None,
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for hist in history_bars or []:
            if hist.stock_id != stock_id:
                continue
            rows.append(
                {
                    "trade_date": hist.trade_date,
                    "open_price": hist.open_price,
                    "high_price": hist.high_price,
                    "low_price": hist.low_price,
                    "close_price": hist.close_price,
                    "pre_close": hist.pre_close,
                    "pct_chg": hist.pct_chg,
                    "source_tag": "history_bars",
                }
            )
        for prior in prior_rows:
            payload = prior.payload or {}
            if prior.stock_id != stock_id:
                continue
            rows.append(
                {
                    "trade_date": prior.trade_date,
                    "open_price": self._d(payload.get("open_price")),
                    "high_price": self._d(payload.get("high_price")),
                    "low_price": self._d(payload.get("low_price")),
                    "close_price": self._d(payload.get("close_price")),
                    "pre_close": self._d(payload.get("pre_close")),
                    "pct_chg": self._d(payload.get("pct_chg")),
                    "source_tag": "prior_rows",
                }
            )
        rows.append(
            {
                "trade_date": current_bar.trade_date,
                "open_price": current_bar.open_price,
                "high_price": current_bar.high_price,
                "low_price": current_bar.low_price,
                "close_price": current_bar.close_price,
                "pre_close": current_bar.pre_close,
                "pct_chg": current_bar.pct_chg,
                "source_tag": "current_bar",
            }
        )
        rows.sort(key=lambda x: x["trade_date"])
        df = pd.DataFrame(rows)
        if df.empty:
            return df
        for col in ["open_price", "high_price", "low_price", "close_price", "pre_close", "pct_chg"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["close_price", "low_price", "high_price"]).copy()
        df = df[df["close_price"] > 0]
        return df

    @staticmethod
    def _distance_pct(a: Decimal, b: Decimal) -> Decimal:
        if b <= 0:
            return Decimal("999")
        return (abs(a - b) / b) * Decimal("100")

    def _build_prev_low_structure(self, df: pd.DataFrame, current_low: Decimal) -> PreviousLowStructure | None:
        if len(df) < 2:
            return None
        prev = df.iloc[-2]
        prev_low = self._d(prev["low_price"])
        if prev_low <= 0:
            return None
        distance_pct = self._distance_pct(current_low, prev_low)
        return PreviousLowStructure(
            level=prev_low,
            distance_pct=distance_pct.quantize(Decimal("0.0001")),
            is_valid=distance_pct <= Decimal("5"),
        )

    def _build_ma_structures(self, df: pd.DataFrame, current_low: Decimal) -> list[MAStructure]:
        if df.empty:
            return []
        result: list[MAStructure] = []
        close_s = pd.to_numeric(df["close_price"], errors="coerce")

        if len(close_s) >= 5:
            sma5 = self._d(close_s.rolling(5).mean().iloc[-1])
            if sma5 > 0:
                dist = self._distance_pct(current_low, sma5)
                result.append(MAStructure(level=sma5, ma_type="sma5", distance_pct=dist, is_valid=dist <= Decimal("5")))
        if len(close_s) >= 10:
            sma10 = self._d(close_s.rolling(10).mean().iloc[-1])
            if sma10 > 0:
                dist = self._distance_pct(current_low, sma10)
                result.append(MAStructure(level=sma10, ma_type="sma10", distance_pct=dist, is_valid=dist <= Decimal("5")))
        if len(close_s) >= 20:
            ema20 = self._d(close_s.ewm(span=20, adjust=False).mean().iloc[-1])
            if ema20 > 0:
                dist = self._distance_pct(current_low, ema20)
                result.append(MAStructure(level=ema20, ma_type="ema20", distance_pct=dist, is_valid=dist <= Decimal("5")))
        return result

    def score(
        self,
        stock_id: str,
        current_bar: StockBarDTO,
        prior_rows: list[PriorSnapshotDTO],
        history_bars: list[StockBarDTO] | None = None,
    ) -> SupportScoreResult:
        df = self._to_history_frame(stock_id, current_bar, prior_rows, history_bars=history_bars)
        if df.empty:
            return SupportScoreResult(
                support_type="none",
                support_level=Decimal("0"),
                support_score=Decimal("0"),
                support_count=0,
                combined_strength=Decimal("0"),
                gap_hit=False,
                gap_level=Decimal("0"),
                gap_distance_pct=Decimal("999"),
                gap_hit_mode="miss",
                gap_source="",
                support_refs=["scorer_rule=no_history_df"],
                support_types=[],
            )
        if len(df) < 2:
            ma_support = current_bar.close_price * Decimal("0.97")
            return SupportScoreResult(
                support_type="ma_support",
                support_level=ma_support,
                support_score=Decimal("65"),
                support_count=1,
                combined_strength=Decimal("0.6500"),
                gap_hit=False,
                gap_level=Decimal("0"),
                gap_distance_pct=Decimal("999"),
                gap_hit_mode="miss",
                gap_source="",
                support_refs=[f"fallback_ma_support={ma_support}"],
                support_types=[
                    SupportTypeScore(
                        support_type="ma_support",
                        support_level=ma_support,
                        strength=Decimal("0.65"),
                        source="fallback",
                        distance_pct=Decimal("0"),
                        zone_lower=ma_support,
                        zone_upper=ma_support,
                        hit_mode="miss",
                    )
                ],
            )

        current_low = self._d(current_bar.low_price)
        current_close = self._d(current_bar.close_price)

        ma_structures = self._build_ma_structures(df, current_low)
        prev_low_structure = self._build_prev_low_structure(df, current_low)
        ma_levels = {m.ma_type: m.level for m in ma_structures if m.level > 0}
        prev_low_level = prev_low_structure.level if prev_low_structure else None

        gap_structures = self._gap_detector.detect(
            df=df,
            current_trade_date=current_bar.trade_date,
            current_low=current_low,
            current_close=current_close,
            ma_levels=ma_levels,
            prev_low_level=prev_low_level,
        )
        resolved = self._resolver.resolve(
            gap_structures=gap_structures,
            prev_low_structure=prev_low_structure,
            ma_structures=ma_structures,
        )

        refs = list(resolved.support_refs)
        refs.append(f"gap_structures_count={len(gap_structures)}")
        for g in gap_structures[:40]:
            refs.append(
                "legacy_gap_candidate "
                f"id={g.gap_id} gap_level={g.gap_lower} zone=[{g.gap_lower},{g.gap_upper}] "
                f"current_low={current_low} current_close={current_close} "
                f"distance_pct={g.current_distance_pct} strict={g.strict_hit} soft={g.soft_hit} "
                f"resonance={g.resonance_score} source=gap_structure"
            )

        support_types: list[SupportTypeScore] = []
        for g in gap_structures:
            hit_mode = "strict" if g.strict_hit else "soft" if g.soft_hit else "miss"
            strength = Decimal("0.90") if g.strict_hit else Decimal("0.80") if g.soft_hit else Decimal("0.55")
            support_types.append(
                SupportTypeScore(
                    support_type="gap_support",
                    support_level=g.gap_lower,
                    strength=strength,
                    source="gap_structure",
                    distance_pct=g.current_distance_pct,
                    zone_lower=g.gap_lower,
                    zone_upper=g.gap_upper,
                    hit_mode=hit_mode,
                )
            )

        if prev_low_structure and prev_low_structure.is_valid:
            support_types.append(
                SupportTypeScore(
                    support_type="previous_low",
                    support_level=prev_low_structure.level,
                    strength=Decimal("0.78"),
                    source="previous_low",
                    distance_pct=prev_low_structure.distance_pct,
                )
            )
        for ma in ma_structures:
            if ma.is_valid:
                support_types.append(
                    SupportTypeScore(
                        support_type="ma_support",
                        support_level=ma.level,
                        strength=Decimal("0.70"),
                        source=ma.ma_type,
                        distance_pct=ma.distance_pct,
                    )
                )

        return SupportScoreResult(
            support_type=resolved.support_type,
            support_level=resolved.support_level,
            support_score=resolved.support_score,
            support_count=len(support_types),
            combined_strength=(resolved.support_score / Decimal("100")).quantize(Decimal("0.0001")),
            gap_hit=resolved.gap_hit,
            gap_hit_mode=resolved.gap_hit_mode,
            gap_source=resolved.gap_source,
            gap_level=resolved.gap_level,
            gap_distance_pct=resolved.gap_distance_pct,
            support_refs=refs,
            support_types=support_types,
        )

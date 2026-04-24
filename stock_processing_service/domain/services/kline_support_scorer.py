from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO


@dataclass(frozen=True)
class SupportTypeScore:
    support_type: str
    support_level: Decimal
    strength: Decimal
    source: str
    distance_pct: Decimal


@dataclass(frozen=True)
class SupportScoreResult:
    support_type: str
    support_level: Decimal
    support_score: Decimal
    support_count: int = 0
    combined_strength: Decimal = Decimal("0")
    gap_hit: bool = False
    gap_level: Decimal = Decimal("0")
    gap_distance_pct: Decimal = Decimal("999")
    support_refs: list[str] = field(default_factory=list)
    support_types: list[SupportTypeScore] = field(default_factory=list)


class KlineSupportScorer:
    """
    Open-source based support scorer (pandas) for stock_processing_service.
    It mirrors old-chain ideas: gap support + previous_low + MA supports + simple confluence bonus.
    """

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
    def _score_level(candidate_type: str, level: Decimal, current_low: Decimal, base: Decimal, source: str) -> SupportTypeScore:
        if level <= 0:
            return SupportTypeScore(candidate_type, Decimal("0"), Decimal("0"), source, Decimal("999"))
        distance_pct = (abs(current_low - level) / level) * Decimal("100")
        # closer support level => stronger
        distance_penalty = min(Decimal("0.45"), distance_pct / Decimal("20"))
        strength = max(Decimal("0"), min(Decimal("1"), base - distance_penalty))
        return SupportTypeScore(candidate_type, level, strength, source, distance_pct)

    def _detect_gap_support_from_history(self, df: pd.DataFrame, current_low: Decimal) -> list[SupportTypeScore]:
        """
        Legacy-aligned gap support detection:
        - Scan historical upward gaps (day_i.low > day_{i-1}.high * (1+0.1%))
        - Treat gap lower edge (prev high) as support candidate
        - Keep candidates reasonably near current price (<= 8% distance)
        """
        candidates: list[SupportTypeScore] = []
        if len(df) < 3:
            return candidates

        gap_threshold = Decimal("0.001")
        last_idx = len(df) - 1
        for i in range(1, len(df)):
            prev_high = self._d(df.iloc[i - 1]["high_price"])
            cur_low = self._d(df.iloc[i]["low_price"])
            if prev_high <= 0 or cur_low <= 0:
                continue
            if cur_low <= prev_high * (Decimal("1") + gap_threshold):
                continue

            gap_support_level = prev_high
            distance_pct = (abs(current_low - gap_support_level) / gap_support_level) * Decimal("100")
            if distance_pct > Decimal("8"):
                continue

            # recency decay: fresher gap support is stronger
            age = last_idx - i
            recency_bonus = max(Decimal("0"), Decimal("0.12") - Decimal(str(age)) * Decimal("0.004"))
            base = min(Decimal("0.95"), Decimal("0.78") + recency_bonus)
            candidates.append(
                self._score_level(
                    candidate_type="gap_support",
                    level=gap_support_level,
                    current_low=current_low,
                    base=base,
                    source=f"historical_gap_i={i}",
                )
            )
        return candidates

    def score(
        self,
        stock_id: str,
        current_bar: StockBarDTO,
        prior_rows: list[PriorSnapshotDTO],
        history_bars: list[StockBarDTO] | None = None,
    ) -> SupportScoreResult:
        df = self._to_history_frame(stock_id, current_bar, prior_rows, history_bars=history_bars)
        # fallback to legacy simple behavior when history is insufficient
        if len(df) < 2:
            ma_support = current_bar.close_price * Decimal("0.97")
            return SupportScoreResult(
                support_type="ma_support",
                support_level=ma_support,
                support_score=Decimal("65"),
                support_count=1,
                combined_strength=Decimal("0.65"),
                support_refs=[f"fallback_ma_support={ma_support}"],
                support_types=[
                    SupportTypeScore(
                        support_type="ma_support",
                        support_level=ma_support,
                        strength=Decimal("0.65"),
                        source="fallback",
                        distance_pct=Decimal("0"),
                    )
                ],
            )

        cur = df.iloc[-1]
        prev = df.iloc[-2]
        current_low = self._d(cur["low_price"])
        current_close = self._d(cur["close_price"])
        prev_high = self._d(prev["high_price"])
        prev_low = self._d(prev["low_price"])
        prev_close = self._d(prev["close_price"])

        support_candidates: list[SupportTypeScore] = []
        refs: list[str] = []

        # 1) gap_support detection (legacy semantics)
        if prev_high > 0:
            gap_threshold = Decimal("0.001")
            has_up_gap = current_low > (prev_high * (Decimal("1") + gap_threshold))
            gap_support_level = prev_high
            if has_up_gap:
                refs.append(f"up_gap_detected prev_high={prev_high}")
                score = self._score_level(
                    candidate_type="gap_support",
                    level=gap_support_level,
                    current_low=current_low,
                    base=Decimal("0.95"),
                    source="gap_support",
                )
                support_candidates.append(score)
                # legacy-compatible implicit support: gap often coexists with previous_low structure
                support_candidates.append(
                    self._score_level(
                        candidate_type="previous_low",
                        level=gap_support_level,
                        current_low=current_low,
                        base=min(Decimal("0.60"), score.strength * Decimal("0.75")),
                        source="gap_implied_previous_low",
                    )
                )

        # historical gap scan (not only previous-day gap)
        support_candidates.extend(self._detect_gap_support_from_history(df, current_low))

        # 2) previous_low support
        if prev_low > 0:
            support_candidates.append(
                self._score_level(
                    candidate_type="previous_low",
                    level=prev_low,
                    current_low=current_low,
                    base=Decimal("0.80"),
                    source="previous_low",
                )
            )

        # 3) previous_close support
        if prev_close > 0:
            support_candidates.append(
                self._score_level(
                    candidate_type="previous_close",
                    level=prev_close,
                    current_low=current_low,
                    base=Decimal("0.72"),
                    source="previous_close",
                )
            )

        # 4) open-source indicators via pandas
        close_s = pd.to_numeric(df["close_price"], errors="coerce")
        high_s = pd.to_numeric(df["high_price"], errors="coerce")
        low_s = pd.to_numeric(df["low_price"], errors="coerce")
        ma5 = self._d(close_s.rolling(5).mean().iloc[-1]) if len(close_s) >= 5 else Decimal("0")
        ma10 = self._d(close_s.rolling(10).mean().iloc[-1]) if len(close_s) >= 10 else Decimal("0")
        ema20 = self._d(close_s.ewm(span=20, adjust=False).mean().iloc[-1]) if len(close_s) >= 20 else Decimal("0")
        bb_mid = close_s.rolling(20).mean() if len(close_s) >= 20 else pd.Series(dtype="float64")
        bb_std = close_s.rolling(20).std(ddof=0) if len(close_s) >= 20 else pd.Series(dtype="float64")
        bb_lower = self._d((bb_mid - (bb_std * 2)).iloc[-1]) if len(close_s) >= 20 else Decimal("0")

        if ma5 > 0:
            support_candidates.append(
                self._score_level("sma5_support", ma5, current_low, Decimal("0.65"), "sma5")
            )
        if ma10 > 0:
            support_candidates.append(
                self._score_level("sma10_support", ma10, current_low, Decimal("0.74"), "sma10")
            )
        if ema20 > 0:
            support_candidates.append(
                self._score_level("ema20_support", ema20, current_low, Decimal("0.82"), "ema20")
            )
        if bb_lower > 0:
            support_candidates.append(
                self._score_level("bb_lower_support", bb_lower, current_low, Decimal("0.86"), "bb_lower")
            )

        # 5) pivot supports (classic)
        if prev_high > 0 and prev_low > 0 and prev_close > 0:
            pivot = (prev_high + prev_low + prev_close) / Decimal("3")
            s1 = (pivot * Decimal("2")) - prev_high
            s2 = pivot - (prev_high - prev_low)
            if s1 > 0:
                support_candidates.append(
                    self._score_level("pivot_support1", s1, current_low, Decimal("0.75"), "pivot_s1")
                )
            if s2 > 0:
                support_candidates.append(
                    self._score_level("pivot_support2", s2, current_low, Decimal("0.70"), "pivot_s2")
                )

        # 6) fibonacci nearest support (recent swing high/low)
        lookback = min(len(df), 60)
        if lookback >= 20:
            recent = df.iloc[-lookback:]
            swing_high = self._d(recent["high_price"].max())
            swing_low = self._d(recent["low_price"].min())
            swing_range = swing_high - swing_low
            if swing_high > 0 and swing_low > 0 and swing_range > 0:
                fib_levels = [
                    swing_high - swing_range * Decimal("0.382"),
                    swing_high - swing_range * Decimal("0.5"),
                    swing_high - swing_range * Decimal("0.618"),
                ]
                fib_supports = [lvl for lvl in fib_levels if lvl <= current_close]
                if fib_supports:
                    fib_nearest = max(fib_supports)
                    support_candidates.append(
                        self._score_level("fibonacci_support", fib_nearest, current_low, Decimal("0.68"), "fibonacci")
                    )

        # map all supports for downstream introspection
        support_candidates = [s for s in support_candidates if s.strength > 0]
        if not support_candidates:
            return SupportScoreResult(
                support_type="none",
                support_level=Decimal("0"),
                support_score=Decimal("0"),
                support_count=0,
                combined_strength=Decimal("0"),
                support_refs=["no_support_candidate"],
                support_types=[],
            )

        support_candidates.sort(key=lambda x: x.strength, reverse=True)
        primary = support_candidates[0]
        top3 = support_candidates[:3]
        avg_top3 = sum((s.strength for s in top3), Decimal("0")) / Decimal(str(len(top3)))
        resonance_bonus = min(Decimal("0.20"), Decimal(str(max(0, len(support_candidates) - 1))) * Decimal("0.05"))
        combined_strength = min(Decimal("1"), primary.strength * Decimal("0.65") + avg_top3 * Decimal("0.35") + resonance_bonus)
        support_score = (combined_strength * Decimal("100")).quantize(Decimal("0.01"))
        gap_candidates = [x for x in support_candidates if x.support_type == "gap_support"]
        gap_hit = len(gap_candidates) > 0 and bool(gap_candidates[0].distance_pct <= Decimal("5"))
        gap_level = gap_candidates[0].support_level if gap_candidates else Decimal("0")
        gap_distance_pct = gap_candidates[0].distance_pct if gap_candidates else Decimal("999")

        refs.extend(
            [
                f"primary={primary.support_type}:{primary.support_level}",
                f"primary_strength={primary.strength}",
                f"combined_strength={combined_strength}",
                f"support_count={len(support_candidates)}",
            ]
        )
        for item in support_candidates[:5]:
            refs.append(
                f"type={item.support_type}|level={item.support_level}|strength={item.strength}|dist={item.distance_pct}"
            )

        # normalize old/new naming bridge
        mapped_type = primary.support_type
        if mapped_type == "previous_low":
            mapped_type = "prev_low_support"
        elif mapped_type.startswith("sma") or mapped_type.startswith("ema"):
            mapped_type = "ma_support"
        elif mapped_type == "bb_lower_support":
            mapped_type = "ma_support"
        elif mapped_type.startswith("pivot_"):
            mapped_type = "platform_support"

        return SupportScoreResult(
            support_type=mapped_type,
            support_level=primary.support_level,
            support_score=support_score,
            support_count=len(support_candidates),
            combined_strength=combined_strength,
            gap_hit=gap_hit,
            gap_level=gap_level,
            gap_distance_pct=gap_distance_pct,
            support_refs=refs,
            support_types=support_candidates,
        )

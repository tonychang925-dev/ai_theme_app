from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from stock_processing_service.contracts.dto import PriorSnapshotDTO, StockBarDTO
from stock_processing_service.domain.services.gap_structure_detector import GapStructureDetector
from stock_processing_service.domain.services.kline_support_scorer_types import (
    BBLowerStructure,
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

    def _build_bb_lower_structure(self, df: pd.DataFrame, current_low: Decimal) -> BBLowerStructure | None:
        """布林下轨支撑检测 — 使用 pandas_ta 或裸计算。"""
        if len(df) < 20:
            return None
        close_s = pd.to_numeric(df["close_price"], errors="coerce")
        try:
            # 优先 pandas_ta
            import pandas_ta as pta
            bb = pta.bbands(close_s, length=20, std=2.0)
            if bb is not None and "BBL_20_2.0" in bb.columns:
                bb_lower = self._d(bb["BBL_20_2.0"].iloc[-1])
            else:
                raise ImportError("bbands column not found")
        except Exception:
            # fallback: 裸计算
            sma20 = close_s.rolling(20).mean()
            std20 = close_s.rolling(20).std()
            bb_lower = self._d((sma20 - 2.0 * std20).iloc[-1])
        if bb_lower <= 0:
            return None
        dist = self._distance_pct(current_low, bb_lower)
        return BBLowerStructure(
            level=bb_lower,
            distance_pct=dist,
            is_valid=dist <= Decimal("5"),
        )

    @staticmethod
    def _compute_rsi14(df: pd.DataFrame) -> Decimal | None:
        """RSI14 计算 — 优先 pandas_ta，fallback 裸计算。"""
        if len(df) < 14:
            return None
        close_s = pd.to_numeric(df["close_price"], errors="coerce")
        try:
            import pandas_ta as pta
            rsi_series = pta.rsi(close_s, length=14)
            if rsi_series is not None and len(rsi_series) > 0:
                val = float(rsi_series.iloc[-1])
                if pd.notna(val):
                    return Decimal(str(round(val, 2)))
        except Exception:
            pass
        # fallback: 裸计算
        delta = close_s.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, 1e-9)
        rsi = 100.0 - (100.0 / (1.0 + rs))
        val = float(rsi.iloc[-1])
        if pd.notna(val):
            return Decimal(str(round(val, 2)))
        return None

    @staticmethod
    def _safe_atr_pct(atr_value, close_price: float) -> float:
        atr = float(atr_value or 0.0)
        if atr <= 0 or close_price <= 0:
            return 0.0
        return atr / close_price * 100.0

    @staticmethod
    def _score_level_candidate(
        *, candidate_type: str, level: Decimal, anchor_price: Decimal,
        atr_pct: float, base_weight: float,
    ) -> dict:
        """旧链 _score_level_candidate 距离公式：proximity = 1 - distance / tolerance"""
        lv = float(level)
        ap = float(anchor_price)
        if lv <= 0 or ap <= 0:
            return {"type": candidate_type, "level": level, "strength": Decimal("0")}
        distance_pct = abs(ap - lv) / lv * 100.0
        tolerance_pct = min(8.0, max(1.5, atr_pct * 2.2 if atr_pct > 0 else 2.8))
        proximity = max(0.0, 1.0 - distance_pct / tolerance_pct)
        directional = 1.0 if lv <= ap * 1.02 else 0.80
        strength = min(1.0, max(0.0, base_weight * proximity * directional))
        return {"type": candidate_type, "level": level, "strength": Decimal(str(round(strength, 4)))}

    @staticmethod
    def _detect_prior_breakout_level(df: pd.DataFrame) -> Decimal:
        """旧链 _detect_prior_breakout_level 复刻：前15日（排除最近3日）最高价作为突破回踩支撑位。"""
        try:
            if df.empty or "high_price" not in df.columns:
                return Decimal("0")
            high_s = pd.to_numeric(df["high_price"], errors="coerce")
            if len(high_s) < 18:
                return Decimal("0")
            window = high_s.iloc[-18:-3]
            level = float(window.max() or 0.0)
            if level <= 0:
                return Decimal("0")
            return Decimal(str(round(level, 4)))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _compute_pivot_points(df: pd.DataFrame) -> dict[str, Decimal]:
        """旧链 _calculate_pivot_points 日线枢轴点：P=(H+L+C)/3, S1=2P-H, S2=P-(H-L)"""
        try:
            if len(df) < 2:
                return {}
            prev = df.iloc[-2]
            h = float(prev.get("high_price", 0) or 0)
            l = float(prev.get("low_price", 0) or 0)
            c = float(prev.get("close_price", 0) or 0)
            pivot = (h + l + c) / 3.0
            if pivot <= 0:
                return {}
            s1 = 2.0 * pivot - h
            s2 = pivot - (h - l)
            result: dict[str, Decimal] = {}
            if s1 > 0:
                result["support1"] = Decimal(str(round(s1, 4)))
            if s2 > 0 and s2 < s1:
                result["support2"] = Decimal(str(round(s2, 4)))
            return result
        except Exception:
            return {}

    @staticmethod
    def _compute_fibonacci_support(df: pd.DataFrame, current_price: Decimal) -> Decimal:
        """旧链 _calculate_fibonacci_levels：最近10天高低点，斐波那契回撤 nearest_support。"""
        try:
            if len(df) < 10:
                return Decimal("0")
            highs = pd.to_numeric(df["high_price"], errors="coerce")
            lows = pd.to_numeric(df["low_price"], errors="coerce")
            lookback = min(10, len(highs))
            recent_high = float(highs.iloc[-lookback:].max())
            recent_low = float(lows.iloc[-lookback:].min())
            if recent_high <= recent_low:
                return Decimal("0")
            price_range = recent_high - recent_low
            fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
            cp = float(current_price)
            nearest_support = Decimal("0")
            nearest_dist = float("inf")
            for level in fib_levels:
                retracement = recent_high - price_range * level
                if retracement < cp:
                    dist = abs((cp - retracement) / cp * 100) if cp > 0 else 100
                    if dist < nearest_dist:
                        nearest_dist = dist
                        nearest_support = Decimal(str(round(retracement, 4)))
            return nearest_support
        except Exception:
            return Decimal("0")

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
                support_refs=["scorer_rule=insufficient_history"],
                support_types=[],
            )

        current_low = self._d(current_bar.low_price)
        current_close = self._d(current_bar.close_price)

        # ── ATR（距离容差计算基础）──
        atr14 = Decimal("0")
        try:
            high_s = pd.to_numeric(df["high_price"], errors="coerce")
            low_s = pd.to_numeric(df["low_price"], errors="coerce")
            close_s = pd.to_numeric(df["close_price"], errors="coerce")
            if len(high_s) >= 15:
                tr = pd.DataFrame({
                    "h_l": high_s - low_s,
                    "h_pc": abs(high_s - close_s.shift(1)),
                    "l_pc": abs(low_s - close_s.shift(1)),
                }).max(axis=1)
                atr14 = self._d(tr.rolling(14).mean().iloc[-1])
        except Exception:
            pass
        atr_pct = self._safe_atr_pct(atr14, float(current_close))

        ma_structures = self._build_ma_structures(df, current_low)
        prev_low_structure = self._build_prev_low_structure(df, current_low)
        bb_lower_structure = self._build_bb_lower_structure(df, current_low)
        rsi14 = self._compute_rsi14(df)

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
            bb_lower_structure=bb_lower_structure,
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

        anchor = current_low if current_low > 0 else current_close
        support_types: list[SupportTypeScore] = []

        # ── 旧链距离评分公式：_score_level_candidate(type, level, anchor, atr_pct, base_weight) ──
        _sc = lambda t, lv, bw: self._score_level_candidate(
            candidate_type=t, level=lv, anchor_price=anchor, atr_pct=atr_pct, base_weight=bw)

        for g in gap_structures:
            hit_mode = "strict" if g.strict_hit else "soft" if g.soft_hit else "miss"
            bw = 0.95 if g.strict_hit else 0.80 if g.soft_hit else 0.55
            scored = _sc("gap_support", g.gap_lower, bw)
            support_types.append(SupportTypeScore(
                support_type="gap_support", support_level=g.gap_lower,
                strength=scored["strength"], source="gap_structure",
                distance_pct=g.current_distance_pct,
                zone_lower=g.gap_lower, zone_upper=g.gap_upper, hit_mode=hit_mode))

        if prev_low_structure and prev_low_structure.is_valid:
            scored = _sc("previous_low", prev_low_structure.level, 0.80)
            support_types.append(SupportTypeScore(
                support_type="previous_low", support_level=prev_low_structure.level,
                strength=scored["strength"], source="previous_low",
                distance_pct=prev_low_structure.distance_pct))

        if bb_lower_structure and bb_lower_structure.is_valid:
            scored = _sc("bb_lower_support", bb_lower_structure.level, 0.86)
            support_types.append(SupportTypeScore(
                support_type="bb_lower_support", support_level=bb_lower_structure.level,
                strength=scored["strength"], source="bb_lower",
                distance_pct=bb_lower_structure.distance_pct))

        _ma_w = {"sma5": 0.65, "sma10": 0.74, "ema20": 0.82}
        for ma in ma_structures:
            if ma.is_valid:
                scored = _sc(f"{ma.ma_type}_support", ma.level, _ma_w.get(ma.ma_type, 0.70))
                support_types.append(SupportTypeScore(
                    support_type=f"{ma.ma_type}_support", support_level=ma.level,
                    strength=scored["strength"], source=ma.ma_type,
                    distance_pct=ma.distance_pct))

        if len(df) >= 2:
            prev_close = self._d(df["close_price"].iloc[-2])
            if prev_close > 0:
                scored = _sc("previous_close", prev_close, 0.72)
                support_types.append(SupportTypeScore(
                    support_type="previous_close", support_level=prev_close,
                    strength=scored["strength"], source="previous_close",
                    distance_pct=self._distance_pct(current_low, prev_close)))

        breakout_level = self._detect_prior_breakout_level(df)
        if breakout_level > Decimal("0"):
            scored = _sc("prior_breakout_retest", breakout_level, 0.92)
            if current_close >= breakout_level:
                scored["strength"] = min(Decimal("1.0"), scored["strength"] * Decimal("1.08"))
            support_types.append(SupportTypeScore(
                support_type="prior_breakout_retest", support_level=breakout_level,
                strength=scored["strength"], source="prior_breakout_retest",
                distance_pct=self._distance_pct(current_low, breakout_level)))

        pivot_points = self._compute_pivot_points(df)
        for pk, pv in pivot_points.items():
            if pv > Decimal("0"):
                scored = _sc(f"pivot_{pk}", pv, 0.75)
                support_types.append(SupportTypeScore(
                    support_type=f"pivot_{pk}", support_level=pv,
                    strength=scored["strength"], source="daily_pivot",
                    distance_pct=self._distance_pct(current_low, pv)))

        fib_support = self._compute_fibonacci_support(df, current_close)
        if fib_support > Decimal("0"):
            scored = _sc("fibonacci_support", fib_support, 0.68)
            support_types.append(SupportTypeScore(
                support_type="fibonacci_support", support_level=fib_support,
                strength=scored["strength"], source="fibonacci_retracement",
                distance_pct=self._distance_pct(current_low, fib_support)))

        # ── O2: RSI 超卖加分（旧链 §27.2）──
        rsi_bonus = Decimal("0")
        if rsi14 is not None:
            if Decimal("0") < rsi14 <= Decimal("35"):
                rsi_bonus = Decimal("0.04")
            elif Decimal("35") < rsi14 <= Decimal("45"):
                rsi_bonus = Decimal("0.02")

        # ── O3: 多支撑共振加分（每多一种有效支撑类型+0.03，上限0.12）──
        unique_types: set[str] = set()
        for st in support_types:
            unique_types.add(st.support_type)
        resonance_bonus = min(Decimal(str(len(unique_types) - 1)) * Decimal("0.03"), Decimal("0.12"))

        # ── 旧链复合评分：primary * 0.65 + avg_top3 * 0.35 + resonance + oversold ──
        if support_types:
            sorted_types = sorted(support_types, key=lambda x: x.strength, reverse=True)
            primary = sorted_types[0]
            top3 = sorted_types[:3]
            avg_top3 = sum(s.strength for s in top3) / Decimal(str(len(top3)))
            combined = primary.strength * Decimal("0.65") + avg_top3 * Decimal("0.35") + resonance_bonus + rsi_bonus
            combined = min(max(combined, Decimal("0")), Decimal("1"))
            support_score = round(combined * Decimal("100"), 2)
            support_type = primary.support_type
            support_level = primary.support_level
        else:
            combined = Decimal("0")
            support_score = Decimal("0")
            support_type = "none"
            support_level = Decimal("0")

        refs.append(f"rsi14={rsi14}")
        refs.append(f"rsi_bonus={rsi_bonus}")
        refs.append(f"resonance_bonus={resonance_bonus}")
        refs.append(f"unique_support_types={len(unique_types)}")

        return SupportScoreResult(
            support_type=support_type,
            support_level=support_level,
            support_score=support_score,
            support_count=len(support_types),
            combined_strength=combined.quantize(Decimal("0.0001")),
            gap_hit=resolved.gap_hit,
            gap_hit_mode=resolved.gap_hit_mode,
            gap_source=resolved.gap_source,
            gap_level=resolved.gap_level,
            gap_distance_pct=resolved.gap_distance_pct,
            support_refs=refs,
            support_types=support_types,
        )

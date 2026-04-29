from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

import pandas as pd

from stock_service.config import StockServiceConfig
from stock_service.services.kline_data_service import KlineDataService


@dataclass
class SupportScoreResult:
    support_score: float
    support_type: str
    support_level: float
    support_strength: float
    support_breakdown: Dict[str, Any]
    evidence_refs: List[Dict[str, Any]]


class WeakToStrongSupportScorer:
    """独立支撑评分器：输出统一支撑评分结构，供候选池构建器消费。"""

    RULE_VERSION = "weak_to_strong_support.v2.opensource"

    def __init__(self, config: Optional[StockServiceConfig] = None):
        self.config = config or StockServiceConfig()
        self.kline_service = KlineDataService(
            {
                "host": self.config.postgres_host,
                "port": self.config.postgres_port,
                "database": self.config.postgres_database,
                "user": self.config.postgres_user,
                "password": self.config.postgres_password,
            }
        )

    async def close(self) -> None:
        await self.kline_service.close()

    async def score(
        self,
        stock_id: str,
        trade_date: date,
        current_bar: Dict[str, Any],
        prev_bar: Dict[str, Any],
    ) -> SupportScoreResult:
        raw_stock_id = (stock_id or "").split(".", 1)[0]
        fallback = self._fallback_result(current_bar=current_bar, prev_bar=prev_bar)

        try:
            kline_data = await self.kline_service.get_kline_data(raw_stock_id, trade_date, days_before=90, days_after=0)
            if not kline_data:
                return fallback

            df = pd.DataFrame(kline_data)
            if df.empty or "trade_date" not in df.columns:
                return fallback
            df["trade_date"] = pd.to_datetime(df["trade_date"])
            df = df.sort_values("trade_date").reset_index(drop=True)
            df = df[df["close_price"] > 0]
            if len(df) < 6:
                return fallback

            indicators = self._build_indicator_pack(df)
            weekly_context = self._build_weekly_context(df)
            gap_analysis = await self.kline_service.analyze_gap_support(raw_stock_id, trade_date)
            advanced_analysis = await self.kline_service.analyze_advanced_support(raw_stock_id, trade_date, lookback_days=60)

            current_low = float(current_bar.get("low_price") or 0.0) or float(df.iloc[-1]["low_price"] or 0.0)
            current_close = float(current_bar.get("close_price") or 0.0) or float(df.iloc[-1]["close_price"] or 0.0)
            prev_low = float(prev_bar.get("low_price") or 0.0)
            prev_close = float(prev_bar.get("close_price") or 0.0)
            atr_pct = self._safe_atr_pct(indicators.get("atr14"), current_close)

            support_types: List[Dict[str, Any]] = []
            if gap_analysis.get("has_support"):
                support_types.append(
                    self._score_level_candidate(
                        candidate_type=str(gap_analysis.get("support_type") or "gap_support"),
                        level=float(gap_analysis.get("support_level") or 0.0),
                        anchor_price=current_low or current_close,
                        atr_pct=atr_pct,
                        base_weight=0.95,
                        source="kline_gap_support",
                        source_strength=float(gap_analysis.get("support_strength") or 0.0),
                    )
                )

            if prev_low > 0:
                support_types.append(
                    self._score_level_candidate(
                        candidate_type="previous_low",
                        level=prev_low,
                        anchor_price=current_low or current_close,
                        atr_pct=atr_pct,
                        base_weight=0.80,
                        source="prev_day_low_distance",
                    )
                )
            if prev_close > 0:
                support_types.append(
                    self._score_level_candidate(
                        candidate_type="previous_close",
                        level=prev_close,
                        anchor_price=current_close or current_low,
                        atr_pct=atr_pct,
                        base_weight=0.72,
                        source="prev_day_close_distance",
                    )
                )

            for candidate_type, level_key, base_weight in [
                ("sma5_support", "sma5", 0.65),
                ("sma10_support", "sma10", 0.74),
                ("ema20_support", "ema20", 0.82),
                ("bb_lower_support", "bb_lower", 0.86),
            ]:
                level = float(indicators.get(level_key) or 0.0)
                if level > 0:
                    support_types.append(
                        self._score_level_candidate(
                            candidate_type=candidate_type,
                            level=level,
                            anchor_price=current_low or current_close,
                            atr_pct=atr_pct,
                            base_weight=base_weight,
                            source=f"opensource_ta_{level_key}",
                        )
                    )

            # 关键结构支撑：前高突破后的回踩确认
            # 语义：若当前回落到“前期显著高点”附近并收回其上，属于更强的结构性支撑。
            breakout_level = self._detect_prior_breakout_level(df)
            if breakout_level > 0:
                breakout_candidate = self._score_level_candidate(
                    candidate_type="prior_breakout_retest",
                    level=breakout_level,
                    anchor_price=current_low or current_close,
                    atr_pct=atr_pct,
                    base_weight=0.92,
                    source="prior_breakout_retest",
                )
                if float(breakout_candidate.get("strength") or 0.0) > 0:
                    close_reclaim_bonus = 1.08 if current_close >= breakout_level else 1.0
                    breakout_candidate["strength"] = round(
                        min(1.0, float(breakout_candidate.get("strength") or 0.0) * close_reclaim_bonus),
                        4,
                    )
                    support_types.append(breakout_candidate)

            pivots = ((advanced_analysis or {}).get("pivot_points", {}).get("daily_pivots", {}))
            for key in ("support1", "support2"):
                level = float(pivots.get(key) or 0.0)
                if level > 0:
                    support_types.append(
                        self._score_level_candidate(
                            candidate_type=f"pivot_{key}",
                            level=level,
                            anchor_price=current_low or current_close,
                            atr_pct=atr_pct,
                            base_weight=0.75,
                            source="daily_pivot_support_distance",
                        )
                    )

            fib_support = float((advanced_analysis or {}).get("fibonacci_levels", {}).get("nearest_support", {}).get("price") or 0.0)
            if fib_support > 0:
                support_types.append(
                    self._score_level_candidate(
                        candidate_type="fibonacci_support",
                        level=fib_support,
                        anchor_price=current_close or current_low,
                        atr_pct=atr_pct,
                        base_weight=0.68,
                        source="fibonacci_nearest_support",
                    )
                )

            support_types = [x for x in support_types if float(x.get("strength") or 0.0) > 0.0]
            if not support_types:
                return fallback

            support_types.sort(key=lambda x: float(x.get("strength") or 0.0), reverse=True)
            primary = support_types[0]
            top3 = support_types[:3]
            avg_top3 = sum(float(item.get("strength") or 0.0) for item in top3) / float(len(top3))
            primary_strength = float(primary.get("strength") or 0.0)
            resonance_bonus = min(0.12, max(len(support_types) - 1, 0) * 0.03)
            oversold_bonus = 0.0
            rsi14 = float(indicators.get("rsi14") or 0.0)
            if 0 < rsi14 <= 35.0:
                oversold_bonus = 0.04
            elif 35.0 < rsi14 <= 45.0:
                oversold_bonus = 0.02

            combined_strength = min(1.0, max(0.0, primary_strength * 0.65 + avg_top3 * 0.35 + resonance_bonus + oversold_bonus))
            support_score = round(combined_strength * 100.0, 2)

            evidence_refs = [
                {
                    "table": "subject_stock_daily_snapshot",
                    "stock_id": raw_stock_id,
                    "trade_date": trade_date.isoformat(),
                    "rule_version": self.RULE_VERSION,
                    "ta_backend": indicators.get("ta_backend"),
                }
            ]
            for item in support_types[:6]:
                evidence_refs.append(
                    {
                        "source": item.get("source"),
                        "support_type": item.get("type"),
                        "support_level": float(item.get("level") or 0.0),
                        "support_strength": float(item.get("strength") or 0.0),
                        "distance_pct": float(item.get("distance_pct") or 0.0),
                    }
                )

            return SupportScoreResult(
                support_score=support_score,
                support_type=str(primary.get("type") or "none"),
                support_level=float(primary.get("level") or 0.0),
                support_strength=support_score,
                support_breakdown={
                    "support_types": support_types,
                    "support_count": len(support_types),
                    "combined_strength": combined_strength,
                    "ta_backend": indicators.get("ta_backend"),
                    "atr_pct": atr_pct,
                    "rsi14": rsi14,
                    "weekly_context": weekly_context,
                    "weekly_filter_pass": bool(weekly_context.get("weekly_filter_pass") or False),
                    "weekly_data_sufficient": bool(weekly_context.get("weekly_data_sufficient") or False),
                    "weekly_trend_up": bool(weekly_context.get("weekly_trend_up") or False),
                    "weekly_position_pct": float(weekly_context.get("weekly_position_pct") or 0.0),
                    "weekly_pullback_pct": float(weekly_context.get("weekly_pullback_pct") or 0.0),
                    "weekly_high_fall_flag": bool(weekly_context.get("weekly_high_fall_flag") or False),
                    "fallback_used": False,
                },
                evidence_refs=evidence_refs,
            )
        except Exception:
            return fallback

    def _build_indicator_pack(self, df: pd.DataFrame) -> Dict[str, float]:
        close = pd.to_numeric(df["close_price"], errors="coerce")
        high = pd.to_numeric(df["high_price"], errors="coerce")
        low = pd.to_numeric(df["low_price"], errors="coerce")
        result: Dict[str, float] = {
            "sma5": 0.0,
            "sma10": 0.0,
            "ema20": 0.0,
            "atr14": 0.0,
            "rsi14": 0.0,
            "bb_lower": 0.0,
            "ta_backend": "none",
        }

        try:
            import pandas_ta as pta  # type: ignore

            result["sma5"] = self._safe_last(pta.sma(close, length=5))
            result["sma10"] = self._safe_last(pta.sma(close, length=10))
            result["ema20"] = self._safe_last(pta.ema(close, length=20))
            result["atr14"] = self._safe_last(pta.atr(high, low, close, length=14))
            result["rsi14"] = self._safe_last(pta.rsi(close, length=14))
            bbands = pta.bbands(close, length=20, std=2.0)
            if bbands is not None and not bbands.empty:
                lower_col = next((c for c in bbands.columns if "BBL_" in c), "")
                if lower_col:
                    result["bb_lower"] = self._safe_last(bbands[lower_col])
            result["ta_backend"] = "pandas_ta"
            return result
        except Exception:
            pass

        try:
            from ta.momentum import RSIIndicator  # type: ignore
            from ta.trend import EMAIndicator, SMAIndicator  # type: ignore
            from ta.volatility import AverageTrueRange, BollingerBands  # type: ignore

            result["sma5"] = float(SMAIndicator(close=close, window=5).sma_indicator().iloc[-1] or 0.0)
            result["sma10"] = float(SMAIndicator(close=close, window=10).sma_indicator().iloc[-1] or 0.0)
            result["ema20"] = float(EMAIndicator(close=close, window=20).ema_indicator().iloc[-1] or 0.0)
            result["atr14"] = float(AverageTrueRange(high=high, low=low, close=close, window=14).average_true_range().iloc[-1] or 0.0)
            result["rsi14"] = float(RSIIndicator(close=close, window=14).rsi().iloc[-1] or 0.0)
            result["bb_lower"] = float(BollingerBands(close=close, window=20, window_dev=2).bollinger_lband().iloc[-1] or 0.0)
            result["ta_backend"] = "ta"
            return result
        except Exception:
            return result

    def _safe_last(self, series: Any) -> float:
        if series is None:
            return 0.0
        try:
            value = float(series.iloc[-1])
        except Exception:
            return 0.0
        if value != value:
            return 0.0
        return value

    def _score_level_candidate(
        self,
        *,
        candidate_type: str,
        level: float,
        anchor_price: float,
        atr_pct: float,
        base_weight: float,
        source: str,
        source_strength: float = 0.0,
    ) -> Dict[str, Any]:
        if level <= 0 or anchor_price <= 0:
            return {"type": candidate_type, "level": level, "strength": 0.0, "source": source, "distance_pct": 100.0}
        distance_pct = abs(anchor_price - level) / level * 100.0
        tolerance_pct = min(8.0, max(1.5, atr_pct * 2.2 if atr_pct > 0 else 2.8))
        proximity = max(0.0, 1.0 - distance_pct / tolerance_pct)
        directional_factor = 1.0 if level <= anchor_price * 1.02 else 0.80
        extra = source_strength if source_strength <= 1.0 else source_strength / 100.0
        quality_factor = 0.85 + min(max(extra, 0.0), 1.0) * 0.15
        strength = min(1.0, max(0.0, base_weight * proximity * directional_factor * quality_factor))
        return {
            "type": candidate_type,
            "level": level,
            "strength": round(strength, 4),
            "source": source,
            "distance_pct": round(distance_pct, 4),
        }

    def _safe_atr_pct(self, atr_value: Any, close_price: float) -> float:
        atr = float(atr_value or 0.0)
        if atr <= 0 or close_price <= 0:
            return 0.0
        return atr / close_price * 100.0

    def _detect_prior_breakout_level(self, df: pd.DataFrame) -> float:
        """
        在最近窗口中识别“突破前高”的关键位，作为回踩支撑候选。
        用法：取当前日前一段时间的滚动最高点，避免把当日高点当成支撑。
        """
        try:
            if df.empty or "high_price" not in df.columns:
                return 0.0
            high_s = pd.to_numeric(df["high_price"], errors="coerce")
            if len(high_s) < 18:
                return 0.0
            # 排除最近3根，使用其前15根的最高点作为前高参考
            window = high_s.iloc[-18:-3]
            level = float(window.max() or 0.0)
            if level <= 0:
                return 0.0
            return round(level, 4)
        except Exception:
            return 0.0

    def _build_weekly_context(self, df: pd.DataFrame) -> Dict[str, Any]:
        """周线中期结构：识别“低位上涨后的回踩”，过滤高位下跌。"""
        result: Dict[str, Any] = {
            "weekly_data_sufficient": False,
            "weekly_filter_pass": False,
            "weekly_trend_up": False,
            "weekly_position_pct": 1.0,
            "weekly_pullback_pct": 0.0,
            "weekly_high_fall_flag": False,
            "weekly_ma5": 0.0,
            "weekly_ma10": 0.0,
            "weekly_close_last": 0.0,
            "weekly_high_26w": 0.0,
            "weekly_low_26w": 0.0,
        }
        try:
            if df.empty or "trade_date" not in df.columns:
                return result
            wdf = df.copy()
            wdf["trade_date"] = pd.to_datetime(wdf["trade_date"])
            wdf = wdf.sort_values("trade_date")
            weekly = (
                wdf.set_index("trade_date")
                .resample("W-FRI")
                .agg(
                    {
                        "open_price": "first",
                        "high_price": "max",
                        "low_price": "min",
                        "close_price": "last",
                    }
                )
                .dropna()
            )
            if len(weekly) < 8:
                return result

            close_s = pd.to_numeric(weekly["close_price"], errors="coerce")
            high_s = pd.to_numeric(weekly["high_price"], errors="coerce")
            low_s = pd.to_numeric(weekly["low_price"], errors="coerce")
            close_last = float(close_s.iloc[-1] or 0.0)
            if close_last <= 0:
                return result

            ma5 = float(close_s.rolling(5).mean().iloc[-1] or 0.0)
            ma10 = float(close_s.rolling(10).mean().iloc[-1] or 0.0) if len(close_s) >= 10 else ma5
            window = min(26, len(weekly))
            high_26w = float(high_s.tail(window).max() or 0.0)
            low_26w = float(low_s.tail(window).min() or 0.0)
            high_12w = float(high_s.tail(min(12, len(weekly))).max() or 0.0)

            position_pct = 1.0
            if high_26w > low_26w:
                position_pct = max(0.0, min(1.0, (close_last - low_26w) / (high_26w - low_26w)))
            pullback_pct = 0.0
            if high_12w > 0:
                pullback_pct = max(0.0, min(1.0, (high_12w - close_last) / high_12w))

            trend_up = bool(ma5 > 0 and ma10 > 0 and ma5 >= ma10 * 0.985 and close_last >= ma10 * 0.96)
            low_mid_zone = bool(position_pct <= 0.60)
            pullback_after_rise = bool(0.02 <= pullback_pct <= 0.22)
            high_fall_flag = bool(position_pct >= 0.72 and pullback_pct >= 0.05)
            weekly_filter_pass = bool(trend_up and low_mid_zone and pullback_after_rise and (not high_fall_flag))

            result.update(
                {
                    "weekly_data_sufficient": True,
                    "weekly_filter_pass": weekly_filter_pass,
                    "weekly_trend_up": trend_up,
                    "weekly_position_pct": round(position_pct, 4),
                    "weekly_pullback_pct": round(pullback_pct, 4),
                    "weekly_high_fall_flag": high_fall_flag,
                    "weekly_ma5": round(ma5, 4),
                    "weekly_ma10": round(ma10, 4),
                    "weekly_close_last": round(close_last, 4),
                    "weekly_high_26w": round(high_26w, 4),
                    "weekly_low_26w": round(low_26w, 4),
                }
            )
        except Exception:
            return result
        return result

    def _fallback_result(self, *, current_bar: Dict[str, Any], prev_bar: Dict[str, Any]) -> SupportScoreResult:
        pct_chg = float(current_bar.get("pct_chg") or 0.0)
        prev_pct_chg = float(prev_bar.get("pct_chg") or 0.0)
        support_type = "none"
        base = 20.0
        if prev_pct_chg <= -3.5 and pct_chg > -3.5:
            support_type = "previous_low"
            base = 60.0
        elif -1.5 <= pct_chg <= 1.5:
            support_type = "ma5"
            base = 55.0
        elif pct_chg > 1.5:
            support_type = "break_recover"
            base = 50.0
        return SupportScoreResult(
            support_score=round(base, 2),
            support_type=support_type,
            support_level=float(prev_bar.get("close_price") or 0.0),
            support_strength=round(base, 2),
            support_breakdown={
                "support_types": [{"type": support_type, "strength": base / 100.0}],
                "support_count": 0 if support_type == "none" else 1,
                "combined_strength": base / 100.0,
                "fallback_used": True,
            },
            evidence_refs=[{"source": "fallback_rule", "rule_version": self.RULE_VERSION}],
        )

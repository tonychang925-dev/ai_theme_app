"""PR-11B: Reusable K-line technical analysis kernel.

Computes MA5/10/20/60, support/resistance, volume patterns, MACD, trend state.
Stateless — pure function operating on OHLCV data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _float(val: Any) -> float | None:
    try:
        if val is None or val == "": return None
        return float(val)
    except Exception: return None


@dataclass
class KlineTechnicalAnalyzer:
    """Compute technical indicators from OHLCV data."""

    def analyze(self, bars: list[dict[str, Any]]) -> dict[str, Any]:
        if not bars or len(bars) < 5:
            return _empty_result()

        closes = [_float(b.get("close")) for b in bars if _float(b.get("close")) is not None]
        highs = [_float(b.get("high")) for b in bars if _float(b.get("high")) is not None]
        lows = [_float(b.get("low")) for b in bars if _float(b.get("low")) is not None]
        volumes = [_float(b.get("volume")) or 0 for b in bars]
        amounts = [_float(b.get("amount")) or 0 for b in bars]

        if not closes: return _empty_result()

        ma = self._ma_analysis(closes)
        sr = self._support_resistance(closes, highs, lows)
        vol = self._volume_analysis(volumes, amounts)
        macd = self._macd_analysis(closes)
        trend = self._trend_analysis(closes, ma, sr, vol, macd)

        return {"ma": ma, "support_resistance": sr, "volume": vol, "macd": macd, "trend": trend}

    @staticmethod
    def _ma_analysis(closes: list[float]) -> dict[str, Any]:
        n = len(closes)
        ma5 = sum(closes[-5:]) / min(n, 5) if n >= 5 else None
        ma10 = sum(closes[-10:]) / min(n, 10) if n >= 10 else None
        ma20 = sum(closes[-20:]) / min(n, 20) if n >= 20 else None
        ma60 = sum(closes[-60:]) / min(n, 60) if n >= 60 else None
        latest = closes[-1]

        def slope(ma_curr: float | None, ma_prev: float | None) -> str:
            if ma_curr is None or ma_prev is None: return "unknown"
            return "up" if ma_curr > ma_prev else ("down" if ma_curr < ma_prev else "flat")

        ma5_prev = sum(closes[-10:-5]) / 5 if n >= 10 else None
        ma10_prev = sum(closes[-20:-10]) / 10 if n >= 20 else None
        ma20_prev = sum(closes[-40:-20]) / 20 if n >= 40 else None

        above = [ma5 and latest > ma5, ma10 and latest > ma10, ma20 and latest > ma20, ma60 and latest > ma60]
        alignment = "bullish" if all(above) else ("bearish" if all(not x for x in above) else "mixed")

        risk_flags = []
        if ma20 and latest < ma20: risk_flags.append("指数在MA20下方")
        if ma60 and latest < ma60: risk_flags.append("指数在MA60下方")

        return {"ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
                "above_ma5": bool(ma5 and latest > ma5),
                "above_ma10": bool(ma10 and latest > ma10),
                "above_ma20": bool(ma20 and latest > ma20),
                "above_ma60": bool(ma60 and latest > ma60),
                "ma5_slope": slope(ma5, ma5_prev),
                "ma10_slope": slope(ma10, ma10_prev),
                "ma20_slope": slope(ma20, ma20_prev),
                "ma_alignment": alignment, "risk_flags": risk_flags}

    @staticmethod
    def _support_resistance(closes: list[float], highs: list[float], lows: list[float]) -> dict[str, Any]:
        n = len(closes)
        if n < 20: return _empty_sr()
        recent_highs = highs[-20:] if highs else []
        recent_lows = lows[-20:] if lows else []
        r_high = max(recent_highs) if recent_highs else None
        s_low = min(recent_lows) if recent_lows else None
        latest = closes[-1]
        prev_close = closes[-2] if n >= 2 else None

        pct_support = ((latest - s_low) / latest * 100) if s_low and latest > 0 else None
        pct_resist = ((r_high - latest) / latest * 100) if r_high and latest > 0 else None

        support_broken = bool(s_low is not None and latest < s_low)
        resistance_broken = bool(r_high is not None and latest > r_high)
        near_support = bool(pct_support is not None and 0 <= pct_support <= 1.0)
        near_resistance = bool(pct_resist is not None and 0 <= pct_resist <= 2.0)

        if support_broken:
            support_status = "support_broken"
        elif near_support:
            support_status = "near_support"
        else:
            support_status = "support_available" if s_low is not None else "unknown"

        if resistance_broken:
            resistance_status = "resistance_broken"
        elif near_resistance:
            resistance_status = "near_resistance"
        else:
            resistance_status = "resistance_available" if r_high is not None else "unknown"

        return {
            "nearest_support_level": s_low,
            "nearest_resistance_level": r_high,
            "support_level": s_low,
            "resistance_level": r_high,
            "support_distance_pct": round(pct_support, 2) if pct_support is not None else None,
            "resistance_distance_pct": round(pct_resist, 2) if pct_resist is not None else None,
            "support_broken": support_broken,
            "resistance_broken": resistance_broken,
            "near_support": near_support,
            "near_resistance": near_resistance,
            "previous_close": prev_close,
            "latest_close": latest,
        }

    @staticmethod
    def _volume_analysis(volumes: list[float], amounts: list[float]) -> dict[str, Any]:
        n = len(volumes)
        if n < 5: return _empty_vol()
        v5 = sum(volumes[-5:]) / 5
        v20 = sum(volumes[-20:-1]) / min(n - 1, 19) if n >= 21 else v5
        ratio5 = v5 / v20 if v20 > 0 else 1.0
        a5 = sum(amounts[-5:]) / 5
        a20 = sum(amounts[-20:-1]) / min(n - 1, 19) if n >= 21 else a5
        aratio5 = a5 / a20 if a20 > 0 else 1.0

        pattern = "normal"
        if ratio5 > 2.0: pattern = "spike_high"
        elif ratio5 > 1.3: pattern = "expanding"
        elif ratio5 < 0.5: pattern = "shrinking_significantly"
        elif ratio5 < 0.85: pattern = "shrinking_rebound" if closes_trend_up(volumes) is None else "shrinking"

        return {"volume_ratio_5d": round(ratio5, 2), "volume_ratio_20d": round(ratio5, 2),
                "amount_ratio_5d": round(aratio5, 2), "volume_pattern": pattern}

    @staticmethod
    def _macd_analysis(closes: list[float]) -> dict[str, Any]:
        if len(closes) < 26: return _empty_macd()
        ema12 = _ema(closes, 12)
        ema26 = _ema(closes, 26)
        dif = round(ema12 - ema26, 2)
        dea_l = [_ema(closes[:i + 1] if i < 9 else [ema12 - _ema(closes[:i + 1], 26) for _ in range(9)], 9) for i in range(len(closes))]
        dea_val = _ema([_ema(closes[:i + 1], 12) - _ema(closes[:i + 1], 26) for i in range(len(closes))], 9) if len(closes) >= 35 else dif
        hist = round(dif - dea_val, 2)

        if dif > 0:
            state = "above_zero_bullish" if hist > 0 else "above_zero_weakening"
        else:
            state = "below_zero_bearish" if hist < 0 else "below_zero_weak_rebound"
        cross = "golden_cross" if dif > dea_val else "dead_cross"

        return {"dif": dif, "dea": round(dea_val, 2), "hist": hist,
                "macd_state": state, "macd_cross_state": cross}

    @staticmethod
    def _trend_analysis(closes: list[float], ma: dict, sr: dict, vol: dict, macd: dict) -> dict[str, Any]:
        latest = closes[-1]
        ma20 = ma.get("ma20")
        above_ma20 = ma.get("above_ma20", False)
        ma20_slope = ma.get("ma20_slope", "unknown")
        ratio5 = vol.get("volume_ratio_5d", 1.0)
        near_r = sr.get("near_resistance", False)
        near_s = sr.get("near_support", False)
        macd_state = macd.get("macd_state", "unknown")

        score = 50
        if above_ma20: score += 10
        if ma.get("above_ma60"): score += 5
        if ma20_slope == "up": score += 8
        elif ma20_slope == "down": score -= 10
        if ratio5 > 1.1: score += 5
        elif ratio5 < 0.7: score -= 5

        if not above_ma20 and ma20_slope == "down" and ratio5 < 1.0 and ratio5 > 0.5 and (near_r or latest < ma20) and latest > min(closes[-20:]) * 1.02:
            state = "downtrend_rebound"
            score = min(score, 42)
        elif above_ma20 and ma20_slope in {"up", "flat"}:
            state = "bullish_trend"
            score = max(score, 58)
        elif not above_ma20 and ma20_slope == "down":
            state = "bearish_trend"
            score = min(score, 35)
        else:
            state = "neutral_box"

        flags = []
        if not above_ma20: flags.append("指数在MA20下方")
        if ratio5 < 0.85 and not above_ma20: flags.append("缩量反抽")
        if near_r: flags.append("接近压力位")
        if near_s: flags.append("接近支撑位")
        for f in ma.get("risk_flags", []): flags.append(f)

        if sr.get("support_broken") and macd_state in {"below_zero_bearish", "below_zero_weak_rebound"}:
            flags.append("支撑失守且MACD偏弱")
        if sr.get("resistance_broken"):
            flags.append("压力位突破")

        return {"trend_state": state, "trend_score": score, "risk_flags": flags[:5]}


# ── helpers ──

def _ema(values: list[float], span: int) -> float:
    if not values: return 0.0
    alpha = 2.0 / (span + 1)
    result = values[0]
    for v in values[1:]:
        result = alpha * v + (1 - alpha) * result
    return result


def _empty_result() -> dict[str, Any]:
    return {"ma": {}, "support_resistance": _empty_sr(), "volume": _empty_vol(),
            "macd": _empty_macd(), "trend": {"trend_state": "unknown", "trend_score": None, "risk_flags": []}}


def _empty_sr() -> dict[str, Any]:
    return {
        "nearest_support_level": None,
        "nearest_resistance_level": None,
        "support_level": None,
        "resistance_level": None,
        "support_distance_pct": None,
        "resistance_distance_pct": None,
        "support_broken": False,
        "resistance_broken": False,
        "near_support": False,
        "near_resistance": False,
        "previous_close": None,
        "latest_close": None,
    }


def _empty_vol() -> dict[str, Any]:
    return {"volume_ratio_5d": None, "volume_ratio_20d": None, "amount_ratio_5d": None, "volume_pattern": "unknown"}


def _empty_macd() -> dict[str, Any]:
    return {"dif": None, "dea": None, "hist": None, "macd_state": "unknown", "macd_cross_state": "unknown"}


def closes_trend_up(volumes: list[float]) -> bool | None:
    if len(volumes) < 5: return None
    return volumes[-1] > volumes[-2]  # simplified

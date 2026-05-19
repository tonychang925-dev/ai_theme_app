"""v2.6 Enhanced Pattern/Volume Structure Detector.

Pure domain service — computes pattern features from daily bar history.
No SQL, no I/O. Replaces the v0.8b stub in get_stock_pattern_judgement().

Enhancements:
  - 高量不破 (high volume bar unbroken)
  - 倍量不穿 (2nd highest volume bar not pierced)
  - 缩量回踩 (volume shrinkage on pullback to support)
  - 放量突破 (volume expansion on breakout above resistance)
  - 烂板回撤深度 (bad limit up pullback quality)
  - 前高检测 (prior swing high detection)
  - Risk pattern detection
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class VolumeBar:
    trade_date: date
    volume: float
    high: float
    low: float
    close: float
    open: float
    pre_close: float = 0.0
    pct_chg: float = 0.0


@dataclass
class EnhancedPatternResult:
    stock_id: str
    volume_pattern_status: str = "平量"
    volume_ratio_vs_prior: float = 1.0
    volume_ratio_vs_20d_avg: float = 1.0
    breakout_status: str = "未突破"
    breakout_level: float = 0.0
    breakout_distance_pct: float = 0.0
    pullback_status: str = "正常"
    pullback_to_support_distance: float = 0.0
    pattern_labels: list[str] = field(default_factory=list)
    high_volume_unbroken: bool = False
    high_volume_bar_date: str = ""
    high_volume_level: float = 0.0
    high_volume_distance_pct: float = 0.0
    double_volume_not_pierced: bool = False
    second_high_vol_level: float = 0.0
    bad_limit_up_pullback_pct: float = 0.0
    bad_limit_up_quality: str = ""
    prior_swing_high: float = 0.0
    prior_swing_high_distance_pct: float = 0.0
    risk_pattern_status: str = "正常"
    evidence: dict[str, Any] = field(default_factory=dict)


class EnhancedPatternDetector:
    LOOKBACK_DAYS = 20

    def detect(
        self,
        stock_id: str,
        current: VolumeBar,
        history: list[VolumeBar],
        *,
        support_level: float = 0.0,
        support_type: str = "",
        is_bad_limit_up: bool = False,
        prev_day_limit_up: bool = False,
    ) -> EnhancedPatternResult:
        result = EnhancedPatternResult(stock_id=stock_id)
        prior = history[-1] if history else None
        if not history:
            result.pattern_labels = ["insufficient_history"]
            return result

        self._detect_volume(current, prior, history, result)
        self._detect_pullback(current, prior, result, support_level)
        self._detect_breakout(current, history, result)
        self._detect_high_vol_unbroken(current, history, result)
        self._detect_double_vol_not_pierced(current, history, result)
        self._detect_pattern_labels(current, prior, result, is_bad_limit_up, prev_day_limit_up)
        self._detect_prior_swing_high(history, result)

        if is_bad_limit_up and prior and prior.close > 0:
            self._detect_bad_limit_up_quality(current, prior, result)

        self._detect_risk(current, prior, history, result)

        result.evidence = {
            "rule_version": "enhanced_pattern.v2.6",
            "high_volume_unbroken": result.high_volume_unbroken,
            "double_volume_not_pierced": result.double_volume_not_pierced,
            "bad_limit_up_quality": result.bad_limit_up_quality,
        }
        return result

    # ── Sub-detectors ──────────────────────────────────────────────

    def _detect_volume(self, cur: VolumeBar, prior: VolumeBar | None,
                        hist: list[VolumeBar], r: EnhancedPatternResult):
        if prior and prior.volume > 0:
            r.volume_ratio_vs_prior = cur.volume / prior.volume
            ratio = r.volume_ratio_vs_prior
            up = cur.close >= cur.open
            if ratio > 2.0:
                r.volume_pattern_status = "放量上涨" if up else "放量下跌"
            elif ratio > 1.5:
                r.volume_pattern_status = "温和放量"
            elif ratio < 0.4:
                r.volume_pattern_status = "极度缩量"
            elif ratio < 0.6:
                r.volume_pattern_status = "缩量"
            else:
                r.volume_pattern_status = "平量"

        vols = [b.volume for b in hist[-20:] if b.volume > 0]
        if vols:
            r.volume_ratio_vs_20d_avg = cur.volume / (sum(vols) / len(vols))

    def _detect_pullback(self, cur: VolumeBar, prior: VolumeBar | None,
                          r: EnhancedPatternResult, support_level: float):
        if not prior:
            return
        price_down = cur.close < prior.close
        vol_ratio = r.volume_ratio_vs_prior if r.volume_ratio_vs_prior > 0 else 1.0
        vol_shrink = vol_ratio < 0.8
        near_support = support_level > 0 and abs(cur.close - support_level) / support_level < 0.03

        if price_down and vol_shrink and near_support:
            r.pullback_status = "缩量回踩"
        elif price_down and vol_shrink:
            r.pullback_status = "缩量下跌"
        elif price_down and not vol_shrink:
            r.pullback_status = "放量下跌"
        elif not price_down and vol_shrink:
            r.pullback_status = "缩量上涨"
        else:
            r.pullback_status = "正常"

        if near_support:
            r.pullback_to_support_distance = abs(cur.close - support_level) / support_level

    def _detect_breakout(self, cur: VolumeBar, hist: list[VolumeBar],
                          r: EnhancedPatternResult):
        if len(hist) < 5:
            return
        past = [b for b in hist[-20:] if str(b.trade_date) < str(cur.trade_date)]
        highs = [b.high for b in past] if past else []
        if highs:
            resistance = max(highs)
            if resistance > 0:
                r.breakout_level = resistance
                r.breakout_distance_pct = (cur.close - resistance) / resistance

        vol_surge = r.volume_ratio_vs_20d_avg > 1.5
        if r.breakout_distance_pct > 0.01 and vol_surge:
            r.breakout_status = "放量突破"
        elif r.breakout_distance_pct > 0.01:
            r.breakout_status = "缩量突破"
        elif r.breakout_distance_pct > -0.02:
            r.breakout_status = "接近突破"

    def _detect_high_vol_unbroken(self, cur: VolumeBar, hist: list[VolumeBar],
                                   r: EnhancedPatternResult):
        past = [b for b in hist if str(b.trade_date) < str(cur.trade_date)]
        if len(past) < 3:
            return
        max_vol = 0.0
        max_bar = None
        for b in past[-self.LOOKBACK_DAYS:]:
            if b.volume > max_vol:
                max_vol = b.volume
                max_bar = b
        if max_bar and max_vol > 0:
            r.high_volume_level = max_bar.low
            r.high_volume_bar_date = str(max_bar.trade_date)
            if max_bar.low > 0:
                r.high_volume_distance_pct = (cur.low - max_bar.low) / max_bar.low
            r.high_volume_unbroken = cur.low > max_bar.low
            if r.high_volume_unbroken:
                r.pattern_labels.append("高量不破")

    def _detect_double_vol_not_pierced(self, cur: VolumeBar, hist: list[VolumeBar],
                                        r: EnhancedPatternResult):
        past = [b for b in hist if str(b.trade_date) < str(cur.trade_date)]
        if len(past) < 2:
            return
        ranked = sorted(past[-self.LOOKBACK_DAYS:], key=lambda b: -b.volume)
        if len(ranked) >= 2:
            r.second_high_vol_level = ranked[1].low
            r.double_volume_not_pierced = (
                r.high_volume_unbroken and cur.low > ranked[1].low
            )
            if r.double_volume_not_pierced:
                r.pattern_labels.append("倍量不穿")

    def _detect_pattern_labels(self, cur: VolumeBar, prior: VolumeBar | None,
                                r: EnhancedPatternResult,
                                is_bad_limit_up: bool, prev_day_limit_up: bool):
        pct = cur.pct_chg if cur.pct_chg != 0 else (
            (cur.close - cur.pre_close) / cur.pre_close * 100 if cur.pre_close > 0 else 0)
        if pct >= 9.5:
            r.pattern_labels.append("涨停")
            r.breakout_status = "放量突破"
        elif pct >= 5:
            r.pattern_labels.append("大阳线")
        elif pct <= -7:
            r.pattern_labels.append("大阴线")
        elif pct <= -3:
            r.pattern_labels.append("中阴线")

        if cur.high > max(cur.open, cur.close):
            shadow = (cur.high - max(cur.open, cur.close)) / cur.close if cur.close > 0 else 0
            if shadow > 0.03 and pct < 3:
                r.pattern_labels.append("上影线")
        if cur.low < min(cur.open, cur.close):
            lower = (min(cur.open, cur.close) - cur.low) / cur.close if cur.close > 0 else 0
            if lower > 0.03 and pct > -3:
                r.pattern_labels.append("下影线")

        body = abs(cur.close - cur.open) / cur.close if cur.close > 0 else 0
        if body < 0.005:
            r.pattern_labels.append("十字星")

        if prior and prior.close > 0:
            gap = (cur.open - prior.close) / prior.close
            if gap > 0.02:
                r.pattern_labels.append("向上跳空")
            elif gap < -0.02:
                r.pattern_labels.append("向下跳空")

        if is_bad_limit_up:
            r.pattern_labels.append("烂板")
        if prev_day_limit_up:
            r.pattern_labels.append("前日涨停")

    def _detect_prior_swing_high(self, hist: list[VolumeBar],
                                  r: EnhancedPatternResult):
        if len(hist) < 10:
            return
        highs = [b.high for b in hist[-self.LOOKBACK_DAYS:] if b.high > 0]
        if highs:
            r.prior_swing_high = max(highs)
            last_close = hist[-1].close if hist else 0
            if r.prior_swing_high > 0 and last_close > 0:
                r.prior_swing_high_distance_pct = (
                    (last_close - r.prior_swing_high) / r.prior_swing_high
                )
            if r.prior_swing_high_distance_pct > -0.02:
                r.pattern_labels.append("接近前高")

    def _detect_bad_limit_up_quality(self, cur: VolumeBar, prior: VolumeBar,
                                      r: EnhancedPatternResult):
        pullback = (cur.close - prior.close) / prior.close if prior.close > 0 else 0
        r.bad_limit_up_pullback_pct = pullback
        if pullback > -0.01:
            r.bad_limit_up_quality = "good"
            r.pattern_labels.append("烂而不弱")
        elif pullback > -0.03:
            r.bad_limit_up_quality = "ok"
        else:
            r.bad_limit_up_quality = "poor"

    def _detect_risk(self, cur: VolumeBar, prior: VolumeBar | None,
                      hist: list[VolumeBar], r: EnhancedPatternResult):
        if prior and prior.close > 0:
            pct = (cur.close - prior.close) / prior.close * 100
            if pct <= -7:
                r.risk_pattern_status = "高波动"
                r.pattern_labels.append("破位风险")
        if len(hist) >= 4:
            recent = hist[-4:]
            if all(b.close < b.open for b in recent):
                r.risk_pattern_status = "连阴风险"

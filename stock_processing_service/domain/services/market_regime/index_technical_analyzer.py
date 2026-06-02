"""PR-11C: Index Technical Analyzer — wraps KlineTechnicalAnalyzer for market indices."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .kline_technical_analyzer import KlineTechnicalAnalyzer
from .models import IndexTechnicalReview


@dataclass
class IndexTechnicalAnalyzer:
    def analyze(self, *, index_code: str = "000001.SH", index_name: str = "",
                kline_rows: list[dict[str, Any]]) -> IndexTechnicalReview:
        analyzer = KlineTechnicalAnalyzer()
        result = analyzer.analyze(kline_rows)

        trend = result.get("trend", {})
        ma = result.get("ma", {})
        sr = result.get("support_resistance", {})
        vol = result.get("volume", {})
        macd = result.get("macd", {})
        latest_close = sr.get("latest_close")
        previous_close = sr.get("previous_close")
        pct_chg = None
        if latest_close is not None and previous_close not in (None, 0):
            try:
                pct_chg = round((float(latest_close) - float(previous_close)) / float(previous_close) * 100, 2)
            except Exception:
                pct_chg = None

        support_distance = sr.get("support_distance_pct")
        resistance_distance = sr.get("resistance_distance_pct")
        support_status = str(
            "support_broken" if sr.get("support_broken") else "near_support" if sr.get("near_support") else "support_available"
        )
        resistance_status = str(
            "resistance_broken" if sr.get("resistance_broken") else "near_resistance" if sr.get("near_resistance") else "resistance_available"
        )
        warning_level, hint = self._build_trade_hint(trend, sr, ma, macd)

        return IndexTechnicalReview(
            index_code=index_code, index_name=index_name or "上证指数",
            close=latest_close,
            pct_chg=pct_chg,
            trend_state=trend.get("trend_state", "unknown"),
            trend_score=trend.get("trend_score"),
            above_ma5=bool(ma.get("above_ma5")),
            above_ma10=bool(ma.get("above_ma10")),
            above_ma20=bool(ma.get("above_ma20")),
            above_ma60=bool(ma.get("above_ma60")),
            ma_structure=ma, support_resistance=sr,
            support_level=sr.get("support_level") or sr.get("nearest_support_level"),
            resistance_level=sr.get("resistance_level") or sr.get("nearest_resistance_level"),
            nearest_support_level=sr.get("nearest_support_level"),
            nearest_resistance_level=sr.get("nearest_resistance_level"),
            support_distance_pct=support_distance,
            resistance_distance_pct=resistance_distance,
            support_status=support_status,
            resistance_status=resistance_status,
            volume_pattern=vol.get("volume_pattern", "unknown"),
            macd_state=macd.get("macd_state", "unknown"),
            index_trade_hint=hint,
            warning_level=warning_level,
            risk_flags=trend.get("risk_flags", []),
            diagnostics={"bars_count": len(kline_rows)},
        )

    @staticmethod
    def _build_trade_hint(trend: dict[str, Any], sr: dict[str, Any], ma: dict[str, Any], macd: dict[str, Any]) -> tuple[str, str]:
        if sr.get("support_broken") and macd.get("macd_state") in {"below_zero_bearish", "below_zero_weak_rebound"}:
            return "danger", "支撑失守且MACD偏弱，禁止主动进攻"
        if sr.get("resistance_broken") or (sr.get("near_resistance") and not ma.get("above_ma20")):
            return "warning", "接近压力位或压力已触及，谨慎追高，等待确认突破"
        if sr.get("near_support") and not ma.get("above_ma20"):
            return "watch", "接近支撑位但趋势未确认，等待止跌信号"
        if bool(ma.get("above_ma5")) and bool(ma.get("above_ma10")) and bool(ma.get("above_ma20")) and not sr.get("near_resistance"):
            return "green", "指数环境相对友好，可跟踪主线修复与前排机会"
        if str(trend.get("trend_state") or "") == "downtrend_rebound":
            return "warning", "下降通道反抽，优先看核心确认，不追后排"
        return "normal", "指数环境中性，按主线与市场情绪择机应对"

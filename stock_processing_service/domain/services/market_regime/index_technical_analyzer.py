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

        return IndexTechnicalReview(
            index_code=index_code, index_name=index_name or "上证指数",
            trend_state=trend.get("trend_state", "unknown"),
            trend_score=trend.get("trend_score"),
            ma_structure=ma, support_resistance=sr,
            volume_pattern=vol.get("volume_pattern", "unknown"),
            macd_state=macd.get("macd_state", "unknown"),
            risk_flags=trend.get("risk_flags", []),
            diagnostics={"bars_count": len(kline_rows)},
        )

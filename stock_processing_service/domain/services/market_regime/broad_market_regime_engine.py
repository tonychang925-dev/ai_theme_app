"""PR-11D: BroadMarketRegimeEngine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .index_technical_analyzer import IndexTechnicalAnalyzer
from .models import BroadMarketRegimeReview, IndexTechnicalReview


def _float(val: Any) -> float | None:
    try: return float(val) if val not in (None, "") else None
    except: return None


@dataclass
class BroadMarketRegimeEngine:
    def build(self, *, index_kline: list[dict[str, Any]], market_snapshot: dict[str, Any] | None = None) -> BroadMarketRegimeReview:
        sn = market_snapshot or {}

        # ── index technical ──
        index_review = IndexTechnicalAnalyzer().analyze(index_code="000001.SH", index_name="上证指数", kline_rows=index_kline)
        index_score = index_review.trend_score or 50

        # ── breadth ──
        up_c = int(sn.get("up_count") or 0)
        dn_c = int(sn.get("down_count") or 0)
        lu_c = int(sn.get("limit_up_count") or 0)
        ld_c = int(sn.get("limit_down_count") or 0)
        total = max(up_c + dn_c, 1)
        breadth = min(100, max(10, (up_c / total * 100) * 0.5 + (lu_c - ld_c) * 0.5))
        if ld_c >= 30: breadth = min(breadth, 25)

        # ── volume ──
        vol_pattern = index_review.volume_pattern
        vol = index_review.to_dict().get("volume_pattern", "unknown")
        vol_score = 60 if "expanding" in vol else (45 if "shrinking" in vol else 50)

        # ── composite ──
        bm_score = round(breadth * 0.25 + index_score * 0.40 + vol_score * 0.20 + 50 * 0.15, 1)

        # ── classify ──
        regime = "unknown"
        flags: list[str] = []
        if index_review.trend_state in {"bullish_trend"} and breadth >= 55 and ld_c <= 5:
            regime = "bullish_supportive"
        elif index_review.trend_state == "downtrend_rebound" or (index_review.to_dict().get("above_ma20") is False and vol_score < 50):
            regime = "downtrend_rebound"
            flags.append("下降通道反抽")
        elif breadth < 35 or (ld_c >= 15 and lu_c < 20):
            regime = "bearish_adverse"
        elif index_review.trend_state == "bearish_trend":
            regime = "bearish_adverse"
        elif ld_c >= 30 and breadth < 25:
            regime = "crash_risk"
        else:
            regime = "neutral_choppy"

        flags.extend(index_review.risk_flags or [])

        return BroadMarketRegimeReview(
            broad_market_regime=regime, broad_market_score=bm_score,
            index_technical=index_review.to_dict(), breadth_score=breadth,
            volume_score=vol_score, risk_flags=flags,
            evidence={"up_count": up_c, "down_count": dn_c, "limit_up": lu_c, "limit_down": ld_c},
            diagnostics={"index_trend": index_review.trend_state},
        )

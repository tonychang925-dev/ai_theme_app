"""PR-11E: ShortTermSentimentEngine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ShortTermSentimentReview

def _int(val: Any) -> int: return int(val) if val not in (None, "") else 0


@dataclass
class ShortTermSentimentEngine:
    def build(self, *, market_snapshot: dict[str, Any] | None = None) -> ShortTermSentimentReview:
        sn = market_snapshot or {}
        lu = _int(sn.get("limit_up_count"))
        ld = _int(sn.get("limit_down_count"))
        up = _int(sn.get("up_count"))
        dn = _int(sn.get("down_count"))
        relay = str(sn.get("relay_sentiment_status") or "unknown")
        fade = str(sn.get("intraday_fade_status") or "unknown")

        st = "unknown"
        score = 50
        flags: list[str] = []

        if ld >= 30:
            st = "dead"
            score = 15
            flags.append("跌停数量高")
        elif ld >= 15 or (fade in {"fade", "weak", "退潮"}):
            st = "retreat"
            score = 30
            flags.append("短线情绪退潮")
        elif relay in {"divergence", "分歧"} or fade in {"fade", "weak"}:
            st = "divergence"
            score = 45
        elif lu >= 60 and ld <= 5 and relay not in {"retreat", "dead"}:
            st = "attack"
            score = 78
        elif lu >= 30:
            st = "normal"
            score = 58
        else:
            st = "normal"

        return ShortTermSentimentReview(
            short_term_sentiment=st, sentiment_score=float(score),
            limit_up_count=lu, limit_down_count=ld, up_count=up, down_count=dn,
            relay_status=relay, intraday_fade_status=fade,
            risk_flags=flags,
            evidence={"limit_up": lu, "limit_down": ld, "relay": relay, "fade": fade},
        )

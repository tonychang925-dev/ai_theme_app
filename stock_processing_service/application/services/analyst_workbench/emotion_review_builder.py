"""Phase 4.5.4 T03 — EmotionReviewBuilder.

Converts raw emotion JSON into structured emotion_review dict.
Deterministic rules only. No LLM.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

NODE_LABELS: dict[str, str] = {
    "ICE_POINT": "情绪冰点",
    "REBOUND": "情绪修复",
    "FERMENTATION": "情绪发酵",
    "ACCELERATION": "情绪加速",
    "CLIMAX": "情绪高潮",
    "DIVERGENCE": "情绪退潮",
    "FADE": "情绪衰退",
    "CHAOS": "情绪混沌",
}


class EmotionReviewBuilder:
    """Build emotion_review from emotion JSON."""

    def build(self, emo: dict) -> dict[str, Any]:
        if not emo or not emo.get("emotion_node"):
            return self._empty()

        node = emo.get("emotion_node", "CHAOS")
        score = emo.get("emotion_score", 0) or 0
        confidence = emo.get("confidence", 0.5) or 0.5

        review: dict[str, Any] = {
            "emotion_node": node,
            "emotion_label": NODE_LABELS.get(node, node),
            "emotion_score": score,
            "risk_level": self._risk_level(score),
            "confidence": confidence,
            "summary": self._build_summary(emo, node, score),
            "strategy_bias": emo.get("strategy_bias", ""),
            "key_evidence": emo.get("key_evidence") or [],
            # 5 dimension scores
            "breadth_score": emo.get("breadth_score", 0) or 0,
            "breadth_label": emo.get("breadth_label", ""),
            "momentum_score": emo.get("momentum_score", 0) or 0,
            "momentum_label": emo.get("momentum_label", ""),
            "relay_score": emo.get("relay_score", 0) or 0,
            "relay_label": emo.get("relay_label", ""),
            "capital_score": emo.get("capital_score", 0) or 0,
            "capital_label": emo.get("capital_label", ""),
            "style_score": emo.get("style_score", 0) or 0,
            "style_label": emo.get("style_label", ""),
            # analyst override placeholder
            "analyst_adjustment": None,
            # traceability
            "source_quality": 1.0,
            "missing_fields": [],
        }

        # Use emotion_desc as summary if available, else construct one
        if not review["summary"]:
            review["summary"] = self._fallback_summary(node, score)

        return review

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "emotion_node": "",
            "emotion_label": "",
            "emotion_score": 0,
            "risk_level": "UNKNOWN",
            "confidence": 0,
            "summary": "情绪数据不可用。",
            "strategy_bias": "",
            "key_evidence": [],
            "breadth_score": 0, "breadth_label": "",
            "momentum_score": 0, "momentum_label": "",
            "relay_score": 0, "relay_label": "",
            "capital_score": 0, "capital_label": "",
            "style_score": 0, "style_label": "",
            "analyst_adjustment": None,
            "source_quality": 0,
            "missing_fields": ["emotion_json"],
        }

    @staticmethod
    def _risk_level(score: float) -> str:
        if score > 40:
            return "LOW"
        elif score >= 10:
            return "MEDIUM"
        elif score >= -20:
            return "HIGH"
        else:
            return "EXTREME"

    @staticmethod
    def _build_summary(emo: dict, node: str, score: float) -> str:
        desc = emo.get("emotion_desc", "")
        if desc:
            return desc
        return EmotionReviewBuilder._fallback_summary(node, score)

    @staticmethod
    def _fallback_summary(node: str, score: float) -> str:
        label = NODE_LABELS.get(node, node)
        direction = "积极" if score > 0 else "偏谨慎" if score < -10 else "中性"
        return f"市场处于{label}状态，情绪{score:.0f}，整体{direction}。"

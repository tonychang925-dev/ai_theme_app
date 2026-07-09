"""Phase 4.2.2a — Strategy Intent Matcher v1.

Replaces keyword overlap with deterministic strategy intent matching.
8 intent labels cover A-share short-term trading strategy semantics.

Design:
  - Alias map + token matching only (no LLM)
  - Score = 0.7 * analyst_intent_recall + 0.3 * AI_intent_precision
  - Analyst is the reference — AI missing analyst intents hurts more
    than AI having extra intents the analyst didn't mention.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ═══ 8 Strategy Intent Labels ═══

WAIT_CONFIRMATION = "WAIT_CONFIRMATION"
LIGHT_POSITION = "LIGHT_POSITION"
NO_CHASING = "NO_CHASING"
CORE_ONLY = "CORE_ONLY"
REBOUND_ARBITRAGE = "REBOUND_ARBITRAGE"
RISK_OFF = "RISK_OFF"
CAN_PARTICIPATE = "CAN_PARTICIPATE"
AVOID_HIGH_POSITION = "AVOID_HIGH_POSITION"

ALL_INTENTS = (
    WAIT_CONFIRMATION, LIGHT_POSITION, NO_CHASING, CORE_ONLY,
    REBOUND_ARBITRAGE, RISK_OFF, CAN_PARTICIPATE, AVOID_HIGH_POSITION,
)


# ═══ Alias Map ═══

INTENT_ALIASES: dict[str, tuple[str, ...]] = {
    WAIT_CONFIRMATION: (
        "等待确认", "等确认", "观察", "继续观察", "看确认", "右侧确认",
        "确认后再参与", "等待指数确认", "等待量能确认", "等右侧信号",
        "看指数确认", "量能确认",
    ),
    LIGHT_POSITION: (
        "轻仓", "小仓位", "低仓位", "试错仓", "轻仓试错", "控制仓位",
        "控制总仓", "仓位控制", "仓位管理",
    ),
    NO_CHASING: (
        "不追高", "禁止追高", "不接高潮", "不扩大仓位", "避免追高",
        "不重仓追高", "不追涨", "不抢高", "不接盘", "不追",
    ),
    CORE_ONLY: (
        "只做核心", "核心方向", "聚焦核心", "主线核心", "辨识度",
        "核心标的", "只看核心", "做主线", "只看辨识度", "核心票",
        "聚焦主线",
    ),
    REBOUND_ARBITRAGE: (
        "反弹套利", "修复套利", "快进快出", "短线套利", "反抽套利",
        "日内套利", "修复参与", "反弹参与", "套利", "短线参与",
    ),
    RISK_OFF: (
        "空仓", "防守", "降低仓位", "降仓", "回避风险", "谨慎",
        "少动", "观望为主", "防守为主", "回避", "轻仓观望",
    ),
    CAN_PARTICIPATE: (
        "可参与", "可以参与", "低吸", "试错", "参与修复",
        "小仓参与", "择机参与", "低吸参与", "可以试错", "可试错",
    ),
    AVOID_HIGH_POSITION: (
        "回避高位", "不碰高标", "避开高标", "不做高位", "避免接力",
        "高位谨慎", "接力谨慎", "高位不碰", "不接高位",
    ),
}


# ═══ Match Result ═══

@dataclass(frozen=True)
class StrategyIntentMatch:
    analyst_intents: tuple[str, ...]
    ai_intents: tuple[str, ...]
    overlap_intents: tuple[str, ...]
    missing_intents: tuple[str, ...]     # in analyst but not in AI
    extra_intents: tuple[str, ...]       # in AI but not in analyst
    score: float
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "analyst_intents": list(self.analyst_intents),
            "ai_intents": list(self.ai_intents),
            "overlap_intents": list(self.overlap_intents),
            "missing_intents": list(self.missing_intents),
            "extra_intents": list(self.extra_intents),
            "score": round(self.score, 3),
            "reason": self.reason,
        }


# ═══ Matcher ═══

class StrategyIntentMatcher:
    """Deterministic strategy intent extraction and comparison."""

    def extract_intents(self, text: str) -> tuple[str, ...]:
        """Extract strategy intent labels from free-text strategy description."""
        if not text or not text.strip():
            return ()

        found: list[str] = []
        for intent in ALL_INTENTS:
            aliases = INTENT_ALIASES[intent]
            for alias in aliases:
                if alias in text:
                    found.append(intent)
                    break  # one match per intent is enough

        return tuple(found)

    def compare(self, analyst_text: str, ai_text: str) -> StrategyIntentMatch:
        """Compare analyst and AI strategy intents.

        Recall-weighted: analyst is the reference. AI missing analyst
        intents is penalized more than AI having extra intents.
        """
        a_intents = set(self.extract_intents(analyst_text))
        ai_intents = set(self.extract_intents(ai_text))

        # Edge cases
        if not a_intents and not ai_intents:
            return StrategyIntentMatch(
                analyst_intents=(), ai_intents=(),
                overlap_intents=(), missing_intents=(), extra_intents=(),
                score=0.70,
                reason="Neither analyst nor AI has detectable strategy intents",
            )
        if not ai_intents:
            missing = tuple(a_intents)
            return StrategyIntentMatch(
                analyst_intents=tuple(a_intents), ai_intents=(),
                overlap_intents=(), missing_intents=missing, extra_intents=(),
                score=0.0,
                reason=f"AI strategy text empty or missing (analyst intents: {missing})",
            )
        if not a_intents:
            extra = tuple(ai_intents)
            return StrategyIntentMatch(
                analyst_intents=(), ai_intents=extra,
                overlap_intents=(), missing_intents=(), extra_intents=extra,
                score=0.50,
                reason=f"Analyst strategy has no detectable intents, AI has: {extra}",
            )

        overlap = a_intents & ai_intents
        missing_intents = a_intents - ai_intents
        extra_intents = ai_intents - a_intents

        # Recall-weighted scoring
        recall = len(overlap) / max(len(a_intents), 1)
        precision = len(overlap) / max(len(ai_intents), 1)
        score = 0.7 * recall + 0.3 * precision

        reason_parts = [f"overlap={len(overlap)}/{len(a_intents)}"]
        if missing_intents:
            reason_parts.append(f"missing={sorted(missing_intents)}")
        if extra_intents:
            reason_parts.append(f"extra={sorted(extra_intents)}")

        return StrategyIntentMatch(
            analyst_intents=tuple(sorted(a_intents)),
            ai_intents=tuple(sorted(ai_intents)),
            overlap_intents=tuple(sorted(overlap)),
            missing_intents=tuple(sorted(missing_intents)),
            extra_intents=tuple(sorted(extra_intents)),
            score=round(score, 4),
            reason="; ".join(reason_parts),
        )

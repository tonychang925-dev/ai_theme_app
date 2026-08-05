"""Tool 5: explain_decision — Julia's core capability: explain WHY, not just WHAT."""
from __future__ import annotations

from core.contracts.decision_envelope import (
    DecisionExplanation, CausalLink,
)


def explain_decision(decision_id: str) -> DecisionExplanation | None:
    """Return structured explanation for a specific DecisionEnvelope.

    This is Julia's most important tool — Tony asks "为什么", and Julia
    uses this to build a natural-language explanation grounded in evidence.
    """
    # TODO Phase 2: Wire to DecisionRepository — look up decision by ID,
    #   resolve causal chain, count supporting/opposing evidence, list risks.

    if decision_id == "dec_20260806_001":
        return DecisionExplanation(
            decision_id=decision_id,
            summary="AI Agent板块出现L4级别扩散信号",
            causal_chain=(
                CausalLink(
                    cause="AI Agent技术突破 + 政策催化",
                    effect="产业预期升温，关注度提升",
                    market_response="相关概念股上涨，龙头涨停",
                    confidence=0.82,
                ),
            ),
            supporting_evidence=4,
            opposing_evidence=1,
            confidence=0.82,
            risk_factors=(
                "外围市场波动",
                "成交量未能有效放大",
                "AI板块短期过热风险",
            ),
            alternatives=("短期情绪炒作，非趋势性行情",),
        )

    return None

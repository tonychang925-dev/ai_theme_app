from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class IdentityDecision:
    identity_status: str
    final_score: Decimal
    reason: str


class IdentityDecider:
    def decide(self, composite_score: Decimal, llm_verdict: str, one_day_tour_flag: bool) -> IdentityDecision:
        if one_day_tour_flag and llm_verdict == "confirmed":
            return IdentityDecision(
                identity_status="review_pending",
                final_score=composite_score,
                reason="confirmed_but_tour_risk",
            )
        if llm_verdict == "confirmed":
            return IdentityDecision(identity_status="confirmed", final_score=composite_score, reason="llm_confirmed")
        if llm_verdict == "review_pending":
            return IdentityDecision(
                identity_status="review_pending",
                final_score=composite_score,
                reason="llm_review_pending",
            )
        return IdentityDecision(identity_status="observed", final_score=composite_score, reason="llm_observed")

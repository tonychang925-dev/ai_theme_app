from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class IdentityLLMReviewVerdict:
    verdict: str
    confidence: Decimal
    reason: str


class IdentityLLMReviewService:
    def review(self, composite_score: Decimal, one_day_tour_flag: bool) -> IdentityLLMReviewVerdict:
        # Placeholder deterministic reviewer. Real LLM call should be injected later.
        if one_day_tour_flag:
            return IdentityLLMReviewVerdict(
                verdict="review_pending",
                confidence=Decimal("0.55"),
                reason="one_day_tour_risk",
            )
        if composite_score >= Decimal("75"):
            return IdentityLLMReviewVerdict(
                verdict="confirmed",
                confidence=Decimal("0.80"),
                reason="high_composite_score",
            )
        if composite_score >= Decimal("60"):
            return IdentityLLMReviewVerdict(
                verdict="review_pending",
                confidence=Decimal("0.60"),
                reason="borderline_score",
            )
        return IdentityLLMReviewVerdict(
            verdict="observed",
            confidence=Decimal("0.70"),
            reason="low_composite_score",
        )

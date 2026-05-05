# ============================================================
# DO NOT USE IN PRODUCTION
# Deprecated by IdentityRuleEngine + IdentityDecider path.
# The formal Layer A entry is now BuildIdentityJob →
#   IdentityRuleEngine → IdentityLLMReviewService → IdentityDecider.
# This module is retained only for backward-compatible test
# reference. Do NOT import or invoke from any application/jobs/*.
# ============================================================
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class IdentityScore:
    subject_key: str
    subject_name: str
    logic_score: Decimal
    market_score: Decimal
    composite_score: Decimal


class IdentityScoringService:
    """DEPRECATED: Use IdentityRuleEngine + IdentityDecider instead."""

    def score(self, subject_key: str, subject_name: str, context_tags: list[str], stock_count: int) -> IdentityScore:
        logic = min(Decimal("100"), Decimal(str(len(context_tags) * 12 + stock_count * 2)))
        market = min(Decimal("100"), Decimal(str(stock_count * 3 + (20 if "policy" in context_tags else 0))))
        composite = logic * Decimal("0.6") + market * Decimal("0.4")
        return IdentityScore(
            subject_key=subject_key,
            subject_name=subject_name,
            logic_score=logic,
            market_score=market,
            composite_score=composite,
        )

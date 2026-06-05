from __future__ import annotations

from decimal import Decimal

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures, RuleResult, ScoreResult


class OneToTwoScorer:
    """1进2 的保守排序评分。"""

    def score(self, f: OneToTwoFeatures, rule: RuleResult) -> ScoreResult:
        if rule.decision == "reject":
            return ScoreResult(final_score=None, watch_level=None, score_detail={})

        first_board = self._first_board_quality(f)
        breadth = self._board_breadth(f)
        lifecycle = self._lifecycle_score(f)
        risk = self._risk_control(f)

        final = (
            first_board * Decimal("0.40")
            + breadth * Decimal("0.25")
            + lifecycle * Decimal("0.20")
            + risk * Decimal("0.15")
        )

        level = "A" if final >= Decimal("80") else "B" if final >= Decimal("70") else "C"
        return ScoreResult(
            final_score=final.quantize(Decimal("0.01")),
            watch_level=level,
            score_detail={
                "first_board_quality": str(first_board),
                "board_breadth": str(breadth),
                "lifecycle": str(lifecycle),
                "risk_control": str(risk),
            },
        )

    def _first_board_quality(self, f: OneToTwoFeatures) -> Decimal:
        score = Decimal("50")
        if f.turnover_rate and f.turnover_rate >= Decimal("0.15"):
            score += Decimal("20")
        elif f.turnover_rate and f.turnover_rate >= Decimal("0.08"):
            score += Decimal("10")
        if f.amount and f.amount >= Decimal("1000000000"):
            score += Decimal("15")
        if f.open_board_count is not None and f.open_board_count <= 2:
            score += Decimal("10")
        if f.close_seal_amount:
            score += Decimal("5")
        return min(score, Decimal("100"))

    def _board_breadth(self, f: OneToTwoFeatures) -> Decimal:
        count = f.same_subject_limit_count or 0
        strong = f.same_subject_strong_count or 0
        return min(Decimal("100"), Decimal(count * 25 + strong * 8))

    def _lifecycle_score(self, f: OneToTwoFeatures) -> Decimal:
        mapping = {
            "start": Decimal("95"),
            "fermentation": Decimal("90"),
            "acceleration": Decimal("75"),
            "repair": Decimal("65"),
            "divergence": Decimal("55"),
            "seed": Decimal("45"),
            "climax": Decimal("35"),
            "fade_watch": Decimal("25"),
        }
        return mapping.get(f.lifecycle_state, Decimal("50"))

    def _risk_control(self, f: OneToTwoFeatures) -> Decimal:
        score = Decimal("80")
        if f.position_120 is not None and f.position_120 > Decimal("0.50"):
            score -= Decimal("20")
        if f.near_pressure is None:
            score -= Decimal("10")
        return max(Decimal("0"), min(score, Decimal("100")))

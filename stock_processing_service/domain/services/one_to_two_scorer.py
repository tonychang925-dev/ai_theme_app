from __future__ import annotations

from decimal import Decimal

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures, RuleResult, ScoreResult
from stock_processing_service.domain.services.one_to_two_technical_gate import (
    TECHNICAL_FOCUS_SCORE_THRESHOLD,
    TECHNICAL_GOLDEN_SCORE_THRESHOLD,
)


class OneToTwoScorer:
    """1进2 五维保守排序评分 (v3.1).

    Weights:
      first_board_quality      25%
      theme_authenticity       20%
      board_breadth            20%
      technical_structure      20%
      risk_control             15%
    """

    def score(self, f: OneToTwoFeatures, rule: RuleResult) -> ScoreResult:
        if rule.decision == "reject":
            return ScoreResult(final_score=None, watch_level=None, score_detail={})

        first_board = self._first_board_quality(f)
        authenticity = self._theme_authenticity_score(f)
        breadth = self._board_breadth(f)
        technical = self._technical_structure_score(f)
        risk = self._risk_control(f)

        final = (
            first_board * Decimal("0.25")
            + authenticity * Decimal("0.20")
            + breadth * Decimal("0.20")
            + technical * Decimal("0.20")
            + risk * Decimal("0.15")
        )

        level = "A" if final >= Decimal("80") else "B" if final >= Decimal("70") else "C"
        kpq = f.kline_pattern_quality or {}
        return ScoreResult(
            final_score=final.quantize(Decimal("0.01")),
            watch_level=level,
            score_detail={
                "first_board_quality": str(first_board),
                "theme_authenticity": str(authenticity),
                "board_breadth": str(breadth),
                "technical_structure": str(technical),
                "risk_control": str(risk),
                "final_score": str(final.quantize(Decimal("0.01"))),
                "has_golden_spider": bool(kpq.get("has_golden_spider")) if kpq else False,
                "kline_pattern_score": str(kpq.get("score")) if kpq else None,
                "technical_reason": str(kpq.get("technical_reason") or "") if kpq else "",
                "subject_authenticity_score": str((f.subject_authenticity or {}).get("score")) if f.subject_authenticity else None,
                "subject_authenticity_level": (f.subject_authenticity or {}).get("level") if f.subject_authenticity else None,
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

    def _theme_authenticity_score(self, f: OneToTwoFeatures) -> Decimal:
        data = f.subject_authenticity or {}
        score = data.get("score")
        if score is not None:
            try:
                return min(Decimal("100"), max(Decimal("0"), Decimal(str(score))))
            except Exception:
                pass
        level = str(data.get("level") or "").strip()
        mapping = {
            "strong": Decimal("90"),
            "medium": Decimal("70"),
            "weak": Decimal("45"),
        }
        return mapping.get(level, Decimal("50"))

    def _board_breadth(self, f: OneToTwoFeatures) -> Decimal:
        count = f.same_subject_limit_count or 0
        strong = f.same_subject_strong_count or 0
        return min(Decimal("100"), Decimal(count * 25 + strong * 8))

    def _technical_structure_score(self, f: OneToTwoFeatures) -> Decimal:
        """Score from K-line technical form: golden-spider / trend / pressure / support."""
        k = f.kline_pattern_quality or {}
        if not k or not k.get("kline_data_ready"):
            return Decimal("25")
        if f.is_downtrend:
            return Decimal("0")
        if f.near_pressure:
            return Decimal("30")
        if k.get("support_broken"):
            return Decimal("20")
        raw = k.get("score")
        if raw is not None:
            try:
                return Decimal(str(raw))
            except Exception:
                pass
        if k.get("has_golden_spider"):
            return Decimal("90")
        if str(k.get("level") or "") == "near_golden":
            return Decimal("70")
        return Decimal("45")

    def _risk_control(self, f: OneToTwoFeatures) -> Decimal:
        score = Decimal("80")
        if f.position_120 is not None and f.position_120 > Decimal("0.65"):
            score -= Decimal("20")
        if f.is_downtrend:
            score -= Decimal("20")
        if f.near_pressure:
            score -= Decimal("15")
        return max(Decimal("0"), min(score, Decimal("100")))

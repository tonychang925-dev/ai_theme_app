from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidence


@dataclass(frozen=True)
class CycleJudgement:
    stock_id: str
    subject_key: str
    subject_name: str
    mainline_strength_score: Decimal
    fade_watch_score: Decimal
    fade_confirmed_score: Decimal
    divergence_score: Decimal
    repair_score: Decimal
    final_cycle_state: str
    final_mainline_alive: bool


class CycleJudgementService:
    def judge_many(self, evidences: list[CycleEvidence]) -> list[CycleJudgement]:
        return [self.judge_one(e) for e in evidences]

    def judge_one(self, evidence: CycleEvidence) -> CycleJudgement:
        mainline_strength = (
            evidence.momentum_score * Decimal("0.40")
            + evidence.support_score * Decimal("0.30")
            + evidence.continuity_score * Decimal("0.20")
            + evidence.context_score * Decimal("0.10")
        )
        fade_watch = max(Decimal("0"), Decimal("70") - evidence.momentum_score)
        fade_confirmed = max(Decimal("0"), fade_watch - evidence.continuity_score * Decimal("0.2"))
        divergence = max(Decimal("0"), evidence.support_score - evidence.momentum_score)
        repair = max(Decimal("0"), evidence.continuity_score - fade_watch)

        if mainline_strength >= Decimal("70"):
            state = "mainline_active"
            alive = True
        elif repair >= Decimal("50"):
            state = "repair"
            alive = True
        elif fade_confirmed >= Decimal("55"):
            state = "fade_confirmed"
            alive = False
        elif fade_watch >= Decimal("45"):
            state = "fade_watch"
            alive = False
        else:
            state = "observed"
            alive = False

        return CycleJudgement(
            stock_id=evidence.stock_id,
            subject_key=evidence.subject_key,
            subject_name=evidence.subject_name,
            mainline_strength_score=mainline_strength,
            fade_watch_score=fade_watch,
            fade_confirmed_score=fade_confirmed,
            divergence_score=divergence,
            repair_score=repair,
            final_cycle_state=state,
            final_mainline_alive=alive,
        )

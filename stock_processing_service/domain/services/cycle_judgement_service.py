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
    acceleration_score: Decimal
    fermentation_score: Decimal
    fade_confirmed_evidence_count: int
    final_cycle_state: str
    final_mainline_alive: bool
    decision_path: str = ""
    evidence_count: int = 0
    fade_reason_codes: list[str] | None = None
    mainline_alive_rule: bool = False
    support_break: bool = False
    score_flags: dict[str, bool] | None = None


class CycleJudgementService:
    def judge_many(self, evidences: list[CycleEvidence]) -> list[CycleJudgement]:
        return [self.judge_one(e) for e in evidences]

    def judge_one(self, e: CycleEvidence) -> CycleJudgement:
        # Legacy-like score decomposition.
        mainline_strength = (
            e.event_score * Decimal("0.22")
            + e.continuity_score * Decimal("0.12")
            + e.leader_score * Decimal("0.26")
            + e.relay_score * Decimal("0.16")
            + e.board_score * Decimal("0.14")
            + e.support_score * Decimal("0.10")
        )

        red_ratio = max(Decimal("0"), min(Decimal("1"), (e.leader_score + e.relay_score) / Decimal("200")))
        fade_watch = (
            max(Decimal("0"), Decimal("100") - e.leader_score) * Decimal("0.35")
            + (Decimal("1") - red_ratio) * Decimal("45")
            + max(Decimal("0"), Decimal("100") - e.support_score) * Decimal("0.2")
        )
        fade_confirmed = (
            max(Decimal("0"), Decimal("100") - e.leader_score) * Decimal("0.45")
            + (Decimal("1") - red_ratio) * Decimal("28")
            + max(Decimal("0"), Decimal("40") - e.relay_score) * Decimal("0.45")
        )
        divergence = (
            e.leader_score * Decimal("0.30")
            + e.relay_score * Decimal("0.25")
            + e.support_score * Decimal("0.20")
            + (Decimal("1") - red_ratio) * Decimal("15")
            + e.board_score * Decimal("0.10")
        )
        repair = (
            e.continuity_score * Decimal("0.22")
            + e.relay_score * Decimal("0.24")
            + e.support_score * Decimal("0.20")
            + red_ratio * Decimal("18")
            + e.leader_score * Decimal("0.16")
        )
        acceleration = e.leader_score * Decimal("0.4") + e.board_score * Decimal("0.35") + e.event_score * Decimal("0.25")
        fermentation = e.event_score * Decimal("0.35") + e.board_score * Decimal("0.35") + e.continuity_score * Decimal("0.30")

        # Multi-evidence constraint for fade_confirmed.
        evidence_count = 0
        if e.leader_score < Decimal("40"):
            evidence_count += 1
        if e.relay_score < Decimal("40"):
            evidence_count += 1
        if e.support_score < Decimal("45"):
            evidence_count += 1
        if e.continuity_score < Decimal("50"):
            evidence_count += 1

        # Fixed priority:
        # 1 fade_confirmed (evidence>=3), 2 repair (from divergence/fade_watch),
        # 3 divergence, 4 fade_watch, 5 acceleration, 6 fermentation, 7 start
        if fade_confirmed >= Decimal("60") and evidence_count >= 3:
            state = "fade_confirmed"
        elif repair >= Decimal("65") and e.previous_state in {"divergence", "fade_watch"}:
            state = "repair"
        elif divergence >= Decimal("60"):
            state = "divergence"
        elif fade_watch >= Decimal("50"):
            state = "fade_watch"
        elif acceleration >= Decimal("75"):
            state = "acceleration"
        elif fermentation >= Decimal("60"):
            state = "fermentation"
        else:
            state = "start"

        mainline_alive = (
            mainline_strength >= Decimal("60")
            and e.leader_score >= Decimal("40")
            and (e.event_score > Decimal("0") or e.continuity_score >= Decimal("40"))
            and state != "fade_confirmed"
        )

        return CycleJudgement(
            stock_id=e.stock_id,
            subject_key=e.subject_key,
            subject_name=e.subject_name,
            mainline_strength_score=mainline_strength,
            fade_watch_score=fade_watch,
            fade_confirmed_score=fade_confirmed,
            divergence_score=divergence,
            repair_score=repair,
            acceleration_score=acceleration,
            fermentation_score=fermentation,
            fade_confirmed_evidence_count=evidence_count,
            final_cycle_state=state,
            final_mainline_alive=bool(mainline_alive),
        )

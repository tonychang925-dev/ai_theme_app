from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_processing_service.domain.services.subject_cycle_evidence_builder import SubjectCycleEvidence


@dataclass(frozen=True)
class SubjectCycleJudgement:
    subject_key: str
    subject_name: str
    mainline_strength_score: Decimal
    fade_watch_score: Decimal
    fade_confirmed_score: Decimal
    divergence_score: Decimal
    repair_score: Decimal
    final_cycle_state: str
    final_mainline_alive: bool
    fade_confirmed_evidence_count: int
    decision_path: str
    evidence_count: int
    fade_reason_codes: list[str]


class SubjectCycleJudgementService:
    THRESH_MAINLINE_ALIVE = Decimal("60")
    THRESH_MAINLINE_LEADER = Decimal("40")
    THRESH_MAINLINE_EVENT_CONTINUITY = Decimal("40")
    THRESH_FADE_WATCH = Decimal("50")
    THRESH_FADE_CONFIRMED = Decimal("60")
    THRESH_DIVERGENCE = Decimal("60")
    THRESH_REPAIR = Decimal("65")
    THRESH_ACCELERATION = Decimal("75")
    THRESH_FERMENTATION = Decimal("60")

    def judge_many(self, evidences: list[SubjectCycleEvidence]) -> list[SubjectCycleJudgement]:
        return [self.judge_one(e) for e in evidences]

    def judge_one(self, e: SubjectCycleEvidence) -> SubjectCycleJudgement:
        mainline_strength = (
            e.event_strength_score * Decimal("0.22")
            + e.event_continuity_score * Decimal("0.12")
            + e.leader_alive_score * Decimal("0.26")
            + e.relay_strength_score * Decimal("0.16")
            + e.front_row_strength_score * Decimal("0.14")
            + e.theme_support_score * Decimal("0.10")
        )
        fade_watch = (
            (Decimal("100") if e.leader_breakdown_flag else Decimal("0")) * Decimal("0.35")
            + (Decimal("1") - e.red_ratio) * Decimal("45")
            + e.big_drop_ratio * Decimal("35")
            + min(Decimal(str(e.limit_down_count)) * Decimal("10"), Decimal("20"))
        )
        fade_confirmed = (
            (Decimal("100") if e.leader_breakdown_flag else Decimal("0")) * Decimal("0.45")
            + min(Decimal(str(e.limit_down_count)) * Decimal("14"), Decimal("35"))
            + (Decimal("1") - e.red_ratio) * Decimal("28")
            + max(Decimal("0"), Decimal("40") - e.relay_strength_score) * Decimal("0.45")
        )
        divergence = (
            e.leader_alive_score * Decimal("0.30")
            + e.relay_strength_score * Decimal("0.25")
            + e.front_row_survival_ratio * Decimal("20")
            + e.theme_support_score * Decimal("0.20")
            + (Decimal("1") - e.red_ratio) * Decimal("15")
        )
        repair = (
            e.event_continuity_score * Decimal("0.22")
            + e.relay_strength_score * Decimal("0.24")
            + e.theme_support_score * Decimal("0.20")
            + e.red_ratio * Decimal("18")
            + e.leader_alive_score * Decimal("0.16")
        )

        # ── 退潮证据 6 项（对齐生产 _count_fade_confirmed_evidence()）──
        evidence_count = 0
        fade_reason_codes: list[str] = []
        if e.leader_breakdown_flag:
            evidence_count += 1
            fade_reason_codes.append("leader_breakdown")
        if e.limit_down_count >= 1:
            evidence_count += 1
            fade_reason_codes.append("limit_down_count_ge_1")
        if e.red_ratio <= Decimal("0.45"):
            evidence_count += 1
            fade_reason_codes.append("red_ratio_le_0_45")
        if e.big_drop_ratio >= Decimal("0.30"):
            evidence_count += 1
            fade_reason_codes.append("big_drop_ratio_ge_0_30")
        if e.relay_strength_score <= Decimal("35"):
            evidence_count += 1
            fade_reason_codes.append("relay_strength_le_35")
        if e.theme_support_score <= Decimal("35"):
            evidence_count += 1
            fade_reason_codes.append("theme_support_le_35")

        fade_confirmed_flag = fade_confirmed >= self.THRESH_FADE_CONFIRMED and evidence_count >= 3
        fade_watch_flag = (not fade_confirmed_flag) and fade_watch >= self.THRESH_FADE_WATCH
        repair_transition_allowed = e.previous_cycle_state in {"divergence", "fade_watch"}

        if fade_confirmed_flag:
            state = "fade_confirmed"
            decision_path = "fade_confirmed(score>=60,evidence>=3)"
        elif repair >= self.THRESH_REPAIR and repair_transition_allowed:
            state = "repair"
            decision_path = "repair(score>=65,previous in divergence/fade_watch)"
        elif divergence >= self.THRESH_DIVERGENCE:
            state = "divergence"
            decision_path = "divergence(score>=60)"
        elif fade_watch_flag:
            state = "fade_watch"
            decision_path = "fade_watch(score>=50 and not fade_confirmed)"
        elif mainline_strength >= self.THRESH_ACCELERATION:
            state = "acceleration"
            decision_path = "acceleration(mainline_strength>=75)"
        elif mainline_strength >= self.THRESH_FERMENTATION:
            state = "fermentation"
            decision_path = "fermentation(mainline_strength>=60)"
        else:
            state = "start"
            decision_path = "start(default)"

        mainline_alive = (
            mainline_strength >= self.THRESH_MAINLINE_ALIVE
            and e.leader_alive_score >= self.THRESH_MAINLINE_LEADER
            and (
                e.strong_event_count_7d > 0
                or e.event_continuity_score >= self.THRESH_MAINLINE_EVENT_CONTINUITY
            )
            and state != "fade_confirmed"
        )

        return SubjectCycleJudgement(
            subject_key=e.subject_key,
            subject_name=e.subject_name,
            mainline_strength_score=mainline_strength,
            fade_watch_score=fade_watch,
            fade_confirmed_score=fade_confirmed,
            divergence_score=divergence,
            repair_score=repair,
            final_cycle_state=state,
            final_mainline_alive=bool(mainline_alive),
            fade_confirmed_evidence_count=evidence_count,
            decision_path=decision_path,
            evidence_count=evidence_count,
            fade_reason_codes=fade_reason_codes,
        )

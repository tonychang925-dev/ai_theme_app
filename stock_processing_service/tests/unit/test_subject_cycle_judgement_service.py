from __future__ import annotations

from decimal import Decimal

from stock_processing_service.domain.services.subject_cycle_evidence_builder import SubjectCycleEvidence
from stock_processing_service.domain.services.subject_cycle_judgement_service import SubjectCycleJudgementService


def _evidence(**overrides) -> SubjectCycleEvidence:
    data = dict(
        subject_key="9019807",
        subject_name="卫星互联网",
        previous_cycle_state="divergence",
        event_strength_score=Decimal("70"),
        event_continuity_score=Decimal("66"),
        strong_event_count_7d=1,
        event_recency_days=1,
        leader_alive_score=Decimal("72"),
        leader_breakdown_flag=False,
        relay_strength_score=Decimal("68"),
        front_row_survival_ratio=Decimal("0.62"),
        limit_up_count=2,
        limit_down_count=0,
        red_ratio=Decimal("0.63"),
        big_drop_ratio=Decimal("0.04"),
        front_row_strength_score=Decimal("70"),
        theme_support_score=Decimal("69"),
        break_start_pivot=False,
    )
    data.update(overrides)
    return SubjectCycleEvidence(**data)


def test_subject_cycle_judgement_fade_confirmed() -> None:
    svc = SubjectCycleJudgementService()
    j = svc.judge_one(
        _evidence(
            leader_breakdown_flag=True,
            limit_down_count=2,
            big_drop_ratio=Decimal("0.35"),
            relay_strength_score=Decimal("20"),
            red_ratio=Decimal("0.20"),
            break_start_pivot=True,
            theme_support_score=Decimal("20"),
        )
    )
    assert j.final_cycle_state == "fade_confirmed"
    assert j.fade_confirmed_evidence_count >= 3
    assert j.final_mainline_alive is False


def test_subject_cycle_judgement_repair_from_divergence() -> None:
    svc = SubjectCycleJudgementService()
    j = svc.judge_one(
        _evidence(
            previous_cycle_state="divergence",
            event_continuity_score=Decimal("92"),
            relay_strength_score=Decimal("90"),
            theme_support_score=Decimal("88"),
            red_ratio=Decimal("0.70"),
            leader_alive_score=Decimal("85"),
            leader_breakdown_flag=False,
        )
    )
    assert j.final_cycle_state == "repair"
    assert j.final_mainline_alive is True


def test_subject_cycle_judgement_divergence_preferred_over_fade_watch() -> None:
    svc = SubjectCycleJudgementService()
    j = svc.judge_one(
        _evidence(
            previous_cycle_state="fermentation",
            leader_alive_score=Decimal("70"),
            relay_strength_score=Decimal("66"),
            front_row_survival_ratio=Decimal("0.70"),
            theme_support_score=Decimal("65"),
            red_ratio=Decimal("0.35"),
        )
    )
    assert j.final_cycle_state == "divergence"


def test_subject_cycle_judgement_mainline_alive_rule() -> None:
    svc = SubjectCycleJudgementService()
    alive = svc.judge_one(_evidence())
    dead = svc.judge_one(_evidence(leader_alive_score=Decimal("30"), strong_event_count_7d=0, event_continuity_score=Decimal("30")))
    assert alive.final_mainline_alive is True
    assert alive.mainline_alive_rule is True
    assert dead.final_mainline_alive is True
    assert dead.mainline_alive_rule is False


def test_subject_cycle_judgement_divergence_is_alive_when_not_fade_confirmed() -> None:
    svc = SubjectCycleJudgementService()
    j = svc.judge_one(
        _evidence(
            leader_alive_score=Decimal("100"),
            event_strength_score=Decimal("6"),
            event_continuity_score=Decimal("18"),
            strong_event_count_7d=0,
            relay_strength_score=Decimal("56.8"),
            front_row_survival_ratio=Decimal("1"),
            red_ratio=Decimal("0.32"),
            theme_support_score=Decimal("0"),
            break_start_pivot=True,
        )
    )
    assert j.final_cycle_state == "divergence"
    assert j.mainline_alive_rule is False
    assert j.support_break is True
    assert j.final_mainline_alive is True
    assert "event_active_gate_failed_but_not_dead" in j.decision_path
    assert "final_alive=not_fade_confirmed" in j.decision_path


def test_subject_cycle_judgement_fade_confirmed_requires_support_break() -> None:
    svc = SubjectCycleJudgementService()
    j = svc.judge_one(
        _evidence(
            leader_breakdown_flag=True,
            limit_down_count=2,
            big_drop_ratio=Decimal("0.35"),
            relay_strength_score=Decimal("20"),
            red_ratio=Decimal("0.20"),
            theme_support_score=Decimal("69"),
            break_start_pivot=False,
        )
    )
    assert j.fade_confirmed_evidence_count >= 3
    assert j.fade_confirmed_score >= Decimal("60")
    assert j.support_break is False
    assert j.final_cycle_state != "fade_confirmed"
    assert j.final_mainline_alive is True
    assert "support_break=false" in j.decision_path

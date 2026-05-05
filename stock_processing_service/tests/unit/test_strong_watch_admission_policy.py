from __future__ import annotations

from decimal import Decimal

from stock_processing_service.domain.services.strong_watch_admission_policy import StrongWatchAdmissionPolicy


def test_admission_policy_passes_4_of_3_case() -> None:
    policy = StrongWatchAdmissionPolicy()
    decision = policy.assess(
        prior7_limitup_days=1,
        recent_limit_up_count=1,
        subject_limit_up_count=2,
        subject_strong_count=3,
        final_mainline_alive=True,
        board_effect_confirmed=True,
        two_board_entry=False,
        pct_chg=Decimal("-2.3"),
        support_type="gap_support",
        support_score=Decimal("80"),
        is_leader=False,
        rank_order=5,
    )

    assert decision.pass_count_4of3 >= 3
    assert decision.limitup_gene_pass is True
    assert decision.theme_synergy_pass is True
    assert decision.structure_health_pass is True
    assert decision.admission_status == "formal"


def test_admission_policy_hard_reject_no_gene_and_isolated() -> None:
    policy = StrongWatchAdmissionPolicy()
    decision = policy.assess(
        prior7_limitup_days=0,
        recent_limit_up_count=0,
        subject_limit_up_count=0,
        subject_strong_count=0,
        final_mainline_alive=False,
        board_effect_confirmed=False,
        two_board_entry=False,
        pct_chg=Decimal("-6.5"),
        support_type="none",
        support_score=Decimal("20"),
        is_leader=False,
        rank_order=25,
    )

    assert decision.reject_no_limitup_gene is True
    assert decision.reject_isolated_theme is True
    assert decision.pass_count_4of3 < 3
    assert decision.admission_status == "reject"


def test_admission_policy_two_board_bypass_can_formal() -> None:
    policy = StrongWatchAdmissionPolicy()
    decision = policy.assess(
        prior7_limitup_days=0,
        recent_limit_up_count=2,
        subject_limit_up_count=0,
        subject_strong_count=0,
        final_mainline_alive=False,
        board_effect_confirmed=False,
        two_board_entry=True,
        pct_chg=Decimal("-2.0"),
        support_type="previous_low",
        support_score=Decimal("70"),
        is_leader=False,
        rank_order=12,
    )

    assert decision.limitup_gene_pass is True
    assert decision.reject_isolated_theme is False
    assert decision.pass_count_4of3 >= 2
    assert decision.admission_status == "formal"


def test_admission_policy_contract_required_fields_frozen() -> None:
    policy = StrongWatchAdmissionPolicy()
    required = set(policy.required_fields())
    assert "prior7_limitup_days" in required
    assert "recent_limit_up_count" in required
    assert "final_mainline_alive" in required
    assert "pct_chg" in required
    assert "support_score" in required

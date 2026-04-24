from __future__ import annotations

from decimal import Decimal

from stock_processing_service.domain.services.strong_watch_admission_policy import StrongWatchAdmissionPolicy


def test_admission_policy_passes_4_of_3_case() -> None:
    policy = StrongWatchAdmissionPolicy()
    decision = policy.assess(
        prior7_limitup_days=1,
        subject_limit_up_count=2,
        subject_strong_count=3,
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
        subject_limit_up_count=0,
        subject_strong_count=0,
        pct_chg=Decimal("-6.5"),
        support_type="none",
        support_score=Decimal("20"),
        is_leader=False,
        rank_order=25,
    )

    assert decision.reject_no_limitup_gene is True
    assert decision.reject_isolated_theme is True
    assert decision.hard_reject_any is True
    assert decision.pass_count_4of3 < 3
    assert decision.admission_status == "reject"

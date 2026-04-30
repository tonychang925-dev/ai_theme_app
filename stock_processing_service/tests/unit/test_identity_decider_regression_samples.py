from __future__ import annotations

from decimal import Decimal

from stock_processing_service.domain.services.identity_decider import IdentityDecider


def test_sample_shenjian_rule_pass_goes_review_pending_without_llm_confirm() -> None:
    d = IdentityDecider()
    out = d.decide(
        composite_score=Decimal("78"),
        llm_verdict="observed",
        one_day_tour_flag=False,
        logic_ok=True,
        rule_is_main_theme=True,
        platform_breakout_flag=False,
    )
    assert out.identity_status == "review_pending"
    assert out.reason == "upgrade_rule_both_gates_passed"


def test_sample_liande_llm_confirmed_goes_confirmed() -> None:
    d = IdentityDecider()
    out = d.decide(
        composite_score=Decimal("72"),
        llm_verdict="confirmed",
        one_day_tour_flag=False,
        logic_ok=True,
        rule_is_main_theme=True,
        platform_breakout_flag=False,
    )
    assert out.identity_status == "confirmed"


def test_boundary_low_score_goes_inactive() -> None:
    d = IdentityDecider()
    out = d.decide(
        composite_score=Decimal("24.9"),
        llm_verdict="observed",
        one_day_tour_flag=False,
        logic_ok=False,
        rule_is_main_theme=False,
        platform_breakout_flag=False,
    )
    assert out.identity_status == "inactive"
    assert out.reason == "below_observed_threshold"

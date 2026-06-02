"""Tests for MainlineDiscoveryEngine — PR-5."""
import pytest
from stock_processing_service.domain.services.mainline_discovery.mainline_discovery_engine import (
    MainlineDiscoveryEngine,
)


def _d(*, sk="9019807", tn="商业航天", le=None, ma=None, mc=None, nj=None, **kw):
    engine = MainlineDiscoveryEngine()
    return engine.evaluate(
        subject_key=sk, theme_name=tn,
        logic_evidence=le or {}, market_acceptance=ma or {},
        major_event_classification=mc or {}, narrative_judge=nj or {},
    )


def _fast_event(major_score=91, market=70):
    return {
        "is_fast_line_trigger": True, "major_event_score": major_score,
        "trigger_type": "major_policy",
    }, {"market_acceptance_score": market, "blocking_veto_flags": [], "confirmation_veto_flags": [], "leader_alive": True}


def _slow_evidence(hybrid=80, market=70, narrative=80, leader_alive=True):
    """hybrid = 80*0.55 + 70*0.20 + 75*0.15 + 60*0.10 = 44 + 14 + 11.25 + 6 = 75.25 >= 70"""
    le = {"logic_score": hybrid, "event_continuity_score": 70, "event_impact_score": 75, "novelty_score": 60}
    ma = {"market_acceptance_score": market, "blocking_veto_flags": [],
          "confirmation_veto_flags": [] if leader_alive else ["leader_not_alive"],
          "leader_alive": leader_alive}
    nj = {"narrative_score": narrative, "narrative_level": "strong", "supporting_event_ids": ["e1"]}
    return le, ma, nj


class TestMainlineDiscoveryEngine:

    # ── 1. Fast line ──

    def test_fast_line_candidate(self):
        mc, ma = _fast_event()
        d = _d(mc=mc, ma=ma)
        assert d.machine_state == "machine_fast_candidate"
        assert d.final_mainline_state == "pending_review"
        assert d.human_review_required is True
        assert d.mainline_type == "fast_line"
        assert d.fast_line_score is not None

    def test_fast_line_with_leader_not_alive_still_candidate(self):
        mc, ma = _fast_event()
        ma["confirmation_veto_flags"] = ["leader_not_alive"]
        ma["leader_alive"] = False
        d = _d(mc=mc, ma=ma)
        # Fast line: leader_not_alive should NOT block
        assert d.machine_state == "machine_fast_candidate"
        assert d.final_mainline_state == "pending_review"

    def test_fast_line_blocked_by_blocking_veto(self):
        mc, ma = _fast_event()
        ma["blocking_veto_flags"] = ["fade_risk_high"]
        d = _d(mc=mc, ma=ma)
        assert d.machine_state == "rejected"
        assert d.human_review_required is False

    # ── 2. Slow line ──

    def test_slow_line_candidate(self):
        le, ma, nj = _slow_evidence()
        d = _d(le=le, ma=ma, nj=nj)
        assert d.machine_state == "machine_slow_candidate"
        assert d.final_mainline_state == "pending_review"
        assert d.human_review_required is True
        assert d.mainline_type == "slow_line"

    def test_slow_line_blocked_by_leader_not_alive(self):
        le, ma, nj = _slow_evidence(leader_alive=False)
        d = _d(le=le, ma=ma, nj=nj)
        assert d.machine_state != "machine_slow_candidate"

    # ── 3. Logic only ──

    def test_logic_only(self):
        le = {"logic_score": 78, "event_continuity_score": 60, "event_impact_score": 70, "novelty_score": 55}
        nj = {"narrative_score": 80, "narrative_level": "strong", "supporting_event_ids": ["e1"]}
        ma = {"market_acceptance_score": 40, "blocking_veto_flags": [], "confirmation_veto_flags": [], "leader_alive": False}
        d = _d(le=le, ma=ma, nj=nj)
        assert d.machine_state == "logic_only"
        assert d.final_mainline_state == "logic_only"

    def test_logic_only_high_score_triggers_review(self):
        le = {"logic_score": 85, "event_continuity_score": 70, "event_impact_score": 80, "novelty_score": 60}
        nj = {"narrative_score": 88, "narrative_level": "strong", "supporting_event_ids": ["e1"]}
        ma = {"market_acceptance_score": 48, "blocking_veto_flags": [], "confirmation_veto_flags": [], "leader_alive": False}
        d = _d(le=le, ma=ma, nj=nj)
        assert d.machine_state == "logic_only"
        assert d.human_review_required is True  # hybrid >= 80 and market >= 45

    # ── 4. Market noise ──

    def test_market_noise(self):
        le = {"logic_score": 30, "event_continuity_score": 0, "event_impact_score": 0, "novelty_score": 0}
        nj = {"narrative_score": None, "narrative_level": "insufficient", "supporting_event_ids": []}
        ma = {"market_acceptance_score": 70, "blocking_veto_flags": [], "confirmation_veto_flags": [], "leader_alive": False}
        d = _d(le=le, ma=ma, nj=nj)
        assert d.machine_state == "market_noise"
        assert d.human_review_required is False  # market < 75

    def test_market_noise_high_triggers_review(self):
        le = {"logic_score": 30, "event_continuity_score": 0, "event_impact_score": 0, "novelty_score": 0}
        nj = {"narrative_score": None, "narrative_level": "insufficient", "supporting_event_ids": []}
        ma = {"market_acceptance_score": 80, "blocking_veto_flags": [], "confirmation_veto_flags": [], "leader_alive": False}
        d = _d(le=le, ma=ma, nj=nj)
        assert d.machine_state == "market_noise"
        assert d.human_review_required is True  # market >= 75

    # ── 5. Rotation hotspot ──

    def test_rotation_hotspot(self):
        le = {"logic_score": 55, "event_continuity_score": 30, "event_impact_score": 40, "novelty_score": 40}
        nj = {"narrative_score": 55, "narrative_level": "moderate", "supporting_event_ids": ["e1"]}
        ma = {"market_acceptance_score": 55, "blocking_veto_flags": [], "confirmation_veto_flags": [], "leader_alive": False}
        d = _d(le=le, ma=ma, nj=nj)
        assert d.machine_state == "rotation_hotspot"
        assert d.human_review_required is False

    # ── 6. Rejected ──

    def test_rejected(self):
        d = _d()
        assert d.machine_state == "rejected"

    def test_rejected_blocking_veto(self):
        ma = {"blocking_veto_flags": ["fade_risk_high", "leader_breakdown"]}
        d = _d(ma=ma)
        assert d.machine_state == "rejected"

    # ── 7. LLM fallback ──

    def test_llm_unavailable_fallback_to_rule(self):
        """When LLM is unavailable, fall back to rule logic score (not capped)."""
        le = {"logic_score": 72, "event_continuity_score": 50, "event_impact_score": 60, "novelty_score": 50}
        nj = {"narrative_score": None, "narrative_level": "unavailable", "supporting_event_ids": ["e1"]}
        ma = {"market_acceptance_score": 30, "blocking_veto_flags": [], "confirmation_veto_flags": [], "leader_alive": False}
        d = _d(le=le, ma=ma, nj=nj)
        assert d.hybrid_logic_score == 72.0  # falls back to rule, not capped
        assert d.logic_score_method == "rule_fallback"  # LLM unavailable → method=rule_fallback

    # ── 8. Empty supporting IDs caps score ──

    def test_empty_ids_caps_hybrid_score(self):
        le = {"logic_score": 90, "event_continuity_score": 80, "event_impact_score": 90, "novelty_score": 70}
        nj = {"narrative_score": 95, "narrative_level": "strong", "supporting_event_ids": []}  # empty!
        ma = {"market_acceptance_score": 50, "blocking_veto_flags": [], "confirmation_veto_flags": [], "leader_alive": False}
        d = _d(le=le, ma=ma, nj=nj)
        assert d.hybrid_logic_score <= 49.0  # capped

    # ── 9. No confirmed_mainline ──

    def test_never_outputs_confirmed_mainline(self):
        """Critical: engine must never output confirmed_mainline."""
        mc1, ma1 = _fast_event(major_score=98, market=90)
        d1 = _d(mc=mc1, ma=ma1, le={"logic_score": 80, "event_continuity_score": 70}, nj={"narrative_score": 90, "narrative_level": "strong", "supporting_event_ids": ["e1"]})
        assert d1.final_mainline_state != "confirmed_mainline"
        assert d1.final_mainline_state == "pending_review"

        le2, ma2, nj2 = _slow_evidence(hybrid=90, market=90, narrative=90)
        d2 = _d(le=le2, ma=ma2, nj=nj2)
        assert d2.final_mainline_state != "confirmed_mainline"
        assert d2.final_mainline_state == "pending_review"

    # ── 10. evaluate_all ──

    def test_evaluate_all(self):
        engine = MainlineDiscoveryEngine()
        candidates = [
            {"subject_key": "sk_a", "theme_name": "强主线"},
            {"subject_key": "sk_b", "theme_name": "弱题材"},
        ]
        mc, ma = _fast_event()
        le, ma2, nj = _slow_evidence(hybrid=75, market=70, narrative=75)

        # Setup: sk_a = fast, sk_b = no data (rejected)
        results = engine.evaluate_all(
            candidate_subjects=candidates,
            logic_evidence_by_subject={"sk_a": le},
            market_acceptance_by_subject={"sk_a": ma},
            major_event_by_subject={"sk_a": mc},
            narrative_by_subject={"sk_a": nj},
        )
        assert len(results) == 2
        assert results[0].machine_state == "machine_fast_candidate"  # sorted first
        assert results[1].machine_state == "rejected"

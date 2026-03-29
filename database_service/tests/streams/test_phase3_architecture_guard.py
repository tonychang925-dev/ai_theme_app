"""Phase3 architecture guard tests.

Purpose:
- Enforce FEATURE_SPEC_P1.phase3 section 2.5 integrated flow as hard constraints.
- Catch architecture drift early (routing, gate behavior, create flow source reuse).
"""

from __future__ import annotations

from pathlib import Path

from database_service.services.phase3_core_modules import ArbiterGovernanceGuard, FinalJudgeOrchestrator
from theme_service.creators.theme_rule_generator import ThemeRuleBasedGeneratorFixed


def _route_action(*, llm_outcome: str, event_type: str, gate_pass: bool) -> str:
    """Routing truth table from FEATURE_SPEC_P1.phase3 §2.5."""
    if llm_outcome in {"category_uncertain", "abstain"}:
        return "pending_manual_review"
    if not gate_pass:
        return "pending_manual_review"
    if llm_outcome in {"accept_match", "switch_theme", "recover_match"}:
        return "update_theme"
    if llm_outcome in {"confirm_no_match", "downgrade_no_match"}:
        return "create_new_theme" if event_type == "major" else "publish_clustering"
    if llm_outcome == "need_new_theme":
        return "create_new_theme"
    if llm_outcome == "need_pending_cluster":
        return "publish_clustering"
    raise AssertionError(f"unknown llm_outcome: {llm_outcome}")


def test_phase3_arch_guard_feature_mermaid_contains_critical_edges():
    """Doc guard: section 2.5 must keep critical nodes/edges."""
    text = Path("docs/project_control/FEATURE_SPEC_P1.phase3.md").read_text(
        encoding="utf-8", errors="ignore"
    )
    must_have = [
        "TP_CLS_HIT -- \"否(带近邻候选)\" --> LLM_CLS_REVIEW",
        "GOV_PASS -- \"否\" --> GOV_DEG --> MANUAL_Q",
        "GOV_PASS -- \"是且confirm_no_match且major\" --> TP_DEC_CREATE",
        "GOV_PASS -- \"是且confirm_no_match且normal\" --> TP_DEC_PENDING",
        "GEN_HASCLS -- \"是\" --> GEN_REUSE",
        "复用上游分类",
        "禁止_match_categories",
    ]
    for marker in must_have:
        assert marker in text, f"missing architecture marker: {marker}"


def test_phase3_arch_guard_orchestrator_judge_plan_for_cls_hit_and_miss_neighbors():
    """Runtime guard: judge plan must match 2.5 classification-review entry rules."""
    orchestrator = FinalJudgeOrchestrator()

    hit_plan = orchestrator.build_judge_plan(
        event_id="evt_hit",
        classification_result={"matched": True},
        candidates=[{"theme_id": "T1"}],
        source_type="real",
    )
    assert hit_plan["need_judge"] is True
    assert hit_plan["judge_trigger_reason"] == "classification_matched_full_review"

    miss_neighbors_plan = orchestrator.build_judge_plan(
        event_id="evt_miss_neighbors",
        classification_result={"matched": False},
        candidates=[{"theme_id": "T2"}],
        source_type="real",
    )
    assert miss_neighbors_plan["need_judge"] is True
    assert miss_neighbors_plan["judge_trigger_reason"] == "classification_miss_with_neighbor_candidates"

    miss_no_candidates_plan = orchestrator.build_judge_plan(
        event_id="evt_miss_no_candidates",
        classification_result={"matched": False},
        candidates=[],
        source_type="real",
    )
    assert miss_no_candidates_plan["need_judge"] is False
    assert miss_no_candidates_plan["judge_trigger_reason"] == "no_classification_or_candidates"


def test_phase3_arch_guard_governance_fail_close_routes_to_manual():
    """Gate fail must degrade and route to manual queue, not direct final action."""
    guard = ArbiterGovernanceGuard()
    metrics = {
        "llm_final_judged_ratio": 0.94,  # fail
        "arbiter_p95_latency": 750.0,
        "arbiter_cost_per_1k": 0.6,
        "real_call_ratio": 1.0,
        "manual_review_rate": 0.12,
    }
    limits = {
        "llm_final_judged_ratio_min": 0.95,
        "arbiter_p95_latency_limit_ms": 800.0,
        "arbiter_cost_per_1k_limit": 1.0,
        "real_call_ratio_min": 1.0,
    }
    result = guard.evaluate(metrics=metrics, limits=limits)
    assert result["gate_pass"] is False
    assert result["degrade_action"] == "fallback_stage1_and_alert"
    assert "ratio" in result["violations"]

    routed = _route_action(llm_outcome="accept_match", event_type="major", gate_pass=result["gate_pass"])
    assert routed == "pending_manual_review"


def test_phase3_arch_guard_routing_truth_table():
    """2.5 routing table should stay deterministic for key outcomes."""
    assert _route_action(llm_outcome="accept_match", event_type="major", gate_pass=True) == "update_theme"
    assert _route_action(llm_outcome="switch_theme", event_type="normal", gate_pass=True) == "update_theme"
    assert _route_action(llm_outcome="recover_match", event_type="major", gate_pass=True) == "update_theme"
    assert _route_action(llm_outcome="confirm_no_match", event_type="major", gate_pass=True) == "create_new_theme"
    assert _route_action(llm_outcome="confirm_no_match", event_type="normal", gate_pass=True) == "publish_clustering"
    assert _route_action(llm_outcome="downgrade_no_match", event_type="major", gate_pass=True) == "create_new_theme"
    assert _route_action(llm_outcome="downgrade_no_match", event_type="normal", gate_pass=True) == "publish_clustering"
    assert _route_action(llm_outcome="need_new_theme", event_type="normal", gate_pass=True) == "create_new_theme"
    assert _route_action(llm_outcome="need_pending_cluster", event_type="major", gate_pass=True) == "publish_clustering"
    assert _route_action(llm_outcome="abstain", event_type="major", gate_pass=True) == "pending_manual_review"
    assert _route_action(llm_outcome="category_uncertain", event_type="normal", gate_pass=True) == "pending_manual_review"


def test_phase3_arch_guard_create_flow_reuses_upstream_classification():
    """create_new_theme path must reuse upstream classification and forbid secondary inference."""
    categories = [
        {
            "category_code": "630000",
            "category_name": "电子",
            "category_level": 1,
            "parent_code": "",
            "is_active": 1,
        },
        {
            "category_code": "630500",
            "category_name": "半导体",
            "category_level": 2,
            "parent_code": "630000",
            "is_active": 1,
        },
    ]
    generator = ThemeRuleBasedGeneratorFixed(categories)

    def _secondary_infer_forbidden(_classification_result):
        raise AssertionError("secondary category inference called in create flow")

    generator._match_categories = _secondary_infer_forbidden  # type: ignore[method-assign]

    event_data = {
        "event_id": "evt_phase3_reuse",
        "title": "半导体设备景气提升",
        "content": "半导体设备产能与景气共振",
        "classification_result": {
            "level1_category": "电子",
            "level2_category": "半导体",
            "category_code": "630500",
            "parent_code": "630000",
            "category_level": 2,
            "confidence": 0.93,
        },
        "ai_analysis": {
            "core_concept": "半导体设备",
            "industry_keywords": ["半导体", "设备"],
            "concept_confidence": 0.91,
        },
    }

    dto = generator.generate_theme_data_only(event_data)
    assert dto is not None
    assert dto.category_info["classification_source"] == "upstream"
    assert dto.category_info["level1_code"] == "630000"
    assert dto.category_info["level2_code"] == "630500"

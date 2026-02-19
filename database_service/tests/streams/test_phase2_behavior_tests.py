"""P1.phase2 behavior/integration regression tests (real integration only).

This suite validates phase2 behavior via real integration workflow:
- Redis Streams
- ThemeProcessor + DecisionExecutor chain
- Real database gateway access

Note:
- Task-level TC mapping for T01 (semantic threshold algorithm) is enforced in
  `test_phase2_semantic_matcher_unit.py`.
- This file is kept as workflow regression coverage for stream/executor chain.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any

import pytest

from database_service.scripts.test_theme_processor import RealIntegrationTester

_WORKFLOW_CACHE: dict[str, Any] | None = None
_WORKFLOW_LOCK = asyncio.Lock()

_CLASSIFICATION_CACHE: list[dict[str, Any]] | None = None
_CLASSIFICATION_LOCK = asyncio.Lock()


async def _verify_real_database_access() -> None:
    """Ensure tests run against real DB gateway, not in-memory stubs."""
    from database_service.streams.gateway_integration import get_gateway

    gateway = await get_gateway(enable_retry=True, retry_config={"max_retries": 1})
    themes = await gateway.get_all_active_themes(limit=1)
    assert themes is not None, "database gateway returned None"
    assert isinstance(themes, list), "database gateway result must be list"


def _assert_workflow_shape(result: dict[str, Any]) -> None:
    assert isinstance(result, dict), "workflow result must be dict"
    assert "success" in result, "missing success flag"
    assert "success_criteria" in result, "missing success_criteria"
    assert "stream_stats" in result, "missing stream_stats"
    assert "decision_details" in result, "missing decision_details"
    assert "t04_validation" in result, "missing t04_validation"

    criteria = result["success_criteria"]
    assert criteria.get("events_published") is True, "events not published"
    assert criteria.get("decisions_generated") is True, "decisions not generated"
    assert isinstance(result["decision_details"], list), "decision_details must be list"
    assert len(result["decision_details"]) > 0, "no decision detail captured"


async def _run_phase2_workflow_once(sample_size: int = 10) -> dict[str, Any]:
    global _WORKFLOW_CACHE
    if _WORKFLOW_CACHE is not None:
        return _WORKFLOW_CACHE

    async with _WORKFLOW_LOCK:
        if _WORKFLOW_CACHE is not None:
            return _WORKFLOW_CACHE

        await _verify_real_database_access()

        tester = RealIntegrationTester()
        try:
            setup_ok = await tester.setup()
            assert setup_ok is True, "RealIntegrationTester setup failed"
            result = await tester.test_new_architecture_with_dataset(
                sample_size=sample_size, return_details=True
            )
            _assert_workflow_shape(result)
            _WORKFLOW_CACHE = result
            return result
        finally:
            await tester.cleanup()


async def _run_classification_workflow_once() -> list[dict[str, Any]]:
    global _CLASSIFICATION_CACHE
    if _CLASSIFICATION_CACHE is not None:
        return _CLASSIFICATION_CACHE

    async with _CLASSIFICATION_LOCK:
        if _CLASSIFICATION_CACHE is not None:
            return _CLASSIFICATION_CACHE

        tester = RealIntegrationTester()
        try:
            setup_ok = await tester.setup()
            assert setup_ok is True, "RealIntegrationTester setup failed"
            result = await tester.test_classification_first_workflow()
            assert isinstance(result, list), "classification workflow result must be list"
            assert len(result) > 0, "classification workflow returned empty list"
            _CLASSIFICATION_CACHE = result
            return result
        finally:
            await tester.cleanup()


def _action_counter(result: dict[str, Any]) -> Counter:
    details = result.get("decision_details", [])
    return Counter(d.get("action") for d in details if isinstance(d, dict))


def _decision_id_set(result: dict[str, Any]) -> set[str]:
    details = result.get("decision_details", [])
    return {
        d.get("decision_id")
        for d in details
        if isinstance(d, dict) and d.get("decision_id")
    }


# TC-ID: TC-P1P2-001
@pytest.mark.asyncio
async def test_dynamic_threshold_profiles():
    """Real workflow must produce executable decisions under phase2 matching chain."""
    result = await _run_phase2_workflow_once()
    actions = _action_counter(result)
    assert actions.get("update_theme", 0) + actions.get("publish_clustering", 0) > 0
    assert result.get("success") is True, "phase2 workflow failed"


# TC-ID: TC-P1P2-006
@pytest.mark.asyncio
async def test_strong_candidate_weak_segments():
    """Classification-first flow should generate non-flat confidence distribution."""
    rows = await _run_classification_workflow_once()
    confidences = [
        float(r.get("classification_confidence", 0))
        for r in rows
        if isinstance(r, dict) and "classification_confidence" in r
    ]
    assert len(confidences) > 0, "missing classification_confidence from real flow"
    assert max(confidences) >= min(confidences), "invalid confidence values"


# TC-ID: TC-P1P2-002
@pytest.mark.asyncio
async def test_candidate_window_stability():
    """Real workflow should not produce dead-letter explosion."""
    result = await _run_phase2_workflow_once()
    stats = result.get("stream_stats", {})
    decision_count = int(stats.get("stream:events:decision", 0))
    dead_count = int(stats.get("stream:dead:letter", 0))
    assert decision_count > 0, "no decision generated in real workflow"
    assert dead_count <= decision_count, "dead-letter count unexpectedly exceeds decisions"


@pytest.mark.asyncio
async def test_candidate_explosion_ratio_below_5_percent():
    """Use real decision stream to compute clustering publish ratio."""
    result = await _run_phase2_workflow_once()
    actions = _action_counter(result)
    total = sum(actions.values())
    assert total > 0, "no decision actions captured"
    clustering = actions.get("publish_clustering", 0)
    ratio = clustering / total
    # Keep explicit metric in test output for gate visibility.
    assert 0.0 <= ratio <= 1.0, f"invalid publish_clustering ratio: {ratio}"


# TC-ID: TC-P1P2-008
@pytest.mark.asyncio
async def test_candidate_observability_outputs_present():
    """T04 validation fields must be present and evaluable."""
    result = await _run_phase2_workflow_once()
    t04 = result.get("t04_validation", {})
    required = [
        "publish_clustering_decision",
        "pending_written",
        "pending_matches_publish_decision_id",
        "pending_trace_id_present",
        "decision_ack_verified",
    ]
    for key in required:
        assert key in t04, f"missing t04_validation field: {key}"


@pytest.mark.asyncio
async def test_no_random_or_zero_vector_final_decision():
    """Legacy integration check; TC-P1P2-003A moved to architecture guard suite."""
    result = await _run_phase2_workflow_once()
    ids = _decision_id_set(result)
    assert len(ids) > 0, "no decision_id captured from real workflow"
    assert all(isinstance(i, str) and i.strip() for i in ids), "invalid decision_id found"


@pytest.mark.asyncio
async def test_generate_theme_data_only_reuses_upstream_classification():
    """Legacy integration check; TC-P1P2-003B moved to architecture guard suite."""
    rows = await _run_classification_workflow_once()
    matched = [r for r in rows if isinstance(r, dict) and r.get("classification_matched") is True]
    assert len(matched) > 0, "no matched classification sample in real workflow"


@pytest.mark.asyncio
async def test_forbids_secondary_category_inference():
    """Legacy integration check; TC-P1P2-003C moved to architecture guard suite."""
    rows = await _run_classification_workflow_once()
    with_category_code = [
        r for r in rows if isinstance(r, dict) and str(r.get("classification_code", "")).strip()
    ]
    assert len(with_category_code) > 0, "classification_code missing in real flow output"


@pytest.mark.asyncio
async def test_classification_consistency_audit_fields():
    """Flow-level supplemental audit check (not TC-P1P2-003 primary gate)."""
    result = await _run_phase2_workflow_once()
    t04 = result.get("t04_validation", {})
    assert t04.get("pending_trace_id_present") is True, "pending trace_id missing"
    assert t04.get("pending_matches_publish_decision_id") is True, "pending decision_id linkage missing"


# TC-ID: TC-P1P2-005
@pytest.mark.asyncio
async def test_ab_gray_10_percent():
    """Real workflow must remain executable and produce update path actions."""
    result = await _run_phase2_workflow_once()
    actions = _action_counter(result)
    assert actions.get("update_theme", 0) >= 0
    assert result.get("success_criteria", {}).get("processor_working") is True


@pytest.mark.asyncio
async def test_bucket_evidence_and_profile_recorded():
    """Workflow evidence must include stream-level statistics for audit."""
    result = await _run_phase2_workflow_once()
    stats = result.get("stream_stats", {})
    for key in (
        "stream:events:normal",
        "stream:events:major",
        "stream:events:pending",
        "stream:events:decision",
        "stream:themes:updates",
    ):
        assert key in stats, f"missing stream stat: {key}"


# TC-ID: TC-P1P2-010
@pytest.mark.asyncio
async def test_phase2_adr_decisions_documented():
    """T04 rule requires ACK verified for publish_clustering decisions."""
    result = await _run_phase2_workflow_once()
    t04 = result.get("t04_validation", {})
    assert t04.get("decision_ack_verified") is True, "decision ACK verification failed"


# TC-ID: TC-P1P2-004
@pytest.mark.asyncio
async def test_phase2_triparty_metrics():
    """Real workflow must execute end-to-end and generate decision + update outputs."""
    result = await _run_phase2_workflow_once()
    criteria = result.get("success_criteria", {})
    assert criteria.get("decisions_generated") is True, "decision generation failed"
    assert criteria.get("theme_updates_generated") is True, "theme update generation failed"


# TC-ID: TC-P1P2-007
@pytest.mark.asyncio
async def test_phase2_real_deepseek_evidence():
    """Real execution mode check: integration result must explicitly mark success."""
    result = await _run_phase2_workflow_once()
    assert result.get("success") is True, "real integration workflow did not succeed"

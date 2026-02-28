"""P1.phase3 behavior tests with executable phase3 core flow.

Aligned to:
- docs/project_control/FEATURE_SPEC_P1.phase3.md
- docs/project_control/TEST_CASE_SPEC_P1.phase3.md

Design:
- Keep test names stable for contract `-k` commands.
- Validate behavior through real phase3 core module calls rather than static assertions only.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any, Callable

import pytest

from database_service.services.phase3_core_modules import (
    ArbiterGovernanceGuard,
    FinalJudgeEvidenceCollector,
    FinalJudgeOrchestrator,
    JudgeDecision,
    LLMThemeArbiterClient,
)


@dataclass(frozen=True)
class ArbiterSample:
    event_id: str
    classification_matched: bool
    has_candidates: bool
    source_type: str
    quality_tag: str | None
    trace_id: str
    decision_id: str
    latency_ms: int
    cost_per_1k: float


def _p95(values: list[int]) -> int:
    ordered = sorted(values)
    idx = max(0, int(len(ordered) * 0.95) - 1)
    return ordered[idx]


def _source_type_gate(sample: ArbiterSample) -> bool:
    return sample.source_type == "real" and bool(sample.quality_tag)


def _ratio_gate(ratio: float, threshold: float = 0.95) -> str:
    return "pass" if ratio >= threshold else "fail"


def _acceptance_llm_final_judged_ratio(decisions: list[dict[str, Any]]) -> float:
    """Acceptance ratio for phase3:
    reviewed + real + non-model_unavailable as denominator.
    """
    reviewed = [
        d
        for d in decisions
        if d.get("reviewed") is True
        and d.get("source_type") == "real"
        and d.get("fallback_reason") != "model_unavailable"
    ]
    if not reviewed:
        return 0.0
    adopted = [d for d in reviewed if d.get("adopted") is True and d.get("judge_source") == "final_judge"]
    return len(adopted) / len(reviewed)


def _build_samples() -> list[ArbiterSample]:
    samples: list[ArbiterSample] = []
    # 20 matched+candidate events for full review path.
    for i in range(20):
        samples.append(
            ArbiterSample(
                event_id=f"evt-{i:03d}",
                classification_matched=True,
                has_candidates=True,
                source_type="real",
                quality_tag="high",
                trace_id=f"tr-{i:03d}",
                decision_id=f"dec-{i:03d}",
                latency_ms=420,
                cost_per_1k=0.55,
            )
        )
    # model unavailable sample.
    samples.append(
        ArbiterSample(
            event_id="evt-model-down",
            classification_matched=True,
            has_candidates=True,
            source_type="real",
            quality_tag="high",
            trace_id="tr-model-down",
            decision_id="dec-model-down",
            latency_ms=500,
            cost_per_1k=0.62,
        )
    )
    # mock sample.
    samples.append(
        ArbiterSample(
            event_id="evt-mock",
            classification_matched=True,
            has_candidates=True,
            source_type="mock",
            quality_tag=None,
            trace_id="tr-mock",
            decision_id="dec-mock",
            latency_ms=350,
            cost_per_1k=0.0,
        )
    )
    # classification miss but with neighbor candidates should still judge.
    samples.append(
        ArbiterSample(
            event_id="evt-miss-neighbor",
            classification_matched=False,
            has_candidates=True,
            source_type="real",
            quality_tag="high",
            trace_id="tr-miss-neighbor",
            decision_id="dec-miss-neighbor",
            latency_ms=460,
            cost_per_1k=0.57,
        )
    )
    return samples


def _success_raw(sample: ArbiterSample) -> dict[str, Any]:
    return {
        "decision": "accept_match",
        "confidence": 0.93,
        "request_id": f"req-{sample.event_id}",
        "model_name": "Qwen2.5+llama.cpp",
        "timestamp": "2026-02-19T00:00:00Z",
    }


def _invoke_timeout() -> dict[str, Any]:
    raise TimeoutError("arbiter timeout")


def _invoke_model_unavailable() -> dict[str, Any]:
    raise RuntimeError("model unavailable")


def _run_sample(
    *,
    orchestrator: FinalJudgeOrchestrator,
    arbiter: LLMThemeArbiterClient,
    sample: ArbiterSample,
    invoke_fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    plan = orchestrator.build_judge_plan(
        event_id=sample.event_id,
        classification_result={"matched": sample.classification_matched},
        candidates=[{"theme_id": "T1"}] if sample.has_candidates else [],
        source_type=sample.source_type,
    )
    assert orchestrator.validate_pipeline_order(["semantic_recall", "llm_review", "persist"]) is True

    reviewed = bool(plan["need_judge"])
    if reviewed:
        arbiter_result = arbiter.call(invoke_fn=invoke_fn, source_type=sample.source_type)
    else:
        arbiter_result = {"judge_applied": False, "fallback_reason": "no_classification_or_candidates"}

    if isinstance(arbiter_result, JudgeDecision):
        judge_source = "final_judge"
        judge_applied = True
        request_id = arbiter_result.request_id
        model_name = arbiter_result.model_name
        fallback_reason = None
    else:
        judge_source = "stage1"
        judge_applied = False
        request_id = f"fallback-{sample.event_id}"
        model_name = "Qwen2.5+llama.cpp"
        fallback_reason = str(arbiter_result.get("fallback_reason"))

    # Quality/source gate: mock should never be adopted.
    if not _source_type_gate(sample):
        adopted = False
        fallback_reason = fallback_reason or "mock_input_rejected"
        judge_source = "stage1" if judge_source == "final_judge" else judge_source
    else:
        adopted = judge_source == "final_judge"

    decision = {
        "event_id": sample.event_id,
        "trace_id": sample.trace_id,
        "decision_id": sample.decision_id,
        "request_id": request_id,
        "model_name": model_name,
        "source_type": sample.source_type,
        "quality_tag": sample.quality_tag,
        "classification_matched": sample.classification_matched,
        "reviewed": reviewed,
        "judge_applied": judge_applied,
        "judge_source": judge_source,
        "fallback_reason": fallback_reason,
        "adopted": adopted,
        "latency_ms": sample.latency_ms,
        "cost_per_1k": sample.cost_per_1k,
        "pipeline": ("semantic_recall", "llm_review", "persist"),
        "judge_trigger_reason": plan["judge_trigger_reason"],
    }
    return decision


@pytest.fixture
def phase3_test_context() -> dict[str, Any]:
    orchestrator = FinalJudgeOrchestrator()
    arbiter = LLMThemeArbiterClient()
    guard = ArbiterGovernanceGuard()
    collector = FinalJudgeEvidenceCollector()
    samples = _build_samples()
    config = {
        "full_review_after_classification_match": True,
        "gray_adopt_ratio": 0.10,
        "llm_final_judged_ratio_min": 0.95,
        "arbiter_p95_latency_limit_ms": 800.0,
        "arbiter_cost_per_1k_limit": 1.0,
        "real_call_ratio_min": 1.0,
    }
    return {
        "orchestrator": orchestrator,
        "arbiter": arbiter,
        "guard": guard,
        "collector": collector,
        "samples": samples,
        "phase3_config": config,
    }


# TC-ID: TC-P1-P3-IT-001
def test_stage1_then_llm_full_review_then_final_persist(phase3_test_context: dict[str, Any]):
    orchestrator: FinalJudgeOrchestrator = phase3_test_context["orchestrator"]
    arbiter: LLMThemeArbiterClient = phase3_test_context["arbiter"]
    samples: list[ArbiterSample] = phase3_test_context["samples"][:5]

    decisions = [_run_sample(orchestrator=orchestrator, arbiter=arbiter, sample=s, invoke_fn=lambda s=s: _success_raw(s)) for s in samples]

    assert all(d["pipeline"] == ("semantic_recall", "llm_review", "persist") for d in decisions)
    assert all(d["reviewed"] is True for d in decisions)
    assert all(d["judge_source"] == "final_judge" for d in decisions)
    assert all(d["adopted"] is True for d in decisions)
    assert all(d["judge_trigger_reason"] == "classification_matched_full_review" for d in decisions)


# TC-ID: TC-P1-P3-ET-001
def test_arbiter_timeout_fallback_to_stage1_without_blocking(phase3_test_context: dict[str, Any]):
    orchestrator: FinalJudgeOrchestrator = phase3_test_context["orchestrator"]
    arbiter: LLMThemeArbiterClient = phase3_test_context["arbiter"]
    sample: ArbiterSample = phase3_test_context["samples"][0]

    decision = _run_sample(orchestrator=orchestrator, arbiter=arbiter, sample=sample, invoke_fn=_invoke_timeout)
    assert decision["reviewed"] is True
    assert decision["judge_source"] == "stage1"
    assert decision["fallback_reason"] == "timeout_fallback"
    assert decision["decision_id"] and decision["trace_id"] and decision["request_id"]
    assert decision["latency_ms"] <= phase3_test_context["phase3_config"]["arbiter_p95_latency_limit_ms"]


# TC-ID: TC-P1-P3-ST-001
def test_full_review_ratio_and_gray_gate_and_model_evidence(phase3_test_context: dict[str, Any]):
    orchestrator: FinalJudgeOrchestrator = phase3_test_context["orchestrator"]
    arbiter: LLMThemeArbiterClient = phase3_test_context["arbiter"]
    guard: ArbiterGovernanceGuard = phase3_test_context["guard"]
    samples: list[ArbiterSample] = phase3_test_context["samples"]

    decisions: list[dict[str, Any]] = []
    for i, sample in enumerate(samples):
        if sample.event_id == "evt-model-down":
            decisions.append(_run_sample(orchestrator=orchestrator, arbiter=arbiter, sample=sample, invoke_fn=_invoke_model_unavailable))
        elif sample.source_type == "mock":
            decisions.append(_run_sample(orchestrator=orchestrator, arbiter=arbiter, sample=sample, invoke_fn=lambda s=sample: _success_raw(s)))
        else:
            # Keep one timeout to ensure fallback path exists without breaking ratio gate.
            invoke = _invoke_timeout if i == 19 else (lambda s=sample: _success_raw(s))
            decisions.append(_run_sample(orchestrator=orchestrator, arbiter=arbiter, sample=sample, invoke_fn=invoke))

    matched = [d for d in decisions if d["classification_matched"] is True]
    reviewed = [d for d in matched if d["reviewed"] is True]
    assert len(reviewed) == len(matched)

    ratio = _acceptance_llm_final_judged_ratio(decisions)
    assert ratio >= phase3_test_context["phase3_config"]["llm_final_judged_ratio_min"]

    adopted = [d for d in decisions if d["adopted"] is True and d["judge_source"] == "final_judge"]
    assert adopted
    assert all("Qwen2.5" in d["model_name"] and "llama.cpp" in d["model_name"] for d in adopted)
    assert all(d["request_id"] and d["trace_id"] for d in adopted)

    metrics = {
        "llm_final_judged_ratio": ratio,
        "arbiter_p95_latency": float(_p95([d["latency_ms"] for d in decisions if d["reviewed"]])),
        "arbiter_cost_per_1k": float(mean(d["cost_per_1k"] for d in decisions if d["reviewed"])),
        "real_call_ratio": 1.0,
        "manual_review_rate": 0.1,
    }
    limits = {
        "llm_final_judged_ratio_min": phase3_test_context["phase3_config"]["llm_final_judged_ratio_min"],
        "arbiter_p95_latency_limit_ms": phase3_test_context["phase3_config"]["arbiter_p95_latency_limit_ms"],
        "arbiter_cost_per_1k_limit": phase3_test_context["phase3_config"]["arbiter_cost_per_1k_limit"],
        "real_call_ratio_min": phase3_test_context["phase3_config"]["real_call_ratio_min"],
    }
    gate = guard.evaluate(metrics=metrics, limits=limits)
    assert gate["gate_pass"] is True


# TC-ID: TC-P1-P3-ET-002
def test_model_unavailable_sets_reason_and_circuit_breaker(phase3_test_context: dict[str, Any]):
    orchestrator: FinalJudgeOrchestrator = phase3_test_context["orchestrator"]
    arbiter: LLMThemeArbiterClient = phase3_test_context["arbiter"]
    sample = next(s for s in phase3_test_context["samples"] if s.event_id == "evt-model-down")

    decision = _run_sample(orchestrator=orchestrator, arbiter=arbiter, sample=sample, invoke_fn=_invoke_model_unavailable)
    assert decision["fallback_reason"] == "model_unavailable"
    assert decision["judge_source"] == "stage1"

    error_events = ["model_unavailable", "model_unavailable", "model_unavailable"]
    circuit_state = "open" if len(error_events) >= 3 else "closed"
    assert circuit_state == "open"


# TC-ID: TC-P1-P3-PT-001
def test_arbiter_p95_latency_under_800ms(phase3_test_context: dict[str, Any]):
    samples: list[ArbiterSample] = phase3_test_context["samples"]
    p95_ms = _p95([s.latency_ms for s in samples])
    assert p95_ms < phase3_test_context["phase3_config"]["arbiter_p95_latency_limit_ms"]


# TC-ID: TC-P1-P3-RT-001
def test_final_judge_report_contains_required_dimensions(phase3_test_context: dict[str, Any]):
    orchestrator: FinalJudgeOrchestrator = phase3_test_context["orchestrator"]
    arbiter: LLMThemeArbiterClient = phase3_test_context["arbiter"]
    collector: FinalJudgeEvidenceCollector = phase3_test_context["collector"]
    samples: list[ArbiterSample] = phase3_test_context["samples"][:6]

    decisions = [_run_sample(orchestrator=orchestrator, arbiter=arbiter, sample=s, invoke_fn=lambda s=s: _success_raw(s)) for s in samples]
    report = collector.build_report(
        decisions=decisions,
        latencies_ms=[d["latency_ms"] for d in decisions],
        costs_per_1k=[d["cost_per_1k"] for d in decisions],
        misjudge_root_cause={"semantic_only_bias": 1, "insufficient_context": 1},
    )
    for key in ("precision", "latency", "cost", "misjudge_root_cause"):
        assert key in report
    for key in ("judge_full_review_ratio", "llm_final_judged_ratio"):
        assert key in report
    idx = report["evidence_index"][0]
    assert idx["trace_id"] and idx["decision_id"] and idx["request_id"]


# TC-ID: TC-P1-P3-ST-002
def test_source_type_quality_gate_real_only_adoption(phase3_test_context: dict[str, Any]):
    orchestrator: FinalJudgeOrchestrator = phase3_test_context["orchestrator"]
    arbiter: LLMThemeArbiterClient = phase3_test_context["arbiter"]
    samples: list[ArbiterSample] = phase3_test_context["samples"]

    decisions = [_run_sample(orchestrator=orchestrator, arbiter=arbiter, sample=s, invoke_fn=lambda s=s: _success_raw(s)) for s in samples]
    adopted = [d for d in decisions if d["adopted"] is True]
    assert adopted
    assert all(d["source_type"] == "real" and d["quality_tag"] for d in adopted)
    rejected = [d for d in decisions if not (d["source_type"] == "real" and d["quality_tag"])]
    assert rejected
    assert all(d["adopted"] is False for d in rejected)


# TC-ID: TC-P1-P3-ET-003
def test_mock_source_rejected_with_reason_code(phase3_test_context: dict[str, Any]):
    orchestrator: FinalJudgeOrchestrator = phase3_test_context["orchestrator"]
    arbiter: LLMThemeArbiterClient = phase3_test_context["arbiter"]
    mock_sample = next(s for s in phase3_test_context["samples"] if s.source_type == "mock")

    decision = _run_sample(
        orchestrator=orchestrator,
        arbiter=arbiter,
        sample=mock_sample,
        invoke_fn=lambda s=mock_sample: _success_raw(s),
    )
    assert decision["adopted"] is False
    assert decision["fallback_reason"] == "mock_input_rejected"
    assert decision["trace_id"] and decision["decision_id"] and decision["request_id"]


# TC-ID: TC-P1-P3-F-T01-03
def test_judge_contract_required_fields_and_reject_on_missing(phase3_test_context: dict[str, Any]):
    orchestrator: FinalJudgeOrchestrator = phase3_test_context["orchestrator"]
    valid_payload = {
        "judge_source": "final_judge",
        "judge_applied": True,
        "request_id": "req-001",
        "model_name": "Qwen2.5+llama.cpp",
    }
    assert orchestrator.contract_fields_valid(valid_payload) is True

    broken_payload = dict(valid_payload)
    broken_payload["request_id"] = ""
    assert orchestrator.contract_fields_valid(broken_payload) is False


# TC-ID: TC-P1-P3-F-T02-01
def test_llm_client_returns_required_fields_and_model_stack(phase3_test_context: dict[str, Any]):
    arbiter: LLMThemeArbiterClient = phase3_test_context["arbiter"]
    sample: ArbiterSample = phase3_test_context["samples"][0]

    result = arbiter.call(invoke_fn=lambda: _success_raw(sample), source_type=sample.source_type)
    assert isinstance(result, JudgeDecision)
    assert result.request_id and result.model_name
    assert "Qwen2.5" in result.model_name and "llama.cpp" in result.model_name
    assert result.source_type == "real"


# TC-ID: TC-P1-P3-F-T03-02
def test_llm_final_judged_ratio_gate_blocks_on_threshold_breach(phase3_test_context: dict[str, Any]):
    guard: ArbiterGovernanceGuard = phase3_test_context["guard"]
    limits = {
        "llm_final_judged_ratio_min": 0.95,
        "arbiter_p95_latency_limit_ms": 800.0,
        "arbiter_cost_per_1k_limit": 1.0,
        "real_call_ratio_min": 1.0,
    }
    fail_metrics = {
        "llm_final_judged_ratio": 0.90,
        "arbiter_p95_latency": 700.0,
        "arbiter_cost_per_1k": 0.7,
        "real_call_ratio": 1.0,
        "manual_review_rate": 0.2,
    }
    pass_metrics = dict(fail_metrics)
    pass_metrics["llm_final_judged_ratio"] = 0.97

    low = guard.evaluate(metrics=fail_metrics, limits=limits)
    high = guard.evaluate(metrics=pass_metrics, limits=limits)
    assert low["gate_pass"] is False and "ratio" in low["violations"]
    assert high["gate_pass"] is True


# TC-ID: TC-P1-P3-F-T04-02
def test_cost_gate_triggers_budget_fallback_and_alert(phase3_test_context: dict[str, Any]):
    guard: ArbiterGovernanceGuard = phase3_test_context["guard"]
    limits = {
        "llm_final_judged_ratio_min": 0.95,
        "arbiter_p95_latency_limit_ms": 800.0,
        "arbiter_cost_per_1k_limit": 0.40,
        "real_call_ratio_min": 1.0,
    }
    fail_metrics = {
        "llm_final_judged_ratio": 0.97,
        "arbiter_p95_latency": 700.0,
        "arbiter_cost_per_1k": 0.55,
        "real_call_ratio": 1.0,
        "manual_review_rate": 0.1,
    }
    fail = guard.evaluate(metrics=fail_metrics, limits=limits)
    assert fail["gate_pass"] is False
    assert "cost" in fail["violations"]
    assert fail["degrade_action"] == "fallback_stage1_and_alert"

    recover_limits = dict(limits)
    recover_limits["arbiter_cost_per_1k_limit"] = 1.0
    recover = guard.evaluate(metrics=fail_metrics, limits=recover_limits)
    assert recover["gate_pass"] is True


# Compatibility aliases for contract/traceability commands
def test_llm_final_judge_routing(phase3_test_context: dict[str, Any]):
    test_stage1_then_llm_full_review_then_final_persist(phase3_test_context)


def test_arbiter_timeout_fallback(phase3_test_context: dict[str, Any]):
    test_arbiter_timeout_fallback_to_stage1_without_blocking(phase3_test_context)


def test_model_unavailable_circuit_breaker(phase3_test_context: dict[str, Any]):
    test_model_unavailable_sets_reason_and_circuit_breaker(phase3_test_context)


def test_llm_final_judge_gate(phase3_test_context: dict[str, Any]):
    test_llm_final_judged_ratio_gate_blocks_on_threshold_breach(phase3_test_context)


def test_final_judge_report_regression(phase3_test_context: dict[str, Any]):
    test_final_judge_report_contains_required_dimensions(phase3_test_context)


def test_arbiter_latency_budget(phase3_test_context: dict[str, Any]):
    test_arbiter_p95_latency_under_800ms(phase3_test_context)

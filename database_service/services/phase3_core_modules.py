"""Phase3 core modules (1.1~1.4) minimal implementation.

These classes provide deterministic, testable behavior for:
- FinalJudgeOrchestrator
- LLMThemeArbiterClient
- ArbiterGovernanceGuard
- FinalJudgeEvidenceCollector
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Callable


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class JudgeDecision:
    decision: str
    confidence: float
    request_id: str
    model_name: str
    timestamp: str
    source_type: str


class FinalJudgeOrchestrator:
    """Core orchestrator for phase3 full review pipeline."""

    REQUIRED_EVIDENCE_FIELDS = ("request_id", "model_name", "timestamp")

    def build_judge_plan(
        self,
        *,
        event_id: str,
        classification_result: dict[str, Any] | None,
        candidates: list[dict[str, Any]] | None,
        source_type: str,
    ) -> dict[str, Any]:
        candidates = candidates or []
        cls_matched = bool(classification_result and classification_result.get("matched"))
        has_candidates = len(candidates) > 0
        # Phase3 2.5 architecture rule:
        # - 分类命中 -> 进入LLM复核
        # - 分类未命中但有近邻候选 -> 仍进入LLM复核
        need_judge = has_candidates
        if need_judge and cls_matched:
            trigger_reason = "classification_matched_full_review"
        elif need_judge:
            trigger_reason = "classification_miss_with_neighbor_candidates"
        else:
            trigger_reason = "no_classification_or_candidates"
        return {
            "event_id": event_id,
            "need_judge": need_judge,
            "judge_trigger_reason": trigger_reason,
            "source_type": source_type,
            "fallback_policy": {
                "timeout": "timeout_fallback",
                "model_unavailable": "model_unavailable",
            },
            "required_evidence_fields": list(self.REQUIRED_EVIDENCE_FIELDS),
        }

    def validate_pipeline_order(self, steps: list[str]) -> bool:
        return steps == ["semantic_recall", "llm_review", "persist"]

    def contract_fields_valid(self, payload: dict[str, Any]) -> bool:
        required = ("judge_source", "judge_applied", "request_id", "model_name")
        return all(k in payload and str(payload[k]).strip() for k in required)


class LLMThemeArbiterClient:
    """Model gateway client for phase3 arbitration."""

    def __init__(self, model_name: str = "Qwen2.5+llama.cpp") -> None:
        self.model_name = model_name

    def parse_response(self, raw: dict[str, Any], *, source_type: str) -> JudgeDecision:
        return JudgeDecision(
            decision=str(raw["decision"]),
            confidence=float(raw["confidence"]),
            request_id=str(raw["request_id"]),
            model_name=str(raw.get("model_name") or self.model_name),
            timestamp=str(raw.get("timestamp") or _utc_now_iso()),
            source_type=source_type,
        )

    def call(
        self,
        *,
        invoke_fn: Callable[[], dict[str, Any]],
        source_type: str,
    ) -> JudgeDecision | dict[str, Any]:
        try:
            raw = invoke_fn()
            return self.parse_response(raw, source_type=source_type)
        except TimeoutError:
            return {"judge_applied": False, "fallback_reason": "timeout_fallback"}
        except Exception:
            return {"judge_applied": False, "fallback_reason": "model_unavailable"}


class ArbiterGovernanceGuard:
    """Governance gate for ratio/latency/cost/real-call checks."""

    def evaluate(self, *, metrics: dict[str, float], limits: dict[str, float]) -> dict[str, Any]:
        violations: list[str] = []
        if metrics.get("llm_final_judged_ratio", 0.0) < limits.get("llm_final_judged_ratio_min", 0.95):
            violations.append("ratio")
        if metrics.get("arbiter_p95_latency", 10_000.0) >= limits.get("arbiter_p95_latency_limit_ms", 800.0):
            violations.append("latency")
        if metrics.get("arbiter_cost_per_1k", 10_000.0) > limits.get("arbiter_cost_per_1k_limit", 1.0):
            violations.append("cost")
        if metrics.get("real_call_ratio", 0.0) < limits.get("real_call_ratio_min", 1.0):
            violations.append("real_call_ratio")

        gate_pass = len(violations) == 0
        return {
            "gate_pass": gate_pass,
            "violations": violations,
            "degrade_action": None if gate_pass else "fallback_stage1_and_alert",
            "manual_review_rate": float(metrics.get("manual_review_rate", 0.0)),
        }


class FinalJudgeEvidenceCollector:
    """Collects final judge report and evidence index."""

    def build_report(
        self,
        *,
        decisions: list[dict[str, Any]],
        latencies_ms: list[int],
        costs_per_1k: list[float],
        misjudge_root_cause: dict[str, int],
    ) -> dict[str, Any]:
        judged = [d for d in decisions if d.get("reviewed") is True]
        matched = [d for d in decisions if d.get("classification_matched") is True]
        adopted = [d for d in judged if d.get("judge_source") == "final_judge" and d.get("adopted") is True]
        judge_full_review_ratio = (len(judged) / len(matched)) if matched else 0.0
        llm_final_judged_ratio = (len(adopted) / len(judged)) if judged else 0.0
        evidence_index = [
            {
                "trace_id": d.get("trace_id", ""),
                "decision_id": d.get("decision_id", ""),
                "request_id": d.get("request_id", ""),
            }
            for d in decisions
        ]
        p95 = sorted(latencies_ms)[max(0, int(len(latencies_ms) * 0.95) - 1)] if latencies_ms else 0
        return {
            "precision": float(mean([1.0 if d.get("adopted") else 0.0 for d in judged])) if judged else 0.0,
            "latency": {"p95_ms": p95, "avg_ms": float(mean(latencies_ms)) if latencies_ms else 0.0},
            "cost": {"avg_cost_per_1k": float(mean(costs_per_1k)) if costs_per_1k else 0.0},
            "misjudge_root_cause": misjudge_root_cause,
            "judge_full_review_ratio": judge_full_review_ratio,
            "llm_final_judged_ratio": llm_final_judged_ratio,
            "evidence_index": evidence_index,
        }

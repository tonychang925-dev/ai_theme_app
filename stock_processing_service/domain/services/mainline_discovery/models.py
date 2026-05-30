"""Mainline Discovery DTO models — Phase 1.

These dataclasses define the output protocol for the mainline discovery
subsystem. A `to_dict()` method is provided on each model so that consumers
(tests, engines, API endpoints) can work with plain dicts without coupling to
the dataclass implementation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 1. MainlineEvent — a single event linked to a subject
# ---------------------------------------------------------------------------

@dataclass
class MainlineEvent:
    event_id: str
    occurred_at: str | None = None
    title: str = ""
    summary: str | None = None
    event_type: str = "unknown"
    impact_score: float | None = None
    confidence: float | None = None
    source_channel: str = "unknown"
    subject_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "occurred_at": self.occurred_at,
            "title": self.title,
            "summary": self.summary,
            "event_type": self.event_type,
            "impact_score": self.impact_score,
            "confidence": self.confidence,
            "source_channel": self.source_channel,
            "subject_key": self.subject_key,
        }


# ---------------------------------------------------------------------------
# 2. MainlineEventSeries — aggregated event series for a subject
# ---------------------------------------------------------------------------

@dataclass
class MainlineEventSeries:
    series_id: str
    series_type: str = "unknown"
    event_count: int = 0
    active_days_7d: int = 0
    first_seen: str | None = None
    last_seen: str | None = None
    key_events: list[dict[str, Any]] = field(default_factory=list)
    logic_summary: str = ""
    consistency_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "series_id": self.series_id,
            "series_type": self.series_type,
            "event_count": self.event_count,
            "active_days_7d": self.active_days_7d,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "key_events": self.key_events,
            "logic_summary": self.logic_summary,
            "consistency_score": self.consistency_score,
        }


# ---------------------------------------------------------------------------
# 3. MainlineLogicEvidence — logic-side evidence for a subject
# ---------------------------------------------------------------------------

@dataclass
class MainlineLogicEvidence:
    logic_score: float | None = None
    event_impact_score: float | None = None
    event_continuity_score: float | None = None
    narrative_consistency_score: float | None = None
    novelty_score: float | None = None
    event_chain: list[dict[str, Any]] = field(default_factory=list)
    event_series: list[dict[str, Any]] = field(default_factory=list)
    logic_summary: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "logic_score": self.logic_score,
            "event_impact_score": self.event_impact_score,
            "event_continuity_score": self.event_continuity_score,
            "narrative_consistency_score": self.narrative_consistency_score,
            "novelty_score": self.novelty_score,
            "event_chain": self.event_chain,
            "event_series": self.event_series,
            "logic_summary": self.logic_summary,
            "diagnostics": self.diagnostics,
        }


# ---------------------------------------------------------------------------
# 4. MainlineMarketAcceptance — market-side evidence for a subject
# ---------------------------------------------------------------------------

@dataclass
class MainlineMarketAcceptance:
    market_acceptance_score: float | None = None
    heat_persistence_score: float | None = None
    relative_strength_score: float | None = None
    board_breadth_score: float | None = None
    leader_strength_score: float | None = None
    capital_confirmation_score: float | None = None
    lifecycle_health_score: float | None = None
    resilience_repair_score: float | None = None
    leader_alive: bool = False
    market_evidence: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    # P1 fix: scoped vetoes — blocking vs confirmation-only
    blocking_veto_flags: list[str] = field(default_factory=list)
    confirmation_veto_flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_acceptance_score": self.market_acceptance_score,
            "heat_persistence_score": self.heat_persistence_score,
            "relative_strength_score": self.relative_strength_score,
            "leader_strength_score": self.leader_strength_score,
            "board_breadth_score": self.board_breadth_score,
            "capital_confirmation_score": self.capital_confirmation_score,
            "lifecycle_health_score": self.lifecycle_health_score,
            "resilience_repair_score": self.resilience_repair_score,
            "leader_alive": self.leader_alive,
            "market_evidence": self.market_evidence,
            "diagnostics": self.diagnostics,
            "blocking_veto_flags": self.blocking_veto_flags,
            "confirmation_veto_flags": self.confirmation_veto_flags,
        }


# ---------------------------------------------------------------------------
# 5. MainlineSubjectBinding — ties a subject to a mainline
# ---------------------------------------------------------------------------

@dataclass
class MainlineSubjectBinding:
    subject_key: str
    theme_name: str = ""
    role: str = "core"  # core / branch / related / noise
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "theme_name": self.theme_name,
            "role": self.role,
            "confidence": self.confidence,
        }


# ---------------------------------------------------------------------------
# 6. MainlineDiscoveryReview — the top-level output per confirmed candidate
# ---------------------------------------------------------------------------

@dataclass
class MainlineDiscoveryReview:
    trade_date: str = ""
    mainline_id: str = ""
    mainline_name: str = ""
    confirmation_state: str = "rejected"   # confirmed_mainline / mainline_watch / logic_only / market_noise / rotation_hotspot / fading_mainline / rejected

    logic_score: float | None = None
    market_acceptance_score: float | None = None
    continuity_score: float | None = None
    mainline_score: float | None = None

    core_subject_keys: list[str] = field(default_factory=list)
    branch_subject_keys: list[str] = field(default_factory=list)
    noise_subject_keys: list[str] = field(default_factory=list)

    event_chain: list[dict[str, Any]] = field(default_factory=list)
    event_series: list[dict[str, Any]] = field(default_factory=list)

    logic_evidence: dict[str, Any] = field(default_factory=dict)
    market_acceptance: dict[str, Any] = field(default_factory=dict)
    subject_bindings: list[dict[str, Any]] = field(default_factory=list)

    decision_implication: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "mainline_id": self.mainline_id,
            "mainline_name": self.mainline_name,
            "confirmation_state": self.confirmation_state,
            "logic_score": self.logic_score,
            "market_acceptance_score": self.market_acceptance_score,
            "continuity_score": self.continuity_score,
            "mainline_score": self.mainline_score,
            "core_subject_keys": self.core_subject_keys,
            "branch_subject_keys": self.branch_subject_keys,
            "noise_subject_keys": self.noise_subject_keys,
            "event_chain": self.event_chain,
            "event_series": self.event_series,
            "logic_evidence": self.logic_evidence,
            "market_acceptance": self.market_acceptance,
            "subject_bindings": self.subject_bindings,
            "decision_implication": self.decision_implication,
            "diagnostics": self.diagnostics,
        }


# ---------------------------------------------------------------------------
# 7. MainlineDiscoveryDiagnostics — aggregate diagnostics for a trading day
# ---------------------------------------------------------------------------

@dataclass
class MainlineDiscoveryDiagnostics:
    candidate_subject_count: int = 0
    event_context_subject_count: int = 0
    market_acceptance_subject_count: int = 0
    confirmed_mainline_count: int = 0
    mainline_watch_count: int = 0
    logic_only_count: int = 0
    market_noise_count: int = 0
    rotation_hotspot_count: int = 0
    rejected_count: int = 0
    fading_mainline_count: int = 0
    fallback_used: list[str] = field(default_factory=list)
    data_quality: str = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_subject_count": self.candidate_subject_count,
            "event_context_subject_count": self.event_context_subject_count,
            "market_acceptance_subject_count": self.market_acceptance_subject_count,
            "confirmed_mainline_count": self.confirmed_mainline_count,
            "mainline_watch_count": self.mainline_watch_count,
            "logic_only_count": self.logic_only_count,
            "market_noise_count": self.market_noise_count,
            "rotation_hotspot_count": self.rotation_hotspot_count,
            "rejected_count": self.rejected_count,
            "fading_mainline_count": self.fading_mainline_count,
            "fallback_used": self.fallback_used,
            "data_quality": self.data_quality,
        }


@dataclass
class NarrativeJudgeResult:
    """LLM narrative arbitration result — PR-4B."""
    is_mainline_logic: bool = False
    narrative_score: float | None = None
    narrative_level: str = "insufficient"
    logic_type: str = "unknown"
    impact_scope: str = "unknown"
    time_horizon: str = "unknown"
    narrative_consistency_score: float | None = None
    novelty_score: float | None = None
    event_continuity_assessment: str = "insufficient"
    supporting_event_ids: list[str] = field(default_factory=list)
    negative_reasons: list[str] = field(default_factory=list)
    logic_summary: str = ""
    confidence: float = 0.0
    method: str = "llm_narrative_judge_v1"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_mainline_logic": self.is_mainline_logic,
            "narrative_score": self.narrative_score,
            "narrative_level": self.narrative_level,
            "logic_type": self.logic_type,
            "impact_scope": self.impact_scope,
            "time_horizon": self.time_horizon,
            "narrative_consistency_score": self.narrative_consistency_score,
            "novelty_score": self.novelty_score,
            "event_continuity_assessment": self.event_continuity_assessment,
            "supporting_event_ids": self.supporting_event_ids,
            "negative_reasons": self.negative_reasons,
            "logic_summary": self.logic_summary,
            "confidence": self.confidence,
            "method": self.method,
            "diagnostics": self.diagnostics,
        }


@dataclass
class MainlineDiscoveryDecision:
    """PR-5: Combined decision output from MainlineDiscoveryEngine."""
    subject_key: str = ""
    theme_name: str = ""

    machine_state: str = "rejected"
    final_mainline_state: str = "rejected"

    mainline_type: str = "unknown"
    confirmation_path: str = "unknown"
    trigger_mode: str = "unknown"

    human_review_required: bool = False
    human_review_status: str = "none"
    review_reason: str = ""
    suggested_human_decision: str = "watch"

    rule_logic_score: float | None = None
    llm_narrative_score: float | None = None
    hybrid_logic_score: float | None = None
    market_acceptance_score: float | None = None
    major_event_score: float | None = None

    fast_line_score: float | None = None
    slow_line_score: float | None = None

    blocking_veto_flags: list[str] = field(default_factory=list)
    confirmation_veto_flags: list[str] = field(default_factory=list)

    logic_score_method: str = "unknown"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "theme_name": self.theme_name,
            "machine_state": self.machine_state,
            "final_mainline_state": self.final_mainline_state,
            "mainline_type": self.mainline_type,
            "confirmation_path": self.confirmation_path,
            "trigger_mode": self.trigger_mode,
            "human_review_required": self.human_review_required,
            "human_review_status": self.human_review_status,
            "review_reason": self.review_reason,
            "suggested_human_decision": self.suggested_human_decision,
            "rule_logic_score": self.rule_logic_score,
            "llm_narrative_score": self.llm_narrative_score,
            "hybrid_logic_score": self.hybrid_logic_score,
            "market_acceptance_score": self.market_acceptance_score,
            "major_event_score": self.major_event_score,
            "fast_line_score": self.fast_line_score,
            "slow_line_score": self.slow_line_score,
            "blocking_veto_flags": self.blocking_veto_flags,
            "confirmation_veto_flags": self.confirmation_veto_flags,
            "logic_score_method": self.logic_score_method,
            "diagnostics": self.diagnostics,
        }


# ---------------------------------------------------------------------------
# 9. AnalystReviewItem — human review queue entry (PR-6)
# ---------------------------------------------------------------------------

@dataclass
class AnalystReviewItem:
    review_id: str = ""
    trade_date: str = ""

    subject_key: str = ""
    theme_name: str = ""

    mainline_id: str = ""
    mainline_name: str = ""

    machine_state: str = ""
    final_mainline_state: str = "pending_review"

    mainline_type: str = "unknown"
    confirmation_path: str = "unknown"
    trigger_mode: str = ""

    review_reason: str = ""
    review_priority: float = 0.0
    review_status: str = "pending"

    suggested_human_decision: str = "watch"

    scores: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    risk_flags: dict[str, Any] = field(default_factory=dict)

    human_decision: str | None = None
    human_reviewer: str | None = None
    human_notes: str | None = None
    reviewed_at: str | None = None

    created_at: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "trade_date": self.trade_date,
            "subject_key": self.subject_key,
            "theme_name": self.theme_name,
            "mainline_id": self.mainline_id,
            "mainline_name": self.mainline_name,
            "machine_state": self.machine_state,
            "final_mainline_state": self.final_mainline_state,
            "mainline_type": self.mainline_type,
            "confirmation_path": self.confirmation_path,
            "trigger_mode": self.trigger_mode,
            "review_reason": self.review_reason,
            "review_priority": self.review_priority,
            "review_status": self.review_status,
            "suggested_human_decision": self.suggested_human_decision,
            "scores": self.scores,
            "evidence": self.evidence,
            "risk_flags": self.risk_flags,
            "human_decision": self.human_decision,
            "human_reviewer": self.human_reviewer,
            "human_notes": self.human_notes,
            "reviewed_at": self.reviewed_at,
            "created_at": self.created_at,
            "diagnostics": self.diagnostics,
        }


@dataclass
class AnalystReviewQueueDiagnostics:
    total_candidates: int = 0
    fast_line_count: int = 0
    slow_line_count: int = 0
    high_market_noise_count: int = 0
    high_logic_only_count: int = 0
    grey_zone_count: int = 0
    rejected_count: int = 0
    queue_total: int = 0
    max_priority: float = 0.0
    min_priority: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "fast_line_count": self.fast_line_count,
            "slow_line_count": self.slow_line_count,
            "high_market_noise_count": self.high_market_noise_count,
            "high_logic_only_count": self.high_logic_only_count,
            "grey_zone_count": self.grey_zone_count,
            "rejected_count": self.rejected_count,
            "queue_total": self.queue_total,
            "max_priority": self.max_priority,
            "min_priority": self.min_priority,
        }

"""Phase B — World State Transition Compiler intermediate objects.

B0: Inference → Candidate → Eligibility → Frozen

  Inference  — Raw transition signal from StateDiff + CycleNode
  Candidate  — Filtered + enriched inference ready for Eligibility Gate
  Compiled   — Frozen hypothesis (NODE_TRANSITION type only)

These three objects sit between the CognitionPipeline output (Phase A)
and the FrozenHypothesisSource (Phase 1 existing contract).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


# ──────────────────────────────────────────────
#  B0.1  WorldTransitionInference
# ──────────────────────────────────────────────

INFERENCE_TRIGGER_TYPES = (
    "node_transition",         # CycleNode changed (e.g. CLIMAX→FIRST_DIVERGENCE)
    "maturity_threshold",      # NodeMaturity crossed a threshold
    "divergence_signal",       # DivergenceQuality changed label
    "external_anchor_shift",   # External anchor changed direction
    "capital_rotation",        # Capital flow changed direction
    "expectation_surprise",    # ExpectationProjection surprise >= 2
    "historical_alignment",    # HistoricalCaseProjection Top-1 suggests transition
)


@dataclass(frozen=True, slots=True)
class WorldTransitionInference:
    """Raw inference: a state change that MIGHT warrant a hypothesis."""

    inference_id: str
    subject_id: str              # -> MarketSubject
    trade_date: date

    from_node: str               # previous CycleNode.name
    to_node: str                 # current CycleNode.name (if unchanged, same)
    trigger_type: str            # one of INFERENCE_TRIGGER_TYPES

    confidence: float            # 0-1 — how strongly the evidence supports this inference
    urgency: float               # 0-1 — how time-sensitive this inference is

    source_diff: str             # StateDiff reference
    source_cycle_node: str       # CycleNode.node_id reference
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.trigger_type not in INFERENCE_TRIGGER_TYPES:
            raise ValueError(
                f"trigger_type must be one of {INFERENCE_TRIGGER_TYPES}, "
                f"got {self.trigger_type!r}"
            )
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"confidence must be 0-1, got {self.confidence}")
        if not 0 <= self.urgency <= 1:
            raise ValueError(f"urgency must be 0-1, got {self.urgency}")


# ──────────────────────────────────────────────
#  B0.2  WorldTransitionCandidate
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class WorldTransitionCandidate:
    """Filtered inference — passed compiler policy, ready for Eligibility Gate."""

    candidate_id: str
    inference_id: str            # -> WorldTransitionInference
    subject_id: str              # -> MarketSubject
    trade_date: date

    statement: str               # e.g. "CLIMAX → FIRST_DIVERGENCE"
    current_node: str
    expected_transition: str

    prediction_probability: float  # 0-1 — from NodeMaturity or TransitionCandidate
    source_quality_score: float    # 0-1 — Evidence/Reasoning quality (not event probability)

    expected_observations: tuple[str, ...]
    falsifiers: tuple[str, ...]

    deadline: date               # from Trade Calendar Producer
    compiler_policy_version: str

    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.prediction_probability <= 1:
            raise ValueError(
                f"prediction_probability must be 0-1, got {self.prediction_probability}"
            )
        if not self.expected_observations:
            raise ValueError("expected_observations must not be empty")
        if not self.falsifiers:
            raise ValueError("falsifiers must not be empty")


# ──────────────────────────────────────────────
#  B0.3  CompiledNodeTransitionHypothesis
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class CompiledNodeTransitionHypothesis:
    """Frozen hypothesis — passed Eligibility Gate, ready for Dataset write."""

    hypothesis_type: str = "NODE_TRANSITION"

    current_node: str = ""
    expected_transition: str = ""

    source_candidate_id: str = ""  # -> WorldTransitionCandidate
    hypothesis_id: str = ""        # assigned by FrozenHypothesisSourceStore

    def is_valid(self) -> bool:
        return (
            self.hypothesis_type == "NODE_TRANSITION"
            and bool(self.current_node)
            and bool(self.expected_transition)
            and bool(self.source_candidate_id)
            and bool(self.hypothesis_id)
        )

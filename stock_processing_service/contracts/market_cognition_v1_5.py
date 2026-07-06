"""M8 v1.5 Core Contract — Cognition Projections dataclasses.

Phase 1.5 — Market World State Verification

Stable Core (9 objects, frozen):
  MarketSubject / DailyMarketState / StateDiff / PolicySnapshot
  CycleNode / DivergenceQuality / NodeMaturity
  MultiHorizonContext / PolicyRegistryEntry

Architecture Budget: no new top-level objects beyond these 9.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping

from .market_cognition import EvidenceRef, QualityEnvelope, canonical_hash


# ──────────────────────────────────────────────
#  A.2  MarketSubject — Unified Aggregate Root
# ──────────────────────────────────────────────

SUBJECT_TYPES = (
    "theme",
    "leader",
    "index",
    "external",
    "macro",
    "sector",
    "emotion_carrier",
)


@dataclass(frozen=True, slots=True)
class MarketSubject:
    """Unified Aggregate Root.

    Theme / Leader / Index / External / Macro / Sector / EmotionCarrier
    are all Subjects. Node / Context / Quality / Hypothesis reference
    subject_id, never theme_id directly.
    """

    subject_id: str
    subject_type: str  # one of SUBJECT_TYPES
    name: str
    parent_subject_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.subject_type not in SUBJECT_TYPES:
            raise ValueError(
                f"subject_type must be one of {SUBJECT_TYPES}, got {self.subject_type!r}"
            )


# ──────────────────────────────────────────────
#  A.2  DailyMarketState — Versioned Aggregate
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    """Policy versions active when this State was generated.

    Ensures replay is 100% reproducible.
    """

    cycle_fsm: str          # e.g. "cycle_fsm.v1"
    divergence: str         # e.g. "divergence_policy.v1"
    maturity: str           # e.g. "maturity_policy.v1"
    compiler: str           # e.g. "compiler_policy.v1"
    snapshot_at: datetime

    def to_dict(self) -> dict[str, str]:
        return {
            "cycle_fsm": self.cycle_fsm,
            "divergence": self.divergence,
            "maturity": self.maturity,
            "compiler": self.compiler,
        }


@dataclass(frozen=True, slots=True)
class DailyMarketState:
    """Immutable World State snapshot.

    Versioned aggregate supporting State Diff / Replay / Rollback.
    """

    state_id: str               # hash(trade_date + content_hash)
    trade_date: date
    version: int                # monotonic within this subject scope
    parent_state: str | None    # previous day's state_id (State Chain)
    created_at: datetime
    policy_snapshot: PolicySnapshot

    # ── World State contents ──
    subjects: tuple[MarketSubject, ...]
    contexts: Any | None = None              # MultiHorizonContext (lazy)
    cycle_nodes: tuple[CycleNode, ...] = ()
    divergence_qualities: tuple[DivergenceQuality, ...] = ()
    maturity_estimates: tuple[NodeMaturity, ...] = ()

    content_hash: str = ""
    evidence_refs: tuple[str, ...] = ()
    quality: QualityEnvelope | None = None

    # ── M9 Bridge — Optional, current implementation = None ──
    working_memory: None = None
    belief_state: None = None
    attention_state: None = None
    goal_state: None = None

    def compute_state_id(self) -> str:
        payload = {
            "trade_date": self.trade_date.isoformat(),
            "content_hash": self.content_hash,
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()


# ──────────────────────────────────────────────
#  A.2  StateDiff
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NodeChange:
    subject_id: str
    from_node: str | None
    to_node: str | None


@dataclass(frozen=True, slots=True)
class MaturityChange:
    subject_id: str
    from_maturity: float | None
    to_maturity: float | None
    delta: float


@dataclass(frozen=True, slots=True)
class StateDiff:
    """Structured difference between two World States."""

    from_state: str  # state_id
    to_state: str    # state_id

    subjects_added: tuple[str, ...] = ()
    subjects_removed: tuple[str, ...] = ()

    node_changes: tuple[NodeChange, ...] = ()
    maturity_changes: tuple[MaturityChange, ...] = ()
    hypothesis_results: tuple[str, ...] = ()

    summary: str = ""


# ──────────────────────────────────────────────
#  A.4  CycleNode — Node is an Object, not a String
# ──────────────────────────────────────────────

CYCLE_NODES = (
    "CHAOS",
    "INITIAL",
    "FERMENTATION",
    "ACCELERATION",
    "CLIMAX",
    "FIRST_DIVERGENCE",
    "DIVERGENCE_REPAIR",
    "WEAK_TO_STRONG",
    "SECOND_ACCELERATION",
    "SECOND_DIVERGENCE",
    "DIVERGENCE_WEAKENING",
    "FADE",
    "ICE_POINT",
    "REBOUND",
    "SECOND_WAVE",
    "CYCLE_END",
)


@dataclass(frozen=True, slots=True)
class TransitionCandidate:
    target_node: str
    probability: float           # 0-1
    required_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.probability <= 1:
            raise ValueError(f"probability must be 0-1, got {self.probability}")


@dataclass(frozen=True, slots=True)
class CycleNode:
    """Cycle node — NOT an enum, NOT a bare string. Full object."""

    node_id: str
    subject_id: str              # -> MarketSubject
    trade_date: date

    name: str                    # e.g. "CLIMAX" (from CYCLE_NODES)
    stage: str                   # 启动 / 发酵 / 加速 / 高潮 / 分歧 / 退潮
    stage_day: int               # days in current stage
    consecutive_direction: str   # accelerating / diverging / repairing / fading / neutral

    maturity: float              # 0-100 — from NodeMaturity
    confidence: float            # 0-1 — confidence in this node assignment

    transition_candidates: tuple[TransitionCandidate, ...] = ()
    quality_label: str = ""      # accelerating / peaking / exhausting / stalling

    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.name not in CYCLE_NODES:
            raise ValueError(f"name must be one of {CYCLE_NODES}, got {self.name!r}")
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"confidence must be 0-1, got {self.confidence}")
        if not 0 <= self.maturity <= 100:
            raise ValueError(f"maturity must be 0-100, got {self.maturity}")


# ──────────────────────────────────────────────
#  A.6  DivergenceQuality — Save the Vector, not the Label
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DivergenceQuality:
    """Divergence quality — saves the full 5-dimension vector.

    Label (healthy/forced/panic/insufficient) is derived by Policy, not stored as fact.
    """

    quality_id: str
    subject_id: str              # -> MarketSubject
    trade_date: date

    # ── Five dimensions — permanently persisted ──
    volume_contraction: float    # 0-1
    leader_intact: float         # 0-1
    rear_cleared: float          # 0-1
    capital_redirected: float    # 0-1
    duration_sufficient: float   # 0-1

    # ── Label — derived by Policy, recomputable ──
    quality_label: str           # healthy / forced / panic / insufficient
    policy_version: str          # version of policy that derived this label

    evidence_refs: tuple[str, ...] = ()


# ──────────────────────────────────────────────
#  A.7  NodeMaturity — Save the Vector, not the Score
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class NodeMaturity:
    """Node maturity — saves the full 6-dimension vector.

    'overall: 82' is not explainable. The full vector is.
    """

    maturity_id: str
    subject_id: str              # -> MarketSubject
    trade_date: date

    # ── Full vector — permanently persisted ──
    overall: float               # 0-100
    crowding: float              # 0-100
    volume: float                # 0-100
    leader: float                # 0-100
    emotion: float               # 0-100
    time: float                  # 0-100

    quality_label: str           # accelerating / peaking / exhausting / stalling
    policy_version: str

    estimated_days_to_threshold: float | None = None
    inflection_likelihood: float = 0.0  # 0-1

    evidence_refs: tuple[str, ...] = ()


# ──────────────────────────────────────────────
#  MultiHorizonContext (placeholder — expanded in Phase A.5)
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ThemeWindowContext:
    theme_id: str
    theme_name: str
    d1_state: str = ""
    d3_trend: str = ""
    d5_phase: str = ""
    d10_cycle_position: str = ""
    d20_mainline_status: str = ""
    consecutive_days: int = 0
    phase_day: int = 0
    available_snapshot_ids: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ExternalAnchorContext:
    anchor_id: str
    anchor_name: str
    affected_themes: tuple[str, ...] = ()
    affected_industry_chain: tuple[str, ...] = ()
    not_directly_affected: tuple[str, ...] = ()
    horizon: str = "D1"
    direction: str = "neutral"
    strength: float = 0.0
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class EarningsSeasonContext:
    theme_id: str
    stage: str = ""              # 预热 / 披露 / 兑现 / 结束
    expected_beneficiaries: tuple[str, ...] = ()
    risk_of_sell_the_news: float = 0.0
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MultiHorizonContext:
    trade_date: date
    horizons: tuple[str, ...] = ("D1", "D3", "D5", "D10", "D20")
    market_windows: tuple[Any, ...] = ()
    theme_windows: tuple[ThemeWindowContext, ...] = ()
    stock_windows: tuple[Any, ...] = ()
    external_windows: tuple[ExternalAnchorContext, ...] = ()
    earnings_windows: tuple[EarningsSeasonContext, ...] = ()
    as_of: datetime | None = None
    source_snapshot_ids: tuple[str, ...] = ()
    policy_version: str = ""

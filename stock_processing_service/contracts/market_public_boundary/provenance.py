from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .identity import MarketObjectRef, MarketReleaseIdentity
from .vocabulary import MarketGovernanceState, ProvenanceStatus


class EpistemicClass(str, Enum):
    OBSERVATION = "OBSERVATION"
    REPORTED_CLAIM = "REPORTED_CLAIM"
    DERIVED_CLAIM = "DERIVED_CLAIM"
    HYPOTHESIS = "HYPOTHESIS"
    JUDGMENT = "JUDGMENT"
    FORECAST = "FORECAST"


class ProvenanceIncompleteBehavior(str, Enum):
    REQUIRE_COMPLETE = "REQUIRE_COMPLETE"
    REPORT_INCOMPLETE = "REPORT_INCOMPLETE"


@dataclass(frozen=True, slots=True)
class ProvenanceValidationContext:
    capability_id: str
    epistemic_class: EpistemicClass
    governance_state: MarketGovernanceState
    product_id: str | None = None
    counter_evidence_state: str | None = None


class ProvenancePredicate:
    pass


@dataclass(frozen=True, slots=True)
class SourceRefsPredicate(ProvenancePredicate):
    predicate_id: str = "source_refs_non_empty"


@dataclass(frozen=True, slots=True)
class ReleaseIdentityPredicate(ProvenancePredicate):
    predicate_id: str = "market_release_identity_required"


@dataclass(frozen=True, slots=True)
class DataCutoffPredicate(ProvenancePredicate):
    epistemic_classes: tuple[EpistemicClass, ...]

    @property
    def predicate_id(self) -> str:
        return "data_cutoff_required_for_epistemic_classes"

    def __post_init__(self) -> None:
        if not self.epistemic_classes:
            raise ValueError("epistemic_classes must be non-empty")


@dataclass(frozen=True, slots=True)
class RequireProductRevisionPredicate(ProvenancePredicate):
    governance_states: tuple[MarketGovernanceState, ...]

    @property
    def predicate_id(self) -> str:
        return "product_revision_required_for_governance_states"

    def __post_init__(self) -> None:
        if not self.governance_states:
            raise ValueError("governance_states must be non-empty")


@dataclass(frozen=True, slots=True)
class RequireCounterEvidencePredicate(ProvenancePredicate):
    epistemic_classes: tuple[EpistemicClass, ...]

    @property
    def predicate_id(self) -> str:
        return "counter_evidence_required_for_epistemic_classes"

    def __post_init__(self) -> None:
        if not self.epistemic_classes:
            raise ValueError("epistemic_classes must be non-empty")


@dataclass(frozen=True, slots=True)
class MarketProvenance:
    provenance_status: ProvenanceStatus
    market_release_identity: MarketReleaseIdentity
    produced_at: datetime
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    public_object_refs: tuple[MarketObjectRef, ...]
    data_cutoff: datetime | None = None
    capability_call_ref: str | None = None
    correlation_id: str | None = None
    governance_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.provenance_status, ProvenanceStatus):
            raise ValueError("provenance_status has the wrong type")
        if not isinstance(self.market_release_identity, MarketReleaseIdentity):
            raise ValueError("market_release_identity has the wrong type")
        if not isinstance(self.produced_at, datetime):
            raise ValueError("produced_at must be a datetime")
        for field_name, values in (
            ("source_refs", self.source_refs),
            ("evidence_refs", self.evidence_refs),
            ("public_object_refs", self.public_object_refs),
        ):
            if not isinstance(values, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            if any(value is None for value in values):
                raise ValueError(f"{field_name} cannot contain missing values")


@dataclass(frozen=True, slots=True)
class MarketProvenanceProfile:
    profile_id: str
    applies_to: tuple[str, ...]
    predicates: tuple[ProvenancePredicate, ...]
    incomplete_behavior: ProvenanceIncompleteBehavior

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id.strip():
            raise ValueError("profile_id must be a non-empty string")
        if not isinstance(self.applies_to, tuple) or not self.applies_to:
            raise ValueError("applies_to must be a non-empty tuple")
        if not isinstance(self.predicates, tuple):
            raise ValueError("predicates must be a tuple")
        if not isinstance(self.incomplete_behavior, ProvenanceIncompleteBehavior):
            raise ValueError("incomplete_behavior has the wrong type")


@dataclass(frozen=True, slots=True)
class ProvenanceValidationResult:
    complete: bool
    evaluated_predicates: tuple[str, ...]
    failed_predicates: tuple[str, ...]

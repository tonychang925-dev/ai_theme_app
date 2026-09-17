"""Mechanical provenance contracts for Julia-facing Market results."""
from __future__ import annotations

from dataclasses import InitVar, dataclass, field
from enum import Enum


class MarketProvenanceStatus(str, Enum):
    COMPLETE = "PROVENANCE_COMPLETE"
    INCOMPLETE = "PROVENANCE_INCOMPLETE"


class ProvenancePredicate(str, Enum):
    MARKET_RELEASE_IDENTITY_PRESENT = "require(market_release_identity)"
    SOURCE_REFS_NON_EMPTY = "require(source_refs.non_empty)"
    PUBLIC_OBJECT_REFS_NON_EMPTY = "require(public_object_refs.non_empty)"


@dataclass(frozen=True)
class MarketReleaseIdentity:
    source_identity: str
    build_identity: str
    artifact_identity: str
    artifact_digest: str
    release_manifest_ref: str

    def __post_init__(self) -> None:
        for name in (
            "source_identity",
            "build_identity",
            "artifact_identity",
            "artifact_digest",
            "release_manifest_ref",
        ):
            if not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")


@dataclass(frozen=True)
class MarketProvenanceProfile:
    profile_id: str
    applies_to: tuple[str, ...]
    predicates: tuple[ProvenancePredicate, ...]
    incomplete_behavior: str

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("profile_id must be non-empty")
        if not self.applies_to:
            raise ValueError("applies_to must be non-empty")


def _predicate_holds(predicate: ProvenancePredicate, provenance: "MarketProvenance") -> bool:
    if predicate is ProvenancePredicate.MARKET_RELEASE_IDENTITY_PRESENT:
        return provenance.market_release_identity is not None
    if predicate is ProvenancePredicate.SOURCE_REFS_NON_EMPTY:
        return bool(provenance.source_refs)
    if predicate is ProvenancePredicate.PUBLIC_OBJECT_REFS_NON_EMPTY:
        return bool(provenance.public_object_refs)
    raise ValueError(f"unsupported provenance predicate: {predicate}")


@dataclass(frozen=True)
class MarketProvenance:
    """Provenance whose COMPLETE state is derived, never caller asserted."""

    profile: InitVar[MarketProvenanceProfile]
    produced_at: str
    market_release_identity: MarketReleaseIdentity | None = None
    data_cutoff: str | None = None
    source_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    public_object_refs: tuple[str, ...] = ()
    capability_call_ref: str | None = None
    correlation_id: str | None = None
    governance_ref: str | None = None
    provenance_status: MarketProvenanceStatus = field(init=False)

    def __post_init__(self, profile: MarketProvenanceProfile) -> None:
        if not self.produced_at:
            raise ValueError("produced_at must be non-empty")
        if (
            self.capability_call_ref is not None
            and "*" not in profile.applies_to
            and self.capability_call_ref not in profile.applies_to
        ):
            raise ValueError("provenance profile does not apply to capability")
        complete = all(_predicate_holds(predicate, self) for predicate in profile.predicates)
        object.__setattr__(
            self,
            "provenance_status",
            MarketProvenanceStatus.COMPLETE if complete else MarketProvenanceStatus.INCOMPLETE,
        )

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .identity import MarketReleaseIdentity
from .vocabulary import (
    CapabilityAvailability,
    CompatibilityState,
    OperationKind,
    ReadinessState,
    ReleaseIdentityEvidenceBasis,
    SideEffectClass,
)


class IdempotencySupport(str, Enum):
    SUPPORTED = "SUPPORTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    CONDITIONAL = "CONDITIONAL"


class MarketAuthorizationRequirement(str, Enum):
    NONE = "NONE"
    AUTHENTICATED_PRINCIPAL = "AUTHENTICATED_PRINCIPAL"
    DOMAIN_ROLE = "DOMAIN_ROLE"
    GOVERNANCE_PRINCIPAL = "GOVERNANCE_PRINCIPAL"
    CUSTOM_POLICY_REF = "CUSTOM_POLICY_REF"


@dataclass(frozen=True, slots=True)
class MarketBoundaryCapabilityContractReference:
    contract_name: str
    contract_version: str


@dataclass(frozen=True, slots=True)
class MarketCapabilityManifestEntry:
    capability_id: str
    capability_version: str
    operation_kind: OperationKind
    side_effect_class: SideEffectClass
    idempotency_support: IdempotencySupport
    market_authorization_requirement: MarketAuthorizationRequirement
    may_create_product: bool
    may_change_governed_authority: bool
    may_refresh_external_data: bool
    may_mutate_market_state: bool
    input_contract_ref: MarketBoundaryCapabilityContractReference
    output_contract_ref: MarketBoundaryCapabilityContractReference
    provenance_profile_ref: str

    def __post_init__(self) -> None:
        enum_fields = (
            ("operation_kind", OperationKind),
            ("side_effect_class", SideEffectClass),
            ("idempotency_support", IdempotencySupport),
            ("market_authorization_requirement", MarketAuthorizationRequirement),
        )
        for field_name, enum_type in enum_fields:
            if not isinstance(getattr(self, field_name), enum_type):
                raise ValueError(f"{field_name} has an unrecognized value")
        for field_name, value in (
            ("capability_id", self.capability_id),
            ("capability_version", self.capability_version),
            ("provenance_profile_ref", self.provenance_profile_ref),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        for field_name in (
            "may_create_product",
            "may_change_governed_authority",
            "may_refresh_external_data",
            "may_mutate_market_state",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise ValueError(f"{field_name} must be boolean")
        if not isinstance(self.input_contract_ref, MarketBoundaryCapabilityContractReference):
            raise ValueError("input_contract_ref has the wrong type")
        if not isinstance(self.output_contract_ref, MarketBoundaryCapabilityContractReference):
            raise ValueError("output_contract_ref has the wrong type")


@dataclass(frozen=True, slots=True)
class MarketCapabilityRuntimeObservation:
    capability_id: str
    availability_state: CapabilityAvailability
    observed_at: datetime
    diagnostics: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, str) or not self.capability_id.strip():
            raise ValueError("capability_id must be a non-empty string")
        if not isinstance(self.availability_state, CapabilityAvailability):
            raise ValueError("availability_state has the wrong type")
        if not isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be a datetime")


@dataclass(frozen=True, slots=True)
class MarketRuntimeObservation:
    runtime_instance_id: str
    attested_release_identity: MarketReleaseIdentity
    release_identity_evidence_basis: tuple[ReleaseIdentityEvidenceBasis, ...]
    readiness_state: ReadinessState
    compatibility_state: CompatibilityState
    capability_runtime_observations: tuple[MarketCapabilityRuntimeObservation, ...]
    observed_at: datetime
    verified_release_identity: MarketReleaseIdentity | None = None
    diagnostics: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.runtime_instance_id, str) or not self.runtime_instance_id.strip():
            raise ValueError("runtime_instance_id must be a non-empty string")
        if not isinstance(self.attested_release_identity, MarketReleaseIdentity):
            raise ValueError("attested_release_identity has the wrong type")
        if self.verified_release_identity is not None and not isinstance(
            self.verified_release_identity, MarketReleaseIdentity
        ):
            raise ValueError("verified_release_identity has the wrong type")
        if not self.release_identity_evidence_basis:
            raise ValueError("release_identity_evidence_basis must be non-empty")
        for evidence_basis in self.release_identity_evidence_basis:
            if not isinstance(evidence_basis, ReleaseIdentityEvidenceBasis):
                raise ValueError("release_identity_evidence_basis contains an unrecognized value")
        if not isinstance(self.readiness_state, ReadinessState):
            raise ValueError("readiness_state has the wrong type")
        if not isinstance(self.compatibility_state, CompatibilityState):
            raise ValueError("compatibility_state has the wrong type")
        if not isinstance(self.observed_at, datetime):
            raise ValueError("observed_at must be a datetime")
        for observation in self.capability_runtime_observations:
            if not isinstance(observation, MarketCapabilityRuntimeObservation):
                raise ValueError("capability_runtime_observations contains an invalid entry")

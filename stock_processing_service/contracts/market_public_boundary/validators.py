from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .capabilities import MarketCapabilityManifestEntry, MarketRuntimeObservation, OperationKind, SideEffectClass
from .failures import MarketContractMismatch, MarketReleaseMismatch
from .identity import MarketBoundaryIdentity
from .provenance import (
    DataCutoffPredicate,
    MarketProvenance,
    MarketProvenanceProfile,
    ProvenanceValidationContext,
    ProvenanceValidationResult,
    ReleaseIdentityPredicate,
    RequireCounterEvidencePredicate,
    RequireProductRevisionPredicate,
    SourceRefsPredicate,
)
from .runtime import ReleaseIdentityEvidenceBasis


@dataclass(frozen=True, slots=True)
class ManifestValidationResult:
    valid: bool
    failures: tuple[MarketContractMismatch, ...]


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    valid: bool
    failures: tuple[MarketContractMismatch, ...]


@dataclass(frozen=True, slots=True)
class RuntimeObservationValidationResult:
    valid: bool
    failures: tuple[MarketReleaseMismatch, ...]


def _mismatch(message: str, details: Iterable[tuple[str, object]] = ()) -> MarketContractMismatch:
    return MarketContractMismatch(message, tuple(details))


def validate_capability_manifest(
    entry: MarketCapabilityManifestEntry,
) -> ManifestValidationResult:
    failures: list[MarketContractMismatch] = []
    mutating_fields = {
        "may_create_product": entry.may_create_product,
        "may_change_governed_authority": entry.may_change_governed_authority,
        "may_refresh_external_data": entry.may_refresh_external_data,
        "may_mutate_market_state": entry.may_mutate_market_state,
    }

    if entry.operation_kind in (OperationKind.READ, OperationKind.ANALYTICAL_INTERROGATION):
        for field_name, enabled in mutating_fields.items():
            if enabled:
                failures.append(
                    _mismatch(
                        f"{entry.operation_kind.value} cannot declare {field_name}",
                        (("capability_id", entry.capability_id), ("field", field_name)),
                    )
                )
        if entry.side_effect_class is not SideEffectClass.READ_ONLY:
            failures.append(
                _mismatch(
                    f"{entry.operation_kind.value} requires READ_ONLY semantics",
                    (("capability_id", entry.capability_id),),
                )
            )

    if entry.side_effect_class is SideEffectClass.READ_ONLY:
        for field_name in (
            "may_create_product",
            "may_change_governed_authority",
            "may_refresh_external_data",
            "may_mutate_market_state",
        ):
            if getattr(entry, field_name):
                failures.append(
                    _mismatch(
                        f"READ_ONLY cannot declare {field_name}",
                        (("capability_id", entry.capability_id), ("field", field_name)),
                    )
                )

    if entry.may_refresh_external_data and entry.operation_kind is not OperationKind.DATA_REFRESH:
        failures.append(
            _mismatch(
                "external refresh requires DATA_REFRESH",
                (("capability_id", entry.capability_id), ("operation_kind", entry.operation_kind)),
            )
        )
    return ManifestValidationResult(not failures, tuple(failures))


def validate_boundary_reconciliation(
    boundary_identity: MarketBoundaryIdentity,
    manifests: tuple[MarketCapabilityManifestEntry, ...],
) -> ReconciliationResult:
    failures: list[MarketContractMismatch] = []
    declared = boundary_identity.supported_capabilities
    manifest_ids = [manifest.capability_id for manifest in manifests]
    declared_ids = [capability_id for capability_id in declared]

    duplicate_declared = {value for value in declared_ids if declared_ids.count(value) > 1}
    for capability_id in sorted(duplicate_declared):
        failures.append(_mismatch("duplicate boundary capability declaration", (("capability_id", capability_id),)))

    duplicate_manifests = {value for value in manifest_ids if manifest_ids.count(value) > 1}
    for capability_id in sorted(duplicate_manifests):
        failures.append(_mismatch("duplicate manifest capability identity", (("capability_id", capability_id),)))

    version_groups: dict[str, list[str]] = {}
    for manifest in manifests:
        version_groups.setdefault(manifest.capability_id, []).append(manifest.capability_version)
    for capability_id, versions in version_groups.items():
        if len(set(versions)) > 1:
            failures.append(
                _mismatch(
                    "ambiguous manifest capability identity",
                    (("capability_id", capability_id), ("versions", tuple(sorted(set(versions))))),
                )
            )

    for capability_id in sorted(set(declared_ids) - set(manifest_ids)):
        failures.append(_mismatch("boundary capability missing manifest", (("capability_id", capability_id),)))
    for capability_id in sorted(set(manifest_ids) - set(declared_ids)):
        failures.append(_mismatch("manifest capability not declared by boundary", (("capability_id", capability_id),)))

    return ReconciliationResult(not failures, tuple(failures))


def validate_runtime_observation(
    observation: MarketRuntimeObservation,
) -> RuntimeObservationValidationResult:
    failures: list[MarketContractMismatch] = []
    evidence = set(observation.release_identity_evidence_basis)
    verifying_evidence = evidence - {
        ReleaseIdentityEvidenceBasis.PROVIDER_ATTESTED,
        ReleaseIdentityEvidenceBasis.UNKNOWN,
    }
    if observation.verified_release_identity is not None and not verifying_evidence:
        failures.append(
            MarketReleaseMismatch(
                "verified release identity requires verification evidence",
                (("runtime_instance_id", observation.runtime_instance_id),),
            )
        )
    return RuntimeObservationValidationResult(not failures, tuple(failures))


def _evaluate_predicate(predicate, provenance: MarketProvenance, context: ProvenanceValidationContext) -> bool:
    if isinstance(predicate, SourceRefsPredicate):
        return bool(provenance.source_refs)
    if isinstance(predicate, ReleaseIdentityPredicate):
        return provenance.market_release_identity is not None
    if isinstance(predicate, DataCutoffPredicate):
        return context.epistemic_class not in predicate.epistemic_classes or provenance.data_cutoff is not None
    if isinstance(predicate, RequireProductRevisionPredicate):
        if context.governance_state not in predicate.governance_states:
            return True
        return (
            context.product_id is not None
            and any(
                obj.object_type == "product" and obj.revision_id is not None
                for obj in provenance.public_object_refs
            )
        )
    if isinstance(predicate, RequireCounterEvidencePredicate):
        return context.epistemic_class not in predicate.epistemic_classes or context.counter_evidence_state is not None
    return False


def validate_provenance_profile(
    profile: MarketProvenanceProfile,
    provenance: MarketProvenance,
    context: ProvenanceValidationContext,
) -> ProvenanceValidationResult:
    if context.capability_id not in profile.applies_to:
        return ProvenanceValidationResult(False, (), ("profile_applies_to",))
    evaluated: list[str] = []
    failed: list[str] = []
    for predicate in profile.predicates:
        evaluated.append(predicate.predicate_id)
        if not _evaluate_predicate(predicate, provenance, context):
            failed.append(predicate.predicate_id)
    return ProvenanceValidationResult(not failed, tuple(evaluated), tuple(failed))

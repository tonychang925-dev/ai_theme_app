from __future__ import annotations

import subprocess
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from stock_processing_service.contracts.market_public_boundary import (
    CapabilityAvailability,
    CompatibilityState,
    DataCutoffPredicate,
    DataState,
    EpistemicClass,
    IdempotencySupport,
    MarketAnalysisFailed,
    MarketAnalysisPartial,
    MarketAnalysisPending,
    MarketAnalysisStale,
    MarketAuthorizationDenied,
    MarketAuthorizationRequirement,
    MarketBoundaryFailure,
    MarketBoundaryCapabilityContractReference,
    MarketBoundaryIdentity,
    MarketCapabilityManifestEntry,
    MarketCapabilityRuntimeObservation,
    MarketContractMismatch,
    MarketEvidenceUnavailable,
    MarketGovernanceFailure,
    MarketGovernanceState,
    MarketInternalFailure,
    MarketNotReady,
    MarketObjectNotFound,
    MarketObjectRef,
    MarketProvenance,
    MarketProvenanceIncomplete,
    MarketProvenanceProfile,
    MarketReleaseIdentity,
    MarketReleaseMismatch,
    MarketResultEnvelope,
    MarketRuntimeObservation,
    MarketTimeout,
    MarketUnavailable,
    OperationKind,
    OperationStatus,
    ProvenanceIncompleteBehavior,
    ProvenanceStatus,
    ProvenanceValidationContext,
    ReadinessState,
    ReleaseIdentityEvidenceBasis,
    ReleaseIdentityPredicate,
    RequireCounterEvidencePredicate,
    RequireProductRevisionPredicate,
    SideEffectClass,
    SourceRefsPredicate,
    serialize,
    validate_boundary_reconciliation,
    validate_capability_manifest,
    validate_provenance_profile,
    validate_runtime_observation,
)


NOW = datetime(2026, 9, 11, 8, 0, tzinfo=timezone.utc)
BASE_SHA = "aeb3e43378843533625c9d7de64796146c0cfd96"
ACCEPTED_SHA = "7a0c42fc31f66a945760140ba0382d79102f1c1f"


def release() -> MarketReleaseIdentity:
    return MarketReleaseIdentity(
        source_identity="source:1",
        build_identity="build:1",
        artifact_identity="artifact:1",
        artifact_digest="sha256:1",
        release_manifest_ref="manifest:1",
    )


def boundary(capabilities: tuple[str, ...] = ("capability.read",)) -> MarketBoundaryIdentity:
    return MarketBoundaryIdentity(
        provider_id="provider",
        public_contract_name="market-public-boundary",
        public_contract_version="1.0",
        release_identity=release(),
        supported_capabilities=capabilities,
        supported_object_types=("market.object",),
    )


def provenance(status: ProvenanceStatus = ProvenanceStatus.PROVENANCE_COMPLETE) -> MarketProvenance:
    return MarketProvenance(
        provenance_status=status,
        market_release_identity=release(),
        produced_at=NOW,
        source_refs=("source:1",),
        evidence_refs=("evidence:1",),
        public_object_refs=(MarketObjectRef("market.object", 1234),),
    )


def manifest(**overrides) -> MarketCapabilityManifestEntry:
    values = {
        "capability_id": "capability.read",
        "capability_version": "1.0",
        "operation_kind": OperationKind.READ,
        "side_effect_class": SideEffectClass.READ_ONLY,
        "idempotency_support": IdempotencySupport.SUPPORTED,
        "market_authorization_requirement": MarketAuthorizationRequirement.NONE,
        "may_create_product": False,
        "may_change_governed_authority": False,
        "may_refresh_external_data": False,
        "may_mutate_market_state": False,
        "input_contract_ref": MarketBoundaryCapabilityContractReference("input", "1.0"),
        "output_contract_ref": MarketBoundaryCapabilityContractReference("output", "1.0"),
        "provenance_profile_ref": "profile:standard",
    }
    values.update(overrides)
    return MarketCapabilityManifestEntry(**values)


def runtime(verified: MarketReleaseIdentity | None = None) -> MarketRuntimeObservation:
    return MarketRuntimeObservation(
        runtime_instance_id="runtime:1",
        attested_release_identity=release(),
        verified_release_identity=release() if verified is None else verified,
        release_identity_evidence_basis=(
            ReleaseIdentityEvidenceBasis.ARTIFACT_DIGEST_VERIFIED,
        ),
        readiness_state=ReadinessState.READY,
        compatibility_state=CompatibilityState.COMPATIBLE,
        capability_runtime_observations=(
            MarketCapabilityRuntimeObservation("capability.read", CapabilityAvailability.AVAILABLE, NOW),
        ),
        observed_at=NOW,
    )


def envelope(
    operation_status: OperationStatus = OperationStatus.SUCCESS,
    data_state: DataState = DataState.READY,
    failures: tuple[MarketBoundaryFailure, ...] = (),
) -> MarketResultEnvelope:
    return MarketResultEnvelope(
        contract_version="1.0",
        capability_id="capability.read",
        correlation_id="correlation:1",
        operation_status=operation_status,
        data_state=data_state,
        payload={"value": 1},
        provenance=provenance(),
        failures=failures,
        boundary_identity_ref=boundary(),
        runtime_observation=runtime(),
        produced_at=NOW,
    )


def test_g1_at01_deterministic_construction_and_serialization():
    assert serialize(envelope()) == serialize(envelope())
    assert serialize(boundary()) == serialize(boundary())


@pytest.mark.parametrize(
    ("operation_status", "data_state"),
    [
        (OperationStatus.SUCCESS, DataState.READY),
        (OperationStatus.SUCCESS, DataState.EMPTY),
        (OperationStatus.SUCCESS, DataState.STALE),
        (OperationStatus.SUCCESS, DataState.PENDING),
        (OperationStatus.PARTIAL, DataState.READY),
        (OperationStatus.FAILURE, DataState.UNAVAILABLE),
    ],
)
def test_g1_at02_operation_and_data_states_are_orthogonal(operation_status, data_state):
    result = envelope(operation_status, data_state)
    assert result.operation_status is operation_status
    assert result.data_state is data_state
    representation = json.loads(serialize(result))
    assert "status" not in representation
    assert representation["operation_status"] == operation_status.value
    assert representation["data_state"] == data_state.value


@pytest.mark.parametrize(
    ("operation_status", "data_state"),
    [
        ("FAILURE", "EMPTY"),
        ("SUCCESS", "ARBITRARY"),
        ("ARBITRARY", "READY"),
    ],
)
def test_g1_at02_raw_state_values_cannot_bypass_enforcement(operation_status, data_state):
    with pytest.raises(ValueError):
        envelope(operation_status, data_state)


def test_g1_at03_governance_state_is_independent():
    assert MarketGovernanceState.PUBLISHED is not DataState.STALE
    assert DataState.STALE.value == "STALE"
    assert MarketGovernanceState.PUBLISHED.value == "PUBLISHED"
    assert "governance_state" not in serialize(runtime())
    with pytest.raises(ValueError, match="EMPTY"):
        envelope(OperationStatus.FAILURE, DataState.EMPTY)


@pytest.mark.parametrize(
    "field_name",
    [
        "may_create_product",
        "may_change_governed_authority",
        "may_refresh_external_data",
        "may_mutate_market_state",
    ],
)
def test_g1_at04_manifest_contradictions_fail_closed(field_name):
    result = validate_capability_manifest(manifest(**{field_name: True}))
    assert not result.valid
    assert result.failures
    assert all(isinstance(failure, MarketContractMismatch) for failure in result.failures)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("operation_kind", "ARBITRARY"),
        ("side_effect_class", "ARBITRARY"),
        ("idempotency_support", "ARBITRARY"),
    ],
)
def test_g1_at04_arbitrary_manifest_vocabularies_fail_closed(field_name, value):
    with pytest.raises(ValueError, match="unrecognized"):
        manifest(**{field_name: value})


@pytest.mark.parametrize(
    "field_name",
    ["may_refresh_external_data", "may_create_product"],
)
def test_g1_at04_read_only_rejects_all_declared_effects(field_name):
    result = validate_capability_manifest(manifest(**{field_name: True}))
    assert not result.valid
    assert isinstance(result.failures[0], MarketContractMismatch)


def test_g1_at05_stable_manifest_has_no_runtime_availability():
    manifest_entry = manifest()
    assert "availability_state" not in serialize(manifest_entry)
    assert "requires_authorization" not in serialize(manifest_entry)
    assert isinstance(manifest_entry.market_authorization_requirement, MarketAuthorizationRequirement)


def test_g1_at06_attested_and_verified_identity_channels_are_distinct():
    observation = runtime()
    assert observation.attested_release_identity == observation.verified_release_identity
    assert validate_runtime_observation(observation).valid
    with pytest.raises(ValueError, match="verified_release_identity"):
        runtime(verified="not-a-release-identity")


@pytest.mark.parametrize(
    "evidence_basis",
    [
        ReleaseIdentityEvidenceBasis.PROVIDER_ATTESTED,
        ReleaseIdentityEvidenceBasis.UNKNOWN,
    ],
)
def test_g1_at07_provider_attestation_alone_cannot_verify_identity(evidence_basis):
    observation = MarketRuntimeObservation(
        runtime_instance_id="runtime:2",
        attested_release_identity=release(),
        verified_release_identity=runtime().verified_release_identity,
        release_identity_evidence_basis=(evidence_basis,),
        readiness_state=ReadinessState.READY,
        compatibility_state=CompatibilityState.COMPATIBLE,
        capability_runtime_observations=(),
        observed_at=NOW,
    )
    result = validate_runtime_observation(observation)
    assert not result.valid
    assert isinstance(result.failures[0], MarketReleaseMismatch)

    with pytest.raises(ValueError, match="unrecognized"):
        MarketRuntimeObservation(
            runtime_instance_id="runtime:3",
            attested_release_identity=release(),
            verified_release_identity=runtime().verified_release_identity,
            release_identity_evidence_basis=("ARBITRARY_STRING",),
            readiness_state=ReadinessState.READY,
            compatibility_state=CompatibilityState.COMPATIBLE,
            capability_runtime_observations=(),
            observed_at=NOW,
        )


def test_g1_at08_provenance_completeness_is_validator_derived():
    profile = MarketProvenanceProfile(
        profile_id="profile:standard",
        applies_to=("capability.analysis",),
        predicates=(
            SourceRefsPredicate(),
            ReleaseIdentityPredicate(),
            DataCutoffPredicate((EpistemicClass.FORECAST,)),
            RequireProductRevisionPredicate(
                (MarketGovernanceState.APPROVED, MarketGovernanceState.PUBLISHED)
            ),
            RequireCounterEvidencePredicate((EpistemicClass.JUDGMENT, EpistemicClass.FORECAST)),
        ),
        incomplete_behavior=ProvenanceIncompleteBehavior.REQUIRE_COMPLETE,
    )
    context = ProvenanceValidationContext(
        capability_id="capability.analysis",
        epistemic_class=EpistemicClass.FORECAST,
        governance_state=MarketGovernanceState.PUBLISHED,
        product_id="product:1",
        counter_evidence_state="SEARCHED",
    )
    asserted_complete = provenance()
    invalid = validate_provenance_profile(profile, asserted_complete, context)
    assert asserted_complete.provenance_status is ProvenanceStatus.PROVENANCE_COMPLETE
    assert not invalid.complete

    complete = MarketProvenance(
        provenance_status=ProvenanceStatus.PROVENANCE_INCOMPLETE,
        market_release_identity=release(),
        produced_at=NOW,
        source_refs=("source:1",),
        evidence_refs=("evidence:1",),
        public_object_refs=(MarketObjectRef("product", "product:1", "revision:1"),),
        data_cutoff=NOW,
    )
    assert validate_provenance_profile(profile, complete, context).complete


def test_g1_at09_market_authorization_does_not_waive_platform_authorization():
    assert [effect.value for effect in SideEffectClass] == [
        "READ_ONLY",
        "REVERSIBLE_WRITE",
        "IRREVERSIBLE_WRITE",
        "EXTERNAL_SIDE_EFFECT",
        "HIGH_IMPACT",
    ]
    assert [requirement.value for requirement in MarketAuthorizationRequirement] == [
        "NONE",
        "AUTHENTICATED_PRINCIPAL",
        "DOMAIN_ROLE",
        "GOVERNANCE_PRINCIPAL",
        "CUSTOM_POLICY_REF",
    ]
    manifest_entry = manifest(
        market_authorization_requirement=MarketAuthorizationRequirement.DOMAIN_ROLE
    )
    assert manifest_entry.market_authorization_requirement != "C08"
    with pytest.raises(ValueError, match="unrecognized"):
        manifest(market_authorization_requirement="C08")
    assert "requires_authorization" not in serialize(manifest_entry)
    assert validate_capability_manifest(manifest_entry).valid


def test_g1_at10_object_references_are_storage_neutral():
    object_ref = MarketObjectRef("market.object", 1234)
    representation = json.loads(serialize(object_ref))
    assert representation == {
        "__type__": "MarketObjectRef",
        "object_id": 1234,
        "object_type": "market.object",
        "revision_id": None,
    }
    uuid_value = UUID("12345678-1234-5678-1234-567812345678")
    uuid_ref = MarketObjectRef("market.object", uuid_value)
    assert json.loads(serialize(uuid_ref))["object_id"] == str(uuid_value)
    assert serialize(uuid_ref) == serialize(MarketObjectRef("market.object", str(uuid_value)))


def test_g1_at11_package_defers_transport_selection():
    package = Path(__file__).parents[2] / "contracts" / "market_public_boundary"
    source = "\n".join(path.read_text() for path in package.rglob("*.py"))
    for forbidden in ("HTTP", "RPC", "MCP", "FastAPI", "endpoint", "wire"):
        assert forbidden not in source


def test_g1_at12_no_runtime_route_behavior_changed():
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", BASE_SHA, ACCEPTED_SHA], text=True
    ).splitlines()
    production = [path for path in changed if not path.startswith("stock_processing_service/tests/")]
    assert production
    assert all(
        path.startswith("stock_processing_service/contracts/market_public_boundary/")
        for path in production
    )


def test_g1_at13_boundary_capabilities_reconcile_with_manifests():
    valid = validate_boundary_reconciliation(
        boundary(("capability.read", "capability.refresh")),
        (
            manifest(),
            manifest(
                capability_id="capability.refresh",
                operation_kind=OperationKind.DATA_REFRESH,
                side_effect_class=SideEffectClass.EXTERNAL_SIDE_EFFECT,
                may_refresh_external_data=True,
            ),
        ),
    )
    assert valid.valid

    invalid = validate_boundary_reconciliation(
        boundary(("capability.read", "capability.missing")),
        (manifest(), manifest(capability_id="capability.undeclared")),
    )
    assert not invalid.valid
    assert len(invalid.failures) == 2


def test_g1_at14_superseded_v02_fields_are_absent():
    result = envelope()
    assert not hasattr(result, "status")
    assert "status" not in json.loads(serialize(result))
    assert not hasattr(result, "availability_state")
    assert not hasattr(result, "requires_authorization")
    assert "availability_state" not in json.loads(serialize(manifest()))
    assert "requires_authorization" not in json.loads(serialize(manifest()))


def test_g1_at15_typed_failures_remain_distinguishable():
    failure_classes = (
        MarketUnavailable,
        MarketNotReady,
        MarketContractMismatch,
        MarketReleaseMismatch,
        MarketObjectNotFound,
        MarketEvidenceUnavailable,
        MarketProvenanceIncomplete,
        MarketAnalysisPending,
        MarketAnalysisPartial,
        MarketAnalysisStale,
        MarketAnalysisFailed,
        MarketGovernanceFailure,
        MarketAuthorizationDenied,
        MarketTimeout,
        MarketInternalFailure,
    )
    failures = [failure_class("failure") for failure_class in failure_classes]
    serialized = [serialize(failure) for failure in failures]
    assert len(set(serialized)) == len(serialized)
    assert all('"__type__":"' + cls.__name__ + '"' in value for cls, value in zip(failure_classes, serialized))
    assert issubclass(MarketBoundaryFailure, object)
    for invalid_failure in ("failure", object()):
        with pytest.raises(ValueError, match="non-Market"):
            envelope(failures=(invalid_failure,))


def test_g1_runtime_vocabulary_is_frozen():
    assert [state.value for state in CapabilityAvailability] == [
        "AVAILABLE",
        "DEGRADED",
        "NOT_READY",
        "UNAVAILABLE",
    ]
    assert [state.value for state in ReadinessState] == [
        "READY",
        "DEGRADED",
        "NOT_READY",
        "UNAVAILABLE",
    ]
    assert CapabilityAvailability.AVAILABLE is not ReadinessState.READY
    assert CapabilityAvailability.AVAILABLE != ReadinessState.READY
    assert [state.value for state in CompatibilityState] == [
        "COMPATIBLE",
        "CONTRACT_MISMATCH",
        "RELEASE_MISMATCH",
        "UNKNOWN",
    ]

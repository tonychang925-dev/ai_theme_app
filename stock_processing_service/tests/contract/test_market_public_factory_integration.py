from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from datetime import date, datetime, timezone
from typing import Any

import pytest

from stock_processing_service.application.identity.models import (
    ArtifactDigest,
    EvidencePurpose,
    MechanicalEvidence,
    ReleaseEvidenceBasis,
    RuntimeInstanceIdentity,
)
from stock_processing_service.application.identity.release_identity_verifier import (
    CanonicalArtifact,
    CanonicalReleaseManifest,
    ReleaseIdentityVerificationError,
)
from stock_processing_service.application.services.analyst_workbench.approval_contract import (
    ApprovalAuthorizationError,
    ApprovalPrincipal,
)
from stock_processing_service.application.services.analyst_workbench.approval_gate import (
    GovernedWorkbenchProduct,
)
from stock_processing_service.application.services.market_analytical_public_boundary import (
    PRODUCT_OBJECT_TYPE,
    PRODUCT_READ_CAPABILITY_ID,
)
from stock_processing_service.application.services.market_public_provider_factory import (
    MarketPublicFactoryInputs,
    MarketPublicProviderBinding,
    MarketPublicProviderFactory,
)
from stock_processing_service.contracts.market_public_boundary import (
    CompatibilityState,
    DataState,
    MarketAuthorizationDenied,
    MarketBoundaryIdentity,
    MarketGovernanceState,
    MarketObjectNotFound,
    MarketReleaseIdentity,
    MarketResultEnvelope,
    MarketRuntimeObservation,
    OperationStatus,
    ReadinessState,
    ReleaseIdentityEvidenceBasis,
)
from stock_processing_service.infrastructure.gateway_adapters.market_public_capability_provider import (
    MarketPublicCapabilityProvider,
    MarketPublicProductReadRequest,
)


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
PRODUCT_ID = "wgp:2026-07-10:abcdefghij"
REVISION_ID = "rev:v1:abcdef"
SOURCE_ID = "source:market-product:candidate:v1"
BUILD_ID = "build:market-product:candidate:v1"
ARTIFACT_ID = "artifact:market-product:candidate:v1"
MANIFEST_REF = "manifest:market-product:candidate:v1"
RUNTIME_ID = "runtime:market-product:candidate:v1"
ARTIFACT_BYTES = b"market product canonical bytes\n"
ARTIFACT_DIGEST = ArtifactDigest("sha256:" + hashlib.sha256(ARTIFACT_BYTES).hexdigest())
MANIFEST_DOCUMENT = {
    "manifest_ref": MANIFEST_REF,
    "profile_id": "market-product-judgment-v1",
    "source_identity": SOURCE_ID,
    "build_identity": BUILD_ID,
    "artifact_identity": ARTIFACT_ID,
    "artifact_digest": ARTIFACT_DIGEST.value,
    "artifact_locator": "canonical:releases/market-product.bin",
}
MANIFEST_BYTES = json.dumps(
    MANIFEST_DOCUMENT, ensure_ascii=False, sort_keys=True, separators=(",", ":")
).encode("utf-8")
MANIFEST_DIGEST = ArtifactDigest("sha256:" + hashlib.sha256(MANIFEST_BYTES).hexdigest())


def canonical_release() -> (
    tuple[CanonicalReleaseManifest, CanonicalArtifact, ArtifactDigest]
):
    manifest = CanonicalReleaseManifest(
        manifest_ref=MANIFEST_REF,
        profile_id="market-product-judgment-v1",
        source_identity=SOURCE_ID,
        build_identity=BUILD_ID,
        artifact_identity=ARTIFACT_ID,
        artifact_digest=ARTIFACT_DIGEST,
        artifact_locator="releases/market-product.bin",
        manifest_digest=MANIFEST_DIGEST,
    )
    artifact = CanonicalArtifact(
        artifact_identity=ARTIFACT_ID,
        artifact_locator="releases/market-product.bin",
        bytes_=ARTIFACT_BYTES,
    )
    return manifest, artifact, ARTIFACT_DIGEST


def evidence(
    manifest: CanonicalReleaseManifest | None = None,
    digest: ArtifactDigest = ARTIFACT_DIGEST,
    transaction: str = "verifier-output:market-product:1",
) -> tuple[MechanicalEvidence, ...]:
    manifest = manifest or canonical_release()[0]
    identity_digest = lambda value: ArtifactDigest(
        "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
    )
    return (
        MechanicalEvidence(
            EvidencePurpose.MANIFEST,
            ReleaseEvidenceBasis.CLEAN_REPOSITORY_SNAPSHOT,
            manifest.manifest_digest,
            transaction,
        ),
        MechanicalEvidence(
            EvidencePurpose.ARTIFACT_IDENTITY,
            ReleaseEvidenceBasis.EXPLICIT_CAPTURED_ARTIFACT,
            identity_digest(manifest.artifact_identity),
            transaction,
        ),
        MechanicalEvidence(
            EvidencePurpose.ARTIFACT_DIGEST,
            ReleaseEvidenceBasis.EXPLICIT_CAPTURED_ARTIFACT,
            digest,
            transaction,
        ),
        MechanicalEvidence(
            EvidencePurpose.SOURCE_BUILD_LINEAGE,
            ReleaseEvidenceBasis.CLEAN_REPOSITORY_SNAPSHOT,
            identity_digest(f"{manifest.source_identity}\0{manifest.build_identity}"),
            transaction,
        ),
    )


def release_identity() -> MarketReleaseIdentity:
    return MarketReleaseIdentity(
        source_identity=SOURCE_ID,
        build_identity=BUILD_ID,
        artifact_identity=ARTIFACT_ID,
        artifact_digest=ARTIFACT_DIGEST.value,
        release_manifest_ref=MANIFEST_REF,
    )


def boundary() -> MarketBoundaryIdentity:
    return MarketBoundaryIdentity(
        provider_id="market",
        public_contract_name="market-public-boundary",
        public_contract_version="1.0",
        release_identity=release_identity(),
        supported_capabilities=(PRODUCT_READ_CAPABILITY_ID,),
        supported_object_types=(PRODUCT_OBJECT_TYPE,),
    )


class ControlledApprovalGate:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls: list[date] = []

    def check(self, trade_date: date):
        self.calls.append(trade_date)
        return type(
            "Approval",
            (),
            {"can_generate_report": self.available, "reason": "unavailable"},
        )()


class ControlledGovernedPort:
    def __init__(self, product: GovernedWorkbenchProduct | None) -> None:
        self.product = product
        self.calls: list[date] = []

    def read(self, trade_date: date) -> GovernedWorkbenchProduct | None:
        self.calls.append(trade_date)
        return self.product


def governed_product(
    **changes: Any,
) -> GovernedWorkbenchProduct:
    values = {
        "product_id": PRODUCT_ID,
        "revision_id": REVISION_ID,
        "governance_state": MarketGovernanceState.APPROVED.value,
        "produced_at": NOW.replace(minute=1).isoformat(),
        "data_cutoff": NOW.isoformat(),
        "supersedes_revision_id": "",
        "judgment_content": {"narrative": {"main_story": "Governed judgment"}},
        "provenance_refs": ("market-source:1",),
        "assumptions": ("market-close-input",),
        "limitations": ("no-intraday-refresh",),
    }
    values.update(changes)
    return GovernedWorkbenchProduct(**values)


def factory_inputs(
    *,
    approval_gate: ControlledApprovalGate | None = None,
    governed_port: ControlledGovernedPort | None = None,
    close_hook: Any = None,
    boundary_identity: MarketBoundaryIdentity | None = None,
    release_manifest: CanonicalReleaseManifest | None = None,
    mechanical_evidence: tuple[MechanicalEvidence, ...] | None = None,
) -> MarketPublicFactoryInputs:
    manifest, artifact, digest = canonical_release()
    return MarketPublicFactoryInputs(
        approval_gate=approval_gate or ControlledApprovalGate(),
        governed_product_port=governed_port
        or ControlledGovernedPort(governed_product()),
        boundary_identity=boundary_identity or boundary(),
        release_manifest=release_manifest or manifest,
        release_artifact=artifact,
        computed_artifact_digest=digest,
        runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
        mechanical_evidence=mechanical_evidence or evidence(manifest, digest),
        authorization="Bearer explicit-test-composition-token",
        close_hook=close_hook,
    )


@pytest.fixture()
def valid_binding(monkeypatch) -> MarketPublicProviderBinding:
    import stock_processing_service.application.services.market_public_provider_factory as factory_module

    monkeypatch.setattr(
        factory_module,
        "require_approval_principal",
        lambda authorization: ApprovalPrincipal(
            "7", "service@market.example.test", "analyst"
        ),
    )
    return MarketPublicProviderFactory().create(factory_inputs())


def public_request(**changes: Any) -> MarketPublicProductReadRequest:
    values = {
        "capability_id": PRODUCT_READ_CAPABILITY_ID,
        "capability_version": "1.0",
        "object_id": PRODUCT_ID,
        "revision_id": REVISION_ID,
        "correlation_id": "correlation-1",
        "request_id": "request-1",
    }
    values.update(changes)
    return MarketPublicProductReadRequest(**values)


def test_m_commit_has_exact_ordered_parents_and_f_direct_parent() -> None:
    def git(*arguments: str) -> str:
        return subprocess.check_output(
            ["git", "rev-parse", *arguments], text=True
        ).strip()

    merge_commit = git("HEAD^")
    parents = (
        subprocess.check_output(
            ["git", "show", "-s", "--format=%P", merge_commit], text=True
        )
        .strip()
        .split()
    )
    assert parents == [
        "b79a1692ba84cc093bf8ba4e721b2b8acff45f0e",
        "08f34f0c3148c17ada669e488e62a5ec678b6556",
    ]
    assert git(f"{merge_commit}^1") == parents[0]
    assert git(f"{merge_commit}^2") == parents[1]
    assert git("HEAD^") == merge_commit


async def test_valid_factory_returns_exact_public_binding_and_verified_read(
    valid_binding, monkeypatch
) -> None:
    import stock_processing_service.infrastructure.gateway_adapters.market_public_capability_provider as provider_module

    calls = []
    original = provider_module.require_verified_result

    def verified(*arguments, **keyword_arguments):
        calls.append((arguments, keyword_arguments))
        return original(*arguments, **keyword_arguments)

    monkeypatch.setattr(provider_module, "require_verified_result", verified)
    assert valid_binding.provider_id == "market"
    assert valid_binding.capability_manifest["capability_id"] == (
        PRODUCT_READ_CAPABILITY_ID
    )
    assert valid_binding.capability_manifest["capability_version"] == "1.0"
    assert valid_binding.boundary_identity == boundary()
    observation = valid_binding.runtime_observation
    assert isinstance(observation, MarketRuntimeObservation)
    assert observation.runtime_instance_id == RUNTIME_ID
    assert observation.readiness_state is ReadinessState.READY
    assert observation.compatibility_state is CompatibilityState.COMPATIBLE
    assert set(observation.release_identity_evidence_basis) == {
        ReleaseIdentityEvidenceBasis.MANIFEST_VERIFIED,
        ReleaseIdentityEvidenceBasis.ARTIFACT_IDENTITY_VERIFIED,
        ReleaseIdentityEvidenceBasis.ARTIFACT_DIGEST_VERIFIED,
        ReleaseIdentityEvidenceBasis.SOURCE_BUILD_LINEAGE_VERIFIED,
    }
    assert observation is valid_binding.provider._runtime_observation
    assert (await valid_binding.provider.health()) == (True, "READY/COMPATIBLE")

    result = await valid_binding.provider.execute(public_request())
    assert result["status"] == "success"
    assert result["data_state"] == DataState.READY.value
    assert result["payload"]["product_id"] == PRODUCT_ID
    assert len(calls) == 1


async def test_ready_and_stale_results_preserve_data_state(valid_binding) -> None:
    ready = await valid_binding.provider.execute(public_request())
    stale = await valid_binding.provider.execute(
        public_request(as_of=NOW.replace(minute=1))
    )
    assert ready["data_state"] == DataState.READY.value
    assert stale["data_state"] == DataState.STALE.value
    assert stale["payload"]["revision_id"] == REVISION_ID


def test_runtime_binding_and_health_reject_wrong_instance_or_identity(
    valid_binding,
) -> None:
    wrong_observation = replace(
        valid_binding.runtime_observation,
        runtime_instance_id="runtime:other",
    )
    with pytest.raises(ValueError, match="provider runtime identity"):
        MarketPublicProviderBinding(
            provider_id="market",
            provider=valid_binding.provider,
            capability_manifest=valid_binding.capability_manifest,
            boundary_identity=valid_binding.boundary_identity,
            runtime_observation=wrong_observation,
        )
    weak = replace(
        valid_binding.runtime_observation,
        release_identity_evidence_basis=(
            ReleaseIdentityEvidenceBasis.PROVIDER_ATTESTED,
        ),
    )
    with pytest.raises(ValueError, match="provider runtime identity"):
        MarketPublicProviderBinding(
            provider_id="market",
            provider=valid_binding.provider,
            capability_manifest=valid_binding.capability_manifest,
            boundary_identity=valid_binding.boundary_identity,
            runtime_observation=weak,
        )


@pytest.mark.parametrize(
    "purpose",
    sorted(EvidencePurpose, key=lambda item: item.value),
)
def test_factory_rejects_missing_g5_evidence_purpose(
    monkeypatch, purpose: EvidencePurpose
) -> None:
    import stock_processing_service.application.services.market_public_provider_factory as factory_module

    monkeypatch.setattr(
        factory_module,
        "require_approval_principal",
        lambda authorization: ApprovalPrincipal(
            "7", "service@market.example.test", "analyst"
        ),
    )
    incomplete = tuple(item for item in evidence() if item.purpose is not purpose)
    with pytest.raises(ReleaseIdentityVerificationError, match="missing"):
        MarketPublicProviderFactory().create(
            factory_inputs(mechanical_evidence=incomplete)
        )


def test_factory_rejects_bad_release_identity_or_mechanical_transaction(
    monkeypatch,
) -> None:
    import stock_processing_service.application.services.market_public_provider_factory as factory_module

    monkeypatch.setattr(
        factory_module,
        "require_approval_principal",
        lambda authorization: ApprovalPrincipal(
            "7", "service@market.example.test", "analyst"
        ),
    )
    manifest, artifact, digest = canonical_release()
    wrong_boundary = replace(
        boundary(),
        release_identity=replace(release_identity(), source_identity="source:other"),
    )
    with pytest.raises(ReleaseIdentityVerificationError, match="does not match"):
        MarketPublicProviderFactory().create(
            factory_inputs(boundary_identity=wrong_boundary)
        )
    bad_profile = replace(manifest, profile_id="market-other:v1")
    with pytest.raises(ValueError, match="profile is invalid"):
        MarketPublicProviderFactory().create(
            factory_inputs(
                boundary_identity=replace(
                    boundary(),
                    release_identity=replace(release_identity()),
                ),
                release_manifest=bad_profile,
                mechanical_evidence=evidence(bad_profile),
            )
        )
    changed_artifact = replace(artifact, bytes_=b"changed")
    with pytest.raises(ReleaseIdentityVerificationError, match="digest mismatch"):
        base_inputs = factory_inputs()
        changed_digest = ArtifactDigest(
            "sha256:" + hashlib.sha256(b"changed").hexdigest()
        )
        MarketPublicProviderFactory().create(
            MarketPublicFactoryInputs(
                approval_gate=base_inputs.approval_gate,
                governed_product_port=base_inputs.governed_product_port,
                boundary_identity=base_inputs.boundary_identity,
                release_manifest=base_inputs.release_manifest,
                release_artifact=changed_artifact,
                computed_artifact_digest=changed_digest,
                runtime_instance_identity=base_inputs.runtime_instance_identity,
                mechanical_evidence=evidence(
                    base_inputs.release_manifest, changed_digest
                ),
                authorization=base_inputs.authorization,
                close_hook=base_inputs.close_hook,
            )
        )
    split_evidence = list(evidence(manifest, digest))
    split_evidence[-1] = replace(
        split_evidence[-1], verifier_output_id="verifier-output:split"
    )
    split_transaction = tuple(split_evidence)
    with pytest.raises(ReleaseIdentityVerificationError, match="one mechanical"):
        MarketPublicProviderFactory().create(
            factory_inputs(mechanical_evidence=split_transaction)
        )


def test_factory_rejects_invalid_missing_or_unauthorized_principal(
    monkeypatch,
) -> None:
    import stock_processing_service.application.services.market_public_provider_factory as factory_module

    def invalid(authorization: str):
        raise ApprovalAuthorizationError("invalid")

    monkeypatch.setattr(factory_module, "require_approval_principal", invalid)
    with pytest.raises(ApprovalAuthorizationError):
        MarketPublicProviderFactory().create(factory_inputs())
    monkeypatch.setattr(
        factory_module,
        "require_approval_principal",
        lambda authorization: ApprovalPrincipal(
            "7", "admin@market.example.test", "admin"
        ),
    )
    with pytest.raises(ValueError, match="analyst"):
        MarketPublicProviderFactory().create(factory_inputs())


async def test_bearer_and_request_authority_cannot_be_retained_or_overridden(
    valid_binding,
) -> None:
    provider_values = vars(valid_binding.provider)
    assert provider_values["_principal_id"] == "user:7:service@market.example.test"
    assert all(
        "explicit-test-composition-token" not in str(value)
        for value in provider_values.values()
    )
    with pytest.raises(TypeError):
        public_request(principal="user:9:override@example.test")
    denied = await valid_binding.provider.execute(
        public_request(capability_id="market.other.read")
    )
    assert denied["status"] == "error"
    assert denied["error_code"] == "unsupported_capability"


async def test_unknown_request_fields_and_non_product_capabilities_fail(
    valid_binding,
) -> None:
    with pytest.raises(TypeError):
        public_request(transport="transport-value")
    wrong_version = await valid_binding.provider.execute(
        public_request(capability_version="2.0")
    )
    assert wrong_version["error_code"] == "capability_version_mismatch"
    invalid_type = await valid_binding.provider.execute({"capability_id": "market"})
    assert invalid_type["error_code"] == "contract_mismatch"


async def test_governed_reader_failures_map_to_typed_provider_errors(
    monkeypatch,
) -> None:
    import stock_processing_service.application.services.market_public_provider_factory as factory_module

    monkeypatch.setattr(
        factory_module,
        "require_approval_principal",
        lambda authorization: ApprovalPrincipal(
            "7", "service@market.example.test", "analyst"
        ),
    )
    unavailable = MarketPublicProviderFactory().create(
        factory_inputs(approval_gate=ControlledApprovalGate(False))
    )
    unavailable_result = await unavailable.provider.execute(public_request())
    assert unavailable_result["status"] == "error"
    assert unavailable_result["error_code"] == "market_governance_failure"

    missing = MarketPublicProviderFactory().create(
        factory_inputs(governed_port=ControlledGovernedPort(None))
    )
    missing_provider = missing.provider
    missing_success = await missing_provider._service.read_product(
        public_request_boundary(missing_provider._principal_id)
    )
    missing_provider._service = ControlledBoundaryService(
        replace(
            missing_success,
            operation_status=OperationStatus.FAILURE,
            payload=None,
            failures=(MarketObjectNotFound("Market product was not found"),),
        )
    )
    missing_result = await missing_provider.execute(public_request())
    assert missing_result["status"] == "unavailable"
    assert missing_result["error_code"] == "market_object_not_found"

    superseded = MarketPublicProviderFactory().create(
        factory_inputs(
            governed_port=ControlledGovernedPort(
                governed_product(revision_id="rev:v2:abcdef")
            )
        )
    )
    superseded_result = await superseded.provider.execute(public_request())
    assert superseded_result["status"] == "error"
    assert superseded_result["error_code"] == "market_governance_failure"


class ControlledBoundaryService:
    def __init__(
        self,
        result: MarketResultEnvelope | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error

    async def read_product(self, request):
        if self.error is not None:
            raise self.error
        return self.result


async def test_provider_failure_mapping_and_no_partial_promotion(
    valid_binding, monkeypatch
) -> None:
    success = await valid_binding.provider.execute(public_request())
    assert success["status"] == "success"
    provider = valid_binding.provider
    original_service = provider._service
    partial = replace(
        await original_service.read_product(
            public_request_boundary(provider._principal_id)
        ),
        operation_status=OperationStatus.PARTIAL,
    )
    provider._service = ControlledBoundaryService(partial)
    partial_result = await provider.execute(public_request())
    assert partial_result["status"] == "error"
    assert partial_result["error_code"] == "invalid_product_result"

    denied_envelope = await original_service.read_product(
        public_request_boundary("anonymous")
    )
    provider._service = ControlledBoundaryService(
        denied_envelope
        if denied_envelope.failures[0].failure_type == "MarketAuthorizationDenied"
        else replace(
            denied_envelope,
            failures=(MarketAuthorizationDenied("principal rejected"),),
        )
    )
    denied = await provider.execute(public_request())
    assert denied["status"] == "error"
    assert denied["error_code"] == "market_authorization_rejected"
    assert "denied" not in denied

    provider._service = ControlledBoundaryService(error=RuntimeError("internal"))
    internal = await provider.execute(public_request())
    assert internal["status"] == "error"
    assert internal["error_code"] == "market_internal_failure"


async def test_unverified_or_unserializable_success_never_becomes_provider_success(
    valid_binding,
) -> None:
    provider = valid_binding.provider
    original_service = provider._service
    verified = await original_service.read_product(
        public_request_boundary(provider._principal_id)
    )
    unverified = replace(
        verified,
        provenance=replace(
            verified.provenance,
            market_release_identity=replace(
                verified.provenance.market_release_identity,
                source_identity="source:other",
            ),
        ),
    )
    provider._service = ControlledBoundaryService(unverified)
    unverified_result = await provider.execute(public_request())
    assert unverified_result["status"] == "error"
    assert unverified_result["error_code"] == ("release_identity_verification_failed")

    unserializable = replace(verified, payload=object())
    provider._service = ControlledBoundaryService(unserializable)
    serialized_result = await provider.execute(public_request())
    assert serialized_result["status"] == "error"
    assert serialized_result["error_code"] == "result_serialization_failed"


def public_request_boundary(principal_id: str):
    from stock_processing_service.application.services.market_analytical_public_boundary import (
        MarketProductReadRequest,
    )
    from stock_processing_service.contracts.market_public_boundary import (
        MarketObjectRef,
    )

    return MarketProductReadRequest(
        object_ref=MarketObjectRef(PRODUCT_OBJECT_TYPE, PRODUCT_ID, REVISION_ID),
        correlation_id="correlation-1",
        principal_id=principal_id,
        request_id="request-1",
    )


async def test_close_invalidates_only_exact_provider(monkeypatch) -> None:
    import stock_processing_service.application.services.market_public_provider_factory as factory_module

    monkeypatch.setattr(
        factory_module,
        "require_approval_principal",
        lambda authorization: ApprovalPrincipal(
            "7", "service@market.example.test", "analyst"
        ),
    )
    first = MarketPublicProviderFactory().create(factory_inputs())
    second = MarketPublicProviderFactory().create(factory_inputs())
    await first.close()
    assert (await first.provider.health()) == (False, "market_provider_closed")
    assert (await second.provider.health()) == (True, "READY/COMPATIBLE")
    failed_hook: list[str] = []

    def fail_close() -> None:
        failed_hook.append("failed")
        raise RuntimeError("close failed")

    failed = MarketPublicProviderFactory().create(factory_inputs(close_hook=fail_close))
    with pytest.raises(RuntimeError):
        await failed.close()
    assert (await failed.provider.health()) == (False, "market_close_failed")

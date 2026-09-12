"""Explicit composition root for the Market public product provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from stock_processing_service.application.identity.models import (
    ArtifactDigest,
    MechanicalEvidence,
    RuntimeInstanceIdentity,
)
from stock_processing_service.application.identity.release_identity_verifier import (
    CanonicalArtifact,
    CanonicalReleaseManifest,
    ReleaseIdentityVerifier,
    VerifiedReleaseIdentity,
)
from stock_processing_service.application.services.analyst_workbench.approval_contract import (
    require_approval_principal,
)
from stock_processing_service.application.services.analyst_workbench.approval_gate import (
    ApprovalGate,
)
from stock_processing_service.application.services.market_analytical_public_boundary import (
    PRODUCT_OBJECT_TYPE,
    PRODUCT_READ_CAPABILITY_ID,
    MarketAnalyticalPublicBoundaryService,
    product_provenance_profile,
    product_read_capability_manifest,
)
from stock_processing_service.contracts.market_public_boundary import (
    MarketBoundaryIdentity,
    MarketRuntimeObservation,
    to_mapping,
    validate_boundary_reconciliation,
    validate_capability_manifest,
    validate_runtime_observation,
)
from stock_processing_service.infrastructure.gateway_adapters.market_governed_product_public_reader import (
    GovernedProductPort,
    MarketGovernedProductPublicReader,
)
from stock_processing_service.infrastructure.gateway_adapters.market_public_capability_provider import (
    MarketPublicCapabilityProvider,
    build_verified_runtime_observation,
    validate_exact_provider_runtime,
)


@dataclass(frozen=True, slots=True)
class MarketPublicFactoryInputs:
    approval_gate: ApprovalGate
    governed_product_port: GovernedProductPort
    boundary_identity: MarketBoundaryIdentity
    release_manifest: CanonicalReleaseManifest
    release_artifact: CanonicalArtifact
    computed_artifact_digest: ArtifactDigest
    runtime_instance_identity: RuntimeInstanceIdentity
    mechanical_evidence: tuple[MechanicalEvidence, ...]
    authorization: str
    close_hook: Callable[[], None] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.boundary_identity, MarketBoundaryIdentity):
            raise ValueError("boundary_identity must be a MarketBoundaryIdentity")
        if not isinstance(self.release_manifest, CanonicalReleaseManifest):
            raise ValueError("release_manifest must be canonical")
        if not isinstance(self.release_artifact, CanonicalArtifact):
            raise ValueError("release_artifact must be canonical")
        if not isinstance(self.computed_artifact_digest, ArtifactDigest):
            raise ValueError("computed_artifact_digest must be an ArtifactDigest")
        if not isinstance(self.runtime_instance_identity, RuntimeInstanceIdentity):
            raise ValueError("runtime_instance_identity has the wrong type")
        if not isinstance(self.mechanical_evidence, tuple) or not (
            self.mechanical_evidence
        ):
            raise ValueError("mechanical_evidence must be a non-empty tuple")
        if any(
            not isinstance(item, MechanicalEvidence)
            for item in self.mechanical_evidence
        ):
            raise ValueError("mechanical_evidence contains an invalid item")
        if not isinstance(self.authorization, str) or not self.authorization.strip():
            raise ValueError("authorization must be a non-empty string")
        if self.close_hook is not None and not callable(self.close_hook):
            raise ValueError("close_hook must be callable or None")
        if self.approval_gate is None or self.governed_product_port is None:
            raise ValueError("Market dependencies must be explicitly supplied")


@dataclass(frozen=True, slots=True)
class MarketPublicProviderBinding:
    provider_id: str
    provider: MarketPublicCapabilityProvider
    capability_manifest: dict[str, Any]
    boundary_identity: MarketBoundaryIdentity
    runtime_observation: MarketRuntimeObservation

    def __post_init__(self) -> None:
        if self.provider_id != "market":
            raise ValueError("Market binding provider_id is invalid")
        if not isinstance(self.provider, MarketPublicCapabilityProvider):
            raise ValueError("Market binding provider is invalid")
        if not isinstance(self.capability_manifest, dict):
            raise ValueError("Market capability manifest must be a mapping")
        if not isinstance(self.boundary_identity, MarketBoundaryIdentity):
            raise ValueError("Market boundary identity is invalid")
        if not validate_exact_provider_runtime(
            provider_runtime_identity=self.provider.runtime_instance_id,
            provider_observation=self.runtime_observation,
            boundary_identity=self.boundary_identity,
        ):
            raise ValueError("Market provider runtime identity is invalid")
        if self.runtime_observation is not self.provider._runtime_observation:
            raise ValueError("Market runtime observation is not provider-bound")
        if not validate_runtime_observation(self.runtime_observation).valid:
            raise ValueError("Market runtime observation is invalid")

    async def close(self) -> None:
        await self.provider.close()


class MarketPublicProviderFactory:
    def create(self, inputs: MarketPublicFactoryInputs) -> MarketPublicProviderBinding:
        if not isinstance(inputs, MarketPublicFactoryInputs):
            raise ValueError("Market factory inputs are invalid")

        principal = require_approval_principal(inputs.authorization)
        if principal.role != "analyst":
            raise ValueError("Market integration principal must be an analyst")
        principal_identity = principal.identity

        verified_identity: VerifiedReleaseIdentity = ReleaseIdentityVerifier().verify(
            attested_release=inputs.boundary_identity.release_identity,
            manifest=inputs.release_manifest,
            artifact=inputs.release_artifact,
            computed_artifact_digest=inputs.computed_artifact_digest,
            runtime_instance_identity=inputs.runtime_instance_identity,
            evidence=inputs.mechanical_evidence,
        )
        manifest = product_read_capability_manifest()
        if inputs.release_manifest.profile_id != "market-product-judgment-v1":
            raise ValueError("Market release manifest profile is invalid")
        if manifest.provenance_profile_ref != product_provenance_profile().profile_id:
            raise ValueError("Market provenance profile is invalid")
        manifest_validation = validate_capability_manifest(manifest)
        reconciliation = validate_boundary_reconciliation(
            inputs.boundary_identity,
            (manifest,),
        )
        if (
            not manifest_validation.valid
            or not reconciliation.valid
            or inputs.boundary_identity.provider_id != "market"
            or inputs.boundary_identity.supported_capabilities
            != (PRODUCT_READ_CAPABILITY_ID,)
            or inputs.boundary_identity.supported_object_types != (PRODUCT_OBJECT_TYPE,)
        ):
            raise ValueError("Market public boundary reconciliation failed")

        reader = MarketGovernedProductPublicReader(
            inputs.approval_gate,
            inputs.governed_product_port,
        )
        service = MarketAnalyticalPublicBoundaryService(
            reader,
            inputs.boundary_identity,
        )
        observation = build_verified_runtime_observation(
            boundary_identity=inputs.boundary_identity,
            verified_identity=verified_identity,
        )
        provider = MarketPublicCapabilityProvider(
            service=service,
            principal_id=principal_identity,
            boundary_identity=inputs.boundary_identity,
            verified_identity=verified_identity,
            runtime_observation=observation,
            close_hook=inputs.close_hook,
        )
        if not validate_exact_provider_runtime(
            provider_runtime_identity=provider.runtime_instance_id,
            provider_observation=observation,
            boundary_identity=inputs.boundary_identity,
        ):
            raise ValueError("Market exact-instance runtime validation failed")
        return MarketPublicProviderBinding(
            provider_id="market",
            provider=provider,
            capability_manifest=to_mapping(manifest),
            boundary_identity=inputs.boundary_identity,
            runtime_observation=observation,
        )

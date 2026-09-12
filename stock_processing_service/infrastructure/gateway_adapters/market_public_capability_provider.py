"""Transport-neutral public provider for the governed Market product read."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from stock_processing_service.application.identity.release_identity_verifier import (
    ReleaseIdentityVerificationError,
    VerifiedReleaseIdentity,
    require_verified_result,
)
from stock_processing_service.application.services.market_analytical_public_boundary import (
    PRODUCT_CAPABILITY_VERSION,
    PRODUCT_OBJECT_TYPE,
    PRODUCT_READ_CAPABILITY_ID,
    EpistemicClass,
    MarketAnalyticalPublicBoundaryService,
    MarketProductReadRequest,
    ProvenanceValidationContext,
    product_provenance_profile,
)
from stock_processing_service.contracts.market_public_boundary import (
    CapabilityAvailability,
    CompatibilityState,
    MarketBoundaryIdentity,
    MarketCapabilityRuntimeObservation,
    MarketReleaseIdentity,
    MarketResultEnvelope,
    MarketRuntimeObservation,
    OperationStatus,
    ReadinessState,
    ReleaseIdentityEvidenceBasis,
    to_mapping,
)


@dataclass(frozen=True, slots=True)
class MarketPublicProductReadRequest:
    capability_id: str
    capability_version: str
    object_id: str
    revision_id: str
    correlation_id: str
    request_id: str | None = None
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "capability_id",
            "capability_version",
            "object_id",
            "revision_id",
            "correlation_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.request_id is not None and (
            not isinstance(self.request_id, str) or not self.request_id.strip()
        ):
            raise ValueError("request_id must be a non-empty string or None")
        if self.as_of is not None and (
            not isinstance(self.as_of, datetime) or self.as_of.tzinfo is None
        ):
            raise ValueError("as_of must be a timezone-aware datetime")


class MarketPublicCapabilityProvider:
    def __init__(
        self,
        *,
        service: MarketAnalyticalPublicBoundaryService,
        principal_id: str,
        boundary_identity: MarketBoundaryIdentity,
        verified_identity: VerifiedReleaseIdentity,
        runtime_observation: MarketRuntimeObservation,
        close_hook: Callable[[], None] | None,
    ) -> None:
        self._service = service
        self._principal_id = principal_id
        self._boundary_identity = boundary_identity
        self._verified_identity = verified_identity
        self._runtime_identity = verified_identity.runtime_instance_identity
        self._runtime_observation = runtime_observation
        self._close_hook = close_hook
        self._closed = False
        self._close_failed = False

    @property
    def runtime_instance_id(self) -> str:
        return self._runtime_identity

    async def execute(self, request: Any) -> dict[str, Any]:
        if self._closed or self._close_failed or not self._runtime_valid():
            return self._error("provider_unavailable", "Market provider is unavailable")
        if not isinstance(request, MarketPublicProductReadRequest):
            return self._error(
                "contract_mismatch", "Market public request type is invalid"
            )
        if request.capability_id != PRODUCT_READ_CAPABILITY_ID:
            return self._error(
                "unsupported_capability", "Only market.product.read is supported"
            )
        if request.capability_version != PRODUCT_CAPABILITY_VERSION:
            return self._error(
                "capability_version_mismatch",
                "Only market.product.read version 1.0 is supported",
            )

        from stock_processing_service.contracts.market_public_boundary import (
            MarketObjectRef,
        )

        boundary_request = MarketProductReadRequest(
            object_ref=MarketObjectRef(
                PRODUCT_OBJECT_TYPE, request.object_id, request.revision_id
            ),
            correlation_id=request.correlation_id,
            principal_id=self._principal_id,
            request_id=request.request_id,
            as_of=request.as_of,
        )
        try:
            envelope = await self._service.read_product(boundary_request)
            if envelope.operation_status in (
                OperationStatus.SUCCESS,
                OperationStatus.PARTIAL,
            ):
                try:
                    require_verified_result(
                        envelope,
                        profile=product_provenance_profile(),
                        context=self._provenance_context(envelope),
                        verified_identity=self._verified_identity,
                        expected_profile_ref="market-product-judgment-v1",
                    )
                except ReleaseIdentityVerificationError as exc:
                    if envelope.operation_status is OperationStatus.PARTIAL:
                        return self._error(
                            "invalid_product_result",
                            "Partial Market result cannot become a full result",
                        )
                    return self._error("release_identity_verification_failed", str(exc))
            return self._from_envelope(envelope)
        except (ReleaseIdentityVerificationError, TypeError, ValueError) as exc:
            return self._error("invalid_product_result", str(exc))
        except Exception as exc:
            return self._error("market_internal_failure", str(exc))

    async def health(self) -> tuple[bool, str]:
        if self._close_failed:
            return False, "market_close_failed"
        if self._closed:
            return False, "market_provider_closed"
        if not self._runtime_valid():
            return False, "market_runtime_observation_invalid"
        return True, "READY/COMPATIBLE"

    async def close(self) -> None:
        if self._closed or self._close_failed:
            return
        try:
            if self._close_hook is not None:
                self._close_hook()
        except Exception:
            self._close_failed = True
            raise
        self._closed = True

    def _runtime_valid(self) -> bool:
        return validate_exact_provider_runtime(
            provider_runtime_identity=self._runtime_identity,
            provider_observation=self._runtime_observation,
            boundary_identity=self._boundary_identity,
        )

    def _provenance_context(
        self, envelope: MarketResultEnvelope
    ) -> ProvenanceValidationContext:
        payload = envelope.payload
        return ProvenanceValidationContext(
            capability_id=PRODUCT_READ_CAPABILITY_ID,
            epistemic_class=EpistemicClass.JUDGMENT,
            governance_state=getattr(payload, "governance_state", None),
            product_id=getattr(payload, "product_id", None),
        )

    def _from_envelope(self, envelope: MarketResultEnvelope) -> dict[str, Any]:
        if (
            envelope.capability_id != PRODUCT_READ_CAPABILITY_ID
            or envelope.contract_version != PRODUCT_CAPABILITY_VERSION
            or envelope.boundary_identity_ref != self._boundary_identity
        ):
            return self._error(
                "contract_mismatch", "Market result does not match the public binding"
            )
        if envelope.operation_status is not OperationStatus.SUCCESS:
            if envelope.failures:
                return self._from_boundary_failure(envelope.failures[0])
            return self._error(
                "invalid_product_result",
                "Only a complete Market product result can become a provider result",
            )
        try:
            return {
                "status": "success",
                "capability_id": PRODUCT_READ_CAPABILITY_ID,
                "capability_version": PRODUCT_CAPABILITY_VERSION,
                "correlation_id": envelope.correlation_id,
                "request_id": envelope.request_id,
                "data_state": envelope.data_state.value,
                "payload": to_mapping(envelope.payload),
                "provenance": to_mapping(envelope.provenance),
                "boundary_identity": to_mapping(self._boundary_identity),
            }
        except (TypeError, ValueError) as exc:
            return self._error("result_serialization_failed", str(exc))

    def _from_boundary_failure(self, failure: Any) -> dict[str, Any]:
        failure_type = getattr(failure, "failure_type", None)
        if failure_type == "MarketUnavailable":
            return self._error("market_unavailable", str(failure), status="unavailable")
        if failure_type == "MarketTimeout":
            return self._error("market_timeout", str(failure), status="timeout")
        if failure_type == "MarketObjectNotFound":
            return self._error(
                "market_object_not_found",
                str(failure),
                status="unavailable",
            )
        if failure_type == "MarketAuthorizationDenied":
            return self._error(
                "market_authorization_rejected", str(failure), status="error"
            )
        if failure_type == "MarketGovernanceFailure":
            return self._error("market_governance_failure", str(failure))
        if isinstance(failure_type, str) and failure_type.startswith("Market"):
            typed_code = "".join(
                "_" + character.lower() if character.isupper() else character
                for character in failure_type.removeprefix("Market")
            ).lower()
            return self._error(typed_code, str(failure))
        return self._error("market_internal_failure", str(failure))

    def _error(
        self, error_code: str, message: str, *, status: str = "error"
    ) -> dict[str, Any]:
        return {
            "status": status,
            "capability_id": PRODUCT_READ_CAPABILITY_ID,
            "capability_version": PRODUCT_CAPABILITY_VERSION,
            "error_code": error_code,
            "message": message,
        }


def build_verified_runtime_observation(
    *,
    boundary_identity: MarketBoundaryIdentity,
    verified_identity: VerifiedReleaseIdentity,
) -> MarketRuntimeObservation:
    public_release = _public_release_identity(verified_identity)
    return MarketRuntimeObservation(
        runtime_instance_id=verified_identity.runtime_instance_identity,
        attested_release_identity=boundary_identity.release_identity,
        release_identity_evidence_basis=(
            ReleaseIdentityEvidenceBasis.MANIFEST_VERIFIED,
            ReleaseIdentityEvidenceBasis.ARTIFACT_IDENTITY_VERIFIED,
            ReleaseIdentityEvidenceBasis.ARTIFACT_DIGEST_VERIFIED,
            ReleaseIdentityEvidenceBasis.SOURCE_BUILD_LINEAGE_VERIFIED,
        ),
        readiness_state=ReadinessState.READY,
        compatibility_state=CompatibilityState.COMPATIBLE,
        capability_runtime_observations=(
            MarketCapabilityRuntimeObservation(
                capability_id=PRODUCT_READ_CAPABILITY_ID,
                availability_state=CapabilityAvailability.AVAILABLE,
                observed_at=verified_identity.verified_at,
            ),
        ),
        observed_at=verified_identity.verified_at,
        verified_release_identity=public_release,
    )


def validate_exact_provider_runtime(
    *,
    provider_runtime_identity: str,
    provider_observation: MarketRuntimeObservation,
    boundary_identity: MarketBoundaryIdentity,
) -> bool:
    required_evidence = {
        ReleaseIdentityEvidenceBasis.MANIFEST_VERIFIED,
        ReleaseIdentityEvidenceBasis.ARTIFACT_IDENTITY_VERIFIED,
        ReleaseIdentityEvidenceBasis.ARTIFACT_DIGEST_VERIFIED,
        ReleaseIdentityEvidenceBasis.SOURCE_BUILD_LINEAGE_VERIFIED,
    }
    observation = provider_observation
    return (
        provider_runtime_identity == observation.runtime_instance_id
        and observation.attested_release_identity == boundary_identity.release_identity
        and observation.verified_release_identity == boundary_identity.release_identity
        and set(observation.release_identity_evidence_basis) == required_evidence
        and len(observation.release_identity_evidence_basis) == len(required_evidence)
        and observation.readiness_state is ReadinessState.READY
        and observation.compatibility_state is CompatibilityState.COMPATIBLE
        and len(observation.capability_runtime_observations) == 1
        and observation.capability_runtime_observations[0].capability_id
        == PRODUCT_READ_CAPABILITY_ID
        and observation.capability_runtime_observations[0].availability_state
        is CapabilityAvailability.AVAILABLE
        and observation.observed_at.tzinfo is not None
        and observation.capability_runtime_observations[0].observed_at.tzinfo
        is not None
    )


def _public_release_identity(
    verified_identity: VerifiedReleaseIdentity,
) -> MarketReleaseIdentity:
    return MarketReleaseIdentity(
        source_identity=verified_identity.source_identity,
        build_identity=verified_identity.build_identity,
        artifact_identity=verified_identity.artifact_identity,
        artifact_digest=verified_identity.artifact_digest.value,
        release_manifest_ref=verified_identity.manifest_ref,
    )

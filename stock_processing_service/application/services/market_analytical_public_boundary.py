from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from stock_processing_service.contracts.market_public_boundary import (
    DataCutoffPredicate,
    DataState,
    EpistemicClass,
    IdempotencySupport,
    MarketAuthorizationDenied,
    MarketAuthorizationRequirement,
    MarketBoundaryCapabilityContractReference,
    MarketBoundaryFailure,
    MarketBoundaryIdentity,
    MarketCapabilityManifestEntry,
    MarketContractMismatch,
    MarketGovernanceFailure,
    MarketGovernanceState,
    MarketInternalFailure,
    MarketObjectNotFound,
    MarketObjectRef,
    MarketProvenance,
    MarketProvenanceIncomplete,
    MarketProvenanceProfile,
    MarketResultEnvelope,
    MarketTimeout,
    MarketUnavailable,
    OperationKind,
    OperationStatus,
    ProvenanceIncompleteBehavior,
    ProvenanceStatus,
    ProvenanceValidationContext,
    ReleaseIdentityPredicate,
    serialize,
    SideEffectClass,
    SourceRefsPredicate,
    SerializationError,
    validate_boundary_reconciliation,
    validate_capability_manifest,
    validate_provenance_profile,
)


PRODUCT_OBJECT_TYPE = "market.product"
PRODUCT_READ_CAPABILITY_ID = "market.product.read"
PRODUCT_CAPABILITY_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class MarketProductReadRequest:
    object_ref: MarketObjectRef
    correlation_id: str
    principal_id: str
    request_id: str | None = None
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.correlation_id, str) or not self.correlation_id.strip():
            raise ValueError("correlation_id must be a non-empty string")
        if self.request_id is not None and (
            not isinstance(self.request_id, str) or not self.request_id.strip()
        ):
            raise ValueError("request_id must be a non-empty string or None")
        if not isinstance(self.principal_id, str) or not self.principal_id.strip():
            raise ValueError("principal_id must be a non-empty string")
        if self.as_of is not None and (
            not isinstance(self.as_of, datetime) or self.as_of.tzinfo is None
        ):
            raise ValueError("as_of must be a timezone-aware datetime")


@dataclass(frozen=True, slots=True)
class MarketProvenanceRecord:
    source_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MarketProductRecord:
    object_ref: MarketObjectRef
    product_id: str
    revision_id: str
    supersedes_revision_id: str
    governance_state: MarketGovernanceState
    produced_at: datetime
    data_cutoff: datetime
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    judgment_material: dict[str, Any]
    provenance: MarketProvenanceRecord


@dataclass(frozen=True, slots=True)
class MarketProductPayload:
    object_ref: MarketObjectRef
    product_id: str
    revision_id: str
    supersedes_revision_id: str
    governance_state: MarketGovernanceState
    produced_at: datetime
    data_cutoff: datetime
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    judgment_material: dict[str, Any]


class MarketGovernedProductReader(Protocol):
    async def read_product(
        self, object_ref: MarketObjectRef
    ) -> MarketProductRecord | None: ...


class GovernedProductReadError(Exception):
    def __init__(self, failure: MarketBoundaryFailure) -> None:
        self.failure = failure
        super().__init__(failure.message)


def product_read_capability_manifest() -> MarketCapabilityManifestEntry:
    return MarketCapabilityManifestEntry(
        capability_id=PRODUCT_READ_CAPABILITY_ID,
        capability_version=PRODUCT_CAPABILITY_VERSION,
        operation_kind=OperationKind.READ,
        side_effect_class=SideEffectClass.READ_ONLY,
        idempotency_support=IdempotencySupport.SUPPORTED,
        market_authorization_requirement=MarketAuthorizationRequirement.GOVERNANCE_PRINCIPAL,
        may_create_product=False,
        may_change_governed_authority=False,
        may_refresh_external_data=False,
        may_mutate_market_state=False,
        input_contract_ref=MarketBoundaryCapabilityContractReference(
            contract_name="MarketProductReadRequest",
            contract_version=PRODUCT_CAPABILITY_VERSION,
        ),
        output_contract_ref=MarketBoundaryCapabilityContractReference(
            contract_name="MarketResultEnvelope",
            contract_version=PRODUCT_CAPABILITY_VERSION,
        ),
        provenance_profile_ref="market-product-judgment-v1",
    )


def product_provenance_profile() -> MarketProvenanceProfile:
    return MarketProvenanceProfile(
        profile_id="market-product-judgment-v1",
        applies_to=(PRODUCT_READ_CAPABILITY_ID,),
        predicates=(
            SourceRefsPredicate(),
            ReleaseIdentityPredicate(),
            DataCutoffPredicate((EpistemicClass.JUDGMENT,)),
        ),
        incomplete_behavior=ProvenanceIncompleteBehavior.REQUIRE_COMPLETE,
    )


def validate_product_object_ref(object_ref) -> bool:
    return (
        object_ref.object_type == PRODUCT_OBJECT_TYPE
        and isinstance(object_ref.object_id, str)
        and bool(object_ref.object_id.strip())
        and bool(object_ref.revision_id and object_ref.revision_id.strip())
    )


class MarketAnalyticalPublicBoundaryService:
    def __init__(
        self,
        reader: MarketGovernedProductReader,
        boundary_identity: MarketBoundaryIdentity,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        manifest = product_read_capability_manifest()
        manifest_validation = validate_capability_manifest(manifest)
        reconciliation = validate_boundary_reconciliation(
            boundary_identity,
            (manifest,),
        )
        if not manifest_validation.valid or not reconciliation.valid:
            failures = (*manifest_validation.failures, *reconciliation.failures)
            raise ValueError(f"Market product boundary contract is invalid: {failures}")
        self._reader = reader
        self._boundary_identity = boundary_identity
        self._clock = clock

    async def read_product(self, request) -> MarketResultEnvelope:
        if not isinstance(request, MarketProductReadRequest):
            return self._failure(
                object_ref=None,
                correlation_id="unknown",
                request_id=None,
                failure=MarketContractMismatch(
                    "Market product request type is invalid"
                ),
            )
        if not _authorized_principal(request.principal_id):
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=MarketAuthorizationDenied(
                    "A governed principal is required to read a market product"
                ),
            )
        if not validate_product_object_ref(request.object_ref):
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=MarketContractMismatch(
                    "Market product object reference is invalid"
                ),
            )

        try:
            record = await self._reader.read_product(request.object_ref)
        except GovernedProductReadError as exc:
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=exc.failure,
            )
        except TimeoutError as exc:
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=MarketTimeout("Governed product read timed out"),
            )
        except RuntimeError as exc:
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=MarketUnavailable("Governed product reader is unavailable"),
            )
        except (OSError, ValueError) as exc:
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=MarketInternalFailure("Governed product projection is invalid"),
            )
        if record is None:
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=MarketObjectNotFound("Market product was not found"),
            )
        record_failure = self._record_failure(record, request)
        if record_failure is not None:
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=record_failure,
            )

        payload = MarketProductPayload(
            object_ref=record.object_ref,
            product_id=record.product_id,
            revision_id=record.revision_id,
            supersedes_revision_id=record.supersedes_revision_id,
            governance_state=record.governance_state,
            produced_at=record.produced_at,
            data_cutoff=record.data_cutoff,
            assumptions=record.assumptions,
            limitations=record.limitations,
            judgment_material=record.judgment_material,
        )
        try:
            serialize(payload)
        except (SerializationError, TypeError, ValueError):
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=MarketInternalFailure(
                    "Market product material is not serializable"
                ),
            )

        provenance = self._validated_provenance(record, request)
        if provenance is None:
            return self._failure(
                object_ref=request.object_ref,
                correlation_id=request.correlation_id,
                request_id=request.request_id,
                failure=MarketProvenanceIncomplete(
                    "Market product provenance is incomplete"
                ),
            )
        data_state = (
            DataState.STALE
            if request.as_of is not None and request.as_of > record.data_cutoff
            else DataState.READY
        )
        now = self._clock()
        return MarketResultEnvelope(
            contract_version=PRODUCT_CAPABILITY_VERSION,
            capability_id=PRODUCT_READ_CAPABILITY_ID,
            correlation_id=request.correlation_id,
            operation_status=OperationStatus.SUCCESS,
            data_state=data_state,
            payload=payload,
            provenance=provenance,
            boundary_identity_ref=self._boundary_identity,
            produced_at=now,
            request_id=request.request_id,
        )

    def _validated_provenance(
        self, record: MarketProductRecord, request: MarketProductReadRequest
    ) -> MarketProvenance | None:
        candidate = MarketProvenance(
            provenance_status=ProvenanceStatus.PROVENANCE_INCOMPLETE,
            market_release_identity=self._boundary_identity.release_identity,
            produced_at=self._clock(),
            source_refs=record.provenance.source_refs,
            evidence_refs=record.provenance.evidence_refs,
            public_object_refs=(record.object_ref,),
            data_cutoff=record.data_cutoff,
            capability_call_ref=PRODUCT_READ_CAPABILITY_ID,
            correlation_id=request.correlation_id,
            governance_ref=record.revision_id,
        )
        context = ProvenanceValidationContext(
            capability_id=PRODUCT_READ_CAPABILITY_ID,
            epistemic_class=EpistemicClass.JUDGMENT,
            governance_state=record.governance_state,
            product_id=record.product_id,
        )
        result = validate_provenance_profile(
            product_provenance_profile(),
            candidate,
            context,
        )
        if not result.complete:
            return None
        return replace(
            candidate, provenance_status=ProvenanceStatus.PROVENANCE_COMPLETE
        )

    @staticmethod
    def _record_failure(
        record: MarketProductRecord, request: MarketProductReadRequest
    ) -> MarketBoundaryFailure | None:
        if record.governance_state not in (
            MarketGovernanceState.APPROVED,
            MarketGovernanceState.PUBLISHED,
        ):
            return MarketGovernanceFailure(
                "Market product governance state is not public"
            )
        if record.object_ref != request.object_ref:
            return MarketContractMismatch(
                "Market product object reference does not match its record"
            )
        if not _public_text(record.product_id) or not _public_text(record.revision_id):
            return MarketProvenanceIncomplete("Market product identity is incomplete")
        if record.revision_id != request.object_ref.revision_id:
            return MarketGovernanceFailure("Requested product revision is superseded")
        if (
            not isinstance(record.produced_at, datetime)
            or record.produced_at.tzinfo is None
            or not isinstance(record.data_cutoff, datetime)
            or record.data_cutoff.tzinfo is None
            or not isinstance(record.judgment_material, dict)
            or not record.judgment_material
        ):
            return MarketInternalFailure("Market product material is incomplete")
        if not isinstance(record.provenance, MarketProvenanceRecord):
            return MarketProvenanceIncomplete("Market product provenance is invalid")
        if (
            not _text_tuple(record.provenance.source_refs)
            or not record.provenance.source_refs
        ):
            return MarketProvenanceIncomplete("Market product provenance is incomplete")
        if not _text_tuple(record.provenance.evidence_refs):
            return MarketProvenanceIncomplete("Market product provenance is incomplete")
        if not _text_tuple(record.assumptions) or not _text_tuple(record.limitations):
            return MarketProvenanceIncomplete(
                "Market product disclosures are incomplete"
            )
        if not isinstance(record.supersedes_revision_id, str):
            return MarketContractMismatch(
                "Market product supersession identity is invalid"
            )
        return None

    def _failure(
        self,
        *,
        object_ref,
        correlation_id: str,
        request_id: str | None,
        failure: MarketBoundaryFailure,
    ) -> MarketResultEnvelope:
        now = self._clock()
        return MarketResultEnvelope(
            contract_version=PRODUCT_CAPABILITY_VERSION,
            capability_id=PRODUCT_READ_CAPABILITY_ID,
            correlation_id=correlation_id,
            operation_status=OperationStatus.FAILURE,
            data_state=DataState.UNAVAILABLE,
            payload=None,
            provenance=MarketProvenance(
                provenance_status=ProvenanceStatus.PROVENANCE_INCOMPLETE,
                market_release_identity=self._boundary_identity.release_identity,
                produced_at=now,
                source_refs=(),
                evidence_refs=(),
                public_object_refs=(object_ref,) if object_ref is not None else (),
                capability_call_ref=PRODUCT_READ_CAPABILITY_ID,
                correlation_id=correlation_id,
            ),
            boundary_identity_ref=self._boundary_identity,
            produced_at=now,
            request_id=request_id,
            failures=(failure,),
        )


def _authorized_principal(principal_id: str) -> bool:
    parts = principal_id.split(":") if isinstance(principal_id, str) else ()
    return (
        len(parts) >= 3
        and parts[0] == "user"
        and bool(parts[1].strip())
        and bool(parts[2].strip())
    )


def _public_text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_tuple(values: object) -> bool:
    return isinstance(values, tuple) and all(_public_text(value) for value in values)

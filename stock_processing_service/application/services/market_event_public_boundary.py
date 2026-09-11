from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID

from stock_processing_service.contracts.market_public_boundary import (
    DataState,
    IdempotencySupport,
    MarketAuthorizationRequirement,
    MarketBoundaryCapabilityContractReference,
    MarketBoundaryFailure,
    MarketBoundaryIdentity,
    MarketCapabilityManifestEntry,
    MarketContractMismatch,
    MarketGovernanceState,
    MarketObjectNotFound,
    MarketObjectRef,
    MarketProvenanceIncomplete,
    MarketProvenanceProfile,
    MarketProvenance,
    MarketResultEnvelope,
    MarketUnavailable,
    OperationKind,
    OperationStatus,
    DataCutoffPredicate,
    EpistemicClass,
    ProvenanceIncompleteBehavior,
    ProvenanceValidationContext,
    ProvenanceStatus,
    ReleaseIdentityPredicate,
    SideEffectClass,
    SourceRefsPredicate,
    validate_capability_manifest,
    validate_provenance_profile,
)


EVENT_OBJECT_TYPE = "market.event"
EVENT_READ_CAPABILITY_ID = "market.event.read"
EVENT_RESOLVE_CAPABILITY_ID = "market.event.resolve"
EVENT_CAPABILITY_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class MarketEventLineage:
    source_trace_id: str | None = None

    def __post_init__(self) -> None:
        if self.source_trace_id is not None and (
            not isinstance(self.source_trace_id, str) or not self.source_trace_id.strip()
        ):
            raise ValueError("source_trace_id must be a non-empty string or None")


@dataclass(frozen=True, slots=True)
class MarketEventRecord:
    object_ref: MarketObjectRef
    title: str
    summary: str
    content: str
    event_type: str
    source: str
    occurred_at: datetime
    data_cutoff: datetime
    governance_state: MarketGovernanceState
    lineage: MarketEventLineage = MarketEventLineage()
    source_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name, value in (
            ("title", self.title),
            ("summary", self.summary),
            ("content", self.content),
            ("event_type", self.event_type),
            ("source", self.source),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        for field_name, value in (
            ("occurred_at", self.occurred_at),
            ("data_cutoff", self.data_cutoff),
        ):
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"{field_name} must be a timezone-aware datetime")
        if not isinstance(self.governance_state, MarketGovernanceState):
            raise ValueError("governance_state has an unrecognized value")
        if not isinstance(self.lineage, MarketEventLineage):
            raise ValueError("lineage must be MarketEventLineage")
        for field_name, values in (
            ("source_refs", self.source_refs),
            ("evidence_refs", self.evidence_refs),
        ):
            if not isinstance(values, tuple) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"{field_name} must contain non-empty strings")


@dataclass(frozen=True, slots=True)
class MarketEventResolutionRecord:
    object_ref: MarketObjectRef
    governance_state: MarketGovernanceState
    source_refs: tuple[str, ...] = ()
    data_cutoff: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.source_refs, tuple) or any(
            not isinstance(value, str) or not value.strip() for value in self.source_refs
        ):
            raise ValueError("source_refs must contain non-empty strings")
        if self.data_cutoff is not None and (
            not isinstance(self.data_cutoff, datetime)
            or self.data_cutoff.tzinfo is None
        ):
            raise ValueError("data_cutoff must be a timezone-aware datetime or None")


@dataclass(frozen=True, slots=True)
class MarketEventReadRequest:
    object_ref: MarketObjectRef
    correlation_id: str
    request_id: str | None = None
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        _validate_request_metadata(
            correlation_id=self.correlation_id,
            request_id=self.request_id,
            as_of=self.as_of,
        )


@dataclass(frozen=True, slots=True)
class MarketEventResolveRequest:
    object_ref: MarketObjectRef
    correlation_id: str
    request_id: str | None = None
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        _validate_request_metadata(
            correlation_id=self.correlation_id,
            request_id=self.request_id,
            as_of=self.as_of,
        )


@dataclass(frozen=True, slots=True)
class MarketEventPayload:
    object_ref: MarketObjectRef
    title: str
    summary: str
    content: str
    event_type: str
    source: str
    occurred_at: datetime
    governance_state: MarketGovernanceState
    lineage: MarketEventLineage


@dataclass(frozen=True, slots=True)
class MarketEventResolution:
    object_ref: MarketObjectRef
    governance_state: MarketGovernanceState


class MarketEventReader(Protocol):
    async def read_event(self, object_ref: MarketObjectRef) -> MarketEventRecord | None:
        ...

    async def resolve_event(
        self, object_ref: MarketObjectRef
    ) -> MarketEventResolutionRecord | None:
        ...


def event_capability_manifests() -> tuple[MarketCapabilityManifestEntry, ...]:
    entries = []
    for capability_id in (EVENT_READ_CAPABILITY_ID, EVENT_RESOLVE_CAPABILITY_ID):
        entries.append(
            MarketCapabilityManifestEntry(
                capability_id=capability_id,
                capability_version=EVENT_CAPABILITY_VERSION,
                operation_kind=OperationKind.READ,
                side_effect_class=SideEffectClass.READ_ONLY,
                idempotency_support=IdempotencySupport.SUPPORTED,
                market_authorization_requirement=MarketAuthorizationRequirement.NONE,
                may_create_product=False,
                may_change_governed_authority=False,
                may_refresh_external_data=False,
                may_mutate_market_state=False,
                input_contract_ref=MarketBoundaryCapabilityContractReference(
                    f"{capability_id}.input", EVENT_CAPABILITY_VERSION
                ),
                output_contract_ref=MarketBoundaryCapabilityContractReference(
                    f"{capability_id}.output", EVENT_CAPABILITY_VERSION
                ),
                provenance_profile_ref="market-public-boundary:standard",
            )
        )
    return tuple(entries)


def event_provenance_profile() -> MarketProvenanceProfile:
    return MarketProvenanceProfile(
        profile_id="market-event:reported-claim:v1",
        applies_to=(EVENT_READ_CAPABILITY_ID, EVENT_RESOLVE_CAPABILITY_ID),
        predicates=(
            SourceRefsPredicate(),
            ReleaseIdentityPredicate(),
            DataCutoffPredicate((EpistemicClass.REPORTED_CLAIM,)),
        ),
        incomplete_behavior=ProvenanceIncompleteBehavior.REQUIRE_COMPLETE,
    )


def validate_event_object_ref(object_ref: MarketObjectRef) -> MarketObjectRef:
    if not isinstance(object_ref, MarketObjectRef):
        raise ValueError("object_ref must be a MarketObjectRef")
    if object_ref.object_type != EVENT_OBJECT_TYPE:
        raise ValueError(f"object_ref.object_type must be {EVENT_OBJECT_TYPE}")
    if isinstance(object_ref.object_id, int):
        raise ValueError("event object_id must not be an integer")
    if isinstance(object_ref.object_id, UUID):
        return object_ref
    if isinstance(object_ref.object_id, str):
        value = object_ref.object_id.strip()
        if value.startswith("evt_") and len(value) >= 22:
            return object_ref
        try:
            UUID(value)
        except ValueError as error:
            raise ValueError(
                "event object_id must be opaque or UUID-compatible"
            ) from error
        return object_ref
    raise ValueError("event object_id must be an opaque string or UUID")


class MarketEventPublicBoundaryService:
    def __init__(
        self,
        reader: MarketEventReader,
        boundary_identity: MarketBoundaryIdentity,
    ) -> None:
        if not callable(getattr(reader, "read_event", None)) or not callable(
            getattr(reader, "resolve_event", None)
        ):
            raise ValueError("reader must implement MarketEventReader")
        required = {EVENT_READ_CAPABILITY_ID, EVENT_RESOLVE_CAPABILITY_ID}
        if not required.issubset(set(boundary_identity.supported_capabilities)):
            raise ValueError("boundary_identity does not declare both event capabilities")
        for manifest in event_capability_manifests():
            if not validate_capability_manifest(manifest).valid:
                raise ValueError("event capability manifest is invalid")
        self._reader = reader
        self._boundary_identity = boundary_identity

    async def read_event(self, request: MarketEventReadRequest) -> MarketResultEnvelope:
        if not isinstance(request, MarketEventReadRequest):
            return self._invalid_request_failure(EVENT_READ_CAPABILITY_ID)
        return await self._execute(
            capability_id=EVENT_READ_CAPABILITY_ID,
            object_ref=request.object_ref,
            correlation_id=request.correlation_id,
            request_id=request.request_id,
            as_of=request.as_of,
            operation="read",
        )

    async def resolve_event(self, request: MarketEventResolveRequest) -> MarketResultEnvelope:
        if not isinstance(request, MarketEventResolveRequest):
            return self._invalid_request_failure(EVENT_RESOLVE_CAPABILITY_ID)
        return await self._execute(
            capability_id=EVENT_RESOLVE_CAPABILITY_ID,
            object_ref=request.object_ref,
            correlation_id=request.correlation_id,
            request_id=request.request_id,
            as_of=request.as_of,
            operation="resolve",
        )

    async def _execute(
        self,
        *,
        capability_id: str,
        object_ref: MarketObjectRef,
        correlation_id: str,
        request_id: str | None,
        as_of: datetime | None,
        operation: str,
    ) -> MarketResultEnvelope:
        try:
            valid_object_ref = validate_event_object_ref(object_ref)
        except ValueError:
            return self._failure(
                capability_id=capability_id,
                object_ref=None,
                correlation_id=correlation_id,
                request_id=request_id,
                failure=MarketContractMismatch("Event public object reference is invalid"),
            )

        try:
            if operation == "read":
                record = await self._reader.read_event(valid_object_ref)
                if record is None:
                    return self._not_found(
                        capability_id, valid_object_ref, correlation_id, request_id
                    )
                payload: MarketEventPayload | MarketEventResolution = _project_event(record)
                data_state = _data_state(record, as_of)
                source_refs = record.source_refs
                evidence_refs = record.evidence_refs
                data_cutoff = record.data_cutoff
            else:
                record = await self._reader.resolve_event(valid_object_ref)
                if record is None:
                    return self._not_found(
                        capability_id, valid_object_ref, correlation_id, request_id
                    )
                payload = MarketEventResolution(
                    object_ref=record.object_ref,
                    governance_state=record.governance_state,
                )
                data_state = (
                    DataState.STALE
                    if record.data_cutoff is not None and as_of is not None and as_of > record.data_cutoff
                    else DataState.READY
                )
                source_refs = record.source_refs
                evidence_refs = ()
                data_cutoff = record.data_cutoff
        except Exception:
            return self._failure(
                capability_id=capability_id,
                object_ref=valid_object_ref,
                correlation_id=correlation_id,
                request_id=request_id,
                failure=MarketUnavailable(f"Market event {operation} is unavailable"),
            )

        try:
            provenance = self._validated_provenance(
                capability_id=capability_id,
                object_ref=valid_object_ref,
                correlation_id=correlation_id,
                source_refs=source_refs,
                evidence_refs=evidence_refs,
                data_cutoff=data_cutoff,
                governance_state=payload.governance_state,
            )
        except Exception:
            return self._failure(
                capability_id=capability_id,
                object_ref=valid_object_ref,
                correlation_id=correlation_id,
                request_id=request_id,
                failure=MarketProvenanceIncomplete(
                    "Event provenance validation failed"
                ),
            )
        if provenance is None:
            return self._failure(
                capability_id=capability_id,
                object_ref=valid_object_ref,
                correlation_id=correlation_id,
                request_id=request_id,
                failure=MarketProvenanceIncomplete(
                    "Event provenance validation failed"
                ),
            )

        return MarketResultEnvelope(
            contract_version=EVENT_CAPABILITY_VERSION,
            capability_id=capability_id,
            correlation_id=correlation_id,
            operation_status=OperationStatus.SUCCESS,
            data_state=data_state,
            payload=payload,
            provenance=provenance,
            boundary_identity_ref=self._boundary_identity,
            produced_at=datetime.now(timezone.utc),
            request_id=request_id,
        )

    def _validated_provenance(
        self,
        *,
        capability_id: str,
        object_ref: MarketObjectRef,
        correlation_id: str,
        source_refs: tuple[str, ...],
        evidence_refs: tuple[str, ...],
        data_cutoff: datetime | None,
        governance_state: MarketGovernanceState,
    ) -> MarketProvenance | None:
        candidate = MarketProvenance(
            provenance_status=ProvenanceStatus.PROVENANCE_INCOMPLETE,
            market_release_identity=self._boundary_identity.release_identity,
            produced_at=datetime.now(timezone.utc),
            source_refs=source_refs,
            evidence_refs=evidence_refs,
            public_object_refs=(object_ref,),
            data_cutoff=data_cutoff,
            capability_call_ref=capability_id,
            correlation_id=correlation_id,
        )
        context = ProvenanceValidationContext(
            capability_id=capability_id,
            epistemic_class=EpistemicClass.REPORTED_CLAIM,
            governance_state=governance_state,
        )
        result = validate_provenance_profile(
            event_provenance_profile(),
            candidate,
            context,
        )
        if not result.complete:
            return None
        return replace(
            candidate,
            provenance_status=ProvenanceStatus.PROVENANCE_COMPLETE,
        )

    def _not_found(
        self,
        capability_id: str,
        object_ref: MarketObjectRef,
        correlation_id: str,
        request_id: str | None,
    ) -> MarketResultEnvelope:
        return self._failure(
            capability_id=capability_id,
            object_ref=object_ref,
            correlation_id=correlation_id,
            request_id=request_id,
            failure=MarketObjectNotFound("Market event object was not found"),
        )

    def _invalid_request_failure(self, capability_id: str) -> MarketResultEnvelope:
        return self._failure(
            capability_id=capability_id,
            object_ref=None,
            correlation_id="unknown",
            request_id=None,
            failure=MarketContractMismatch("Event public request type is invalid"),
        )

    def _failure(
        self,
        *,
        capability_id: str,
        object_ref: MarketObjectRef | None,
        correlation_id: str,
        request_id: str | None,
        failure: MarketBoundaryFailure,
    ) -> MarketResultEnvelope:
        now = datetime.now(timezone.utc)
        return MarketResultEnvelope(
            contract_version=EVENT_CAPABILITY_VERSION,
            capability_id=capability_id,
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
                capability_call_ref=capability_id,
                correlation_id=correlation_id,
            ),
            boundary_identity_ref=self._boundary_identity,
            produced_at=now,
            request_id=request_id,
            failures=(failure,),
        )


def _project_event(record: MarketEventRecord) -> MarketEventPayload:
    return MarketEventPayload(
        object_ref=record.object_ref,
        title=record.title,
        summary=record.summary,
        content=record.content,
        event_type=record.event_type,
        source=record.source,
        occurred_at=record.occurred_at,
        governance_state=record.governance_state,
        lineage=record.lineage,
    )


def _data_state(record: MarketEventRecord, as_of: datetime | None) -> DataState:
    if as_of is not None and as_of > record.data_cutoff:
        return DataState.STALE
    return DataState.READY


def _validate_request_metadata(
    *,
    correlation_id: str,
    request_id: str | None,
    as_of: datetime | None,
) -> None:
    if not isinstance(correlation_id, str) or not correlation_id.strip():
        raise ValueError("correlation_id must be a non-empty string")
    if request_id is not None and (
        not isinstance(request_id, str) or not request_id.strip()
    ):
        raise ValueError("request_id must be a non-empty string or None")
    if as_of is not None and (not isinstance(as_of, datetime) or as_of.tzinfo is None):
        raise ValueError("as_of must be a timezone-aware datetime")

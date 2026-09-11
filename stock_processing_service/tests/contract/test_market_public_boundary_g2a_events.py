from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from stock_processing_service.application.services.market_event_public_boundary import (
    EVENT_READ_CAPABILITY_ID,
    EVENT_RESOLVE_CAPABILITY_ID,
    MarketEventLineage,
    MarketEventReadRequest,
    MarketEventRecord,
    MarketEventResolveRequest,
    MarketEventResolutionRecord,
    MarketEventPublicBoundaryService,
    event_capability_manifests,
)
from stock_processing_service.contracts.market_public_boundary import (
    DataState,
    MarketBoundaryIdentity,
    MarketGovernanceState,
    MarketObjectRef,
    MarketReleaseIdentity,
    MarketResultEnvelope,
    OperationStatus,
    serialize,
    validate_boundary_reconciliation,
)
from stock_processing_service.infrastructure.gateway_adapters.market_event_public_reader import (
    MarketEventPublicReader,
)


NOW = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)
PUBLIC_ID = "evt_0192b42d5c6f4a2b9d3f"
OBJECT_REF = MarketObjectRef("market.event", PUBLIC_ID)
APPLICATION_SOURCE = (
    Path(__file__).parents[2]
    / "application"
    / "services"
    / "market_event_public_boundary.py"
).read_text()
READER_SOURCE = (
    Path(__file__).parents[2]
    / "infrastructure"
    / "gateway_adapters"
    / "market_event_public_reader.py"
).read_text()


def release() -> MarketReleaseIdentity:
    return MarketReleaseIdentity(
        source_identity="source:market-event:1",
        build_identity="build:market-event:1",
        artifact_identity="artifact:market-event:1",
        artifact_digest="sha256:market-event:1",
        release_manifest_ref="manifest:market-event:1",
    )


def boundary() -> MarketBoundaryIdentity:
    return MarketBoundaryIdentity(
        provider_id="market",
        public_contract_name="market-public-boundary",
        public_contract_version="1.0",
        release_identity=release(),
        supported_capabilities=(EVENT_READ_CAPABILITY_ID, EVENT_RESOLVE_CAPABILITY_ID),
        supported_object_types=("market.event",),
    )


def event_record() -> MarketEventRecord:
    return MarketEventRecord(
        object_ref=OBJECT_REF,
        title="Public event title",
        summary="Public event summary",
        content="Public event content",
        event_type="announcement",
        source="market-source",
        occurred_at=NOW,
        data_cutoff=NOW,
        governance_state=MarketGovernanceState.PUBLISHED,
        lineage=MarketEventLineage(source_trace_id="lineage:source:1"),
        source_refs=("market-source",),
        evidence_refs=("evidence:1",),
    )


class FakeEventReader:
    def __init__(
        self,
        record: MarketEventRecord | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.record = record
        self.fail = fail
        self.read_calls: list[MarketObjectRef] = []
        self.resolve_calls: list[MarketObjectRef] = []

    async def read_event(self, object_ref: MarketObjectRef) -> MarketEventRecord | None:
        self.read_calls.append(object_ref)
        if self.fail:
            raise RuntimeError("authoritative reader unavailable")
        return self.record

    async def resolve_event(
        self, object_ref: MarketObjectRef
    ) -> MarketEventResolutionRecord | None:
        self.resolve_calls.append(object_ref)
        if self.fail:
            raise RuntimeError("authoritative resolver unavailable")
        if self.record is None:
            return None
        return MarketEventResolutionRecord(
            object_ref=object_ref,
            governance_state=self.record.governance_state,
        )


class FakeDatabaseGateway:
    def __init__(self) -> None:
        self.get_event_calls: list[int] = []
        self.get_news_event_calls: list[int] = []

    async def get_event(self, event_id: int) -> dict:
        self.get_event_calls.append(event_id)
        return {
            "id": event_id,
            "news_id": 987,
            "title": "Legacy title",
            "summary": "Legacy summary",
            "content": "Legacy content",
            "source": "legacy-source",
            "url": "https://example.test/event",
            "publish_time": NOW,
            "updated_at": NOW,
            "processed": True,
            "processing_status": "complete",
        }

    async def get_news_event_for_match(self, event_id: int) -> dict:
        self.get_news_event_calls.append(event_id)
        return {
            "id": event_id,
            "news_id": 987,
            "source_category": "legacy",
            "event_type": "announcement",
            "summary": "Legacy summary",
            "entities": {},
            "causal_claim": None,
            "evidence_set": {},
            "raw_event_json": {"private": True},
            "title": "Legacy title",
            "content": "Legacy content",
        }


def service(reader: FakeEventReader) -> MarketEventPublicBoundaryService:
    return MarketEventPublicBoundaryService(reader, boundary())


async def test_g2a_at01_event_read_returns_frozen_market_result_envelope() -> None:
    result = await service(FakeEventReader(event_record())).read_event(
        MarketEventReadRequest(
            object_ref=OBJECT_REF,
            correlation_id="correlation-1",
            request_id="request-1",
        )
    )

    assert isinstance(result, MarketResultEnvelope)
    assert result.capability_id == EVENT_READ_CAPABILITY_ID
    assert result.operation_status is OperationStatus.SUCCESS
    assert result.data_state is DataState.READY
    assert result.payload.object_ref == OBJECT_REF
    assert result.payload.event_type == "announcement"
    assert result.provenance.public_object_refs == (OBJECT_REF,)


async def test_g2a_at02_event_resolve_accepts_legal_public_ref_only() -> None:
    reader = FakeEventReader(event_record())
    result = await service(reader).resolve_event(
        MarketEventResolveRequest(object_ref=OBJECT_REF, correlation_id="correlation-2")
    )

    assert result.operation_status is OperationStatus.SUCCESS
    assert result.payload.object_ref == OBJECT_REF
    assert result.payload.governance_state is MarketGovernanceState.PUBLISHED
    assert reader.resolve_calls == [OBJECT_REF]


async def test_g2a_at03_public_requests_reject_private_integer_identity() -> None:
    reader = FakeEventReader(event_record())
    private_ref = MarketObjectRef("market.event", 123)
    result = await service(reader).read_event(
        MarketEventReadRequest(object_ref=private_ref, correlation_id="correlation-3")
    )

    assert result.operation_status is OperationStatus.FAILURE
    assert result.data_state is DataState.UNAVAILABLE
    assert result.payload is None
    assert reader.read_calls == []


async def test_g2a_at04_published_event_with_stale_data_remains_legal() -> None:
    result = await service(FakeEventReader(event_record())).read_event(
        MarketEventReadRequest(
            object_ref=OBJECT_REF,
            correlation_id="correlation-4",
            as_of=NOW.replace(minute=1),
        )
    )

    assert result.operation_status is OperationStatus.SUCCESS
    assert result.data_state is DataState.STALE
    assert result.payload.governance_state is MarketGovernanceState.PUBLISHED


async def test_g2a_at05_source_trace_id_is_lineage_not_identity() -> None:
    reader = FakeEventReader(event_record())
    result = await service(reader).read_event(
        MarketEventReadRequest(object_ref=OBJECT_REF, correlation_id="correlation-5")
    )

    assert result.payload.lineage.source_trace_id == "lineage:source:1"
    assert result.payload.object_ref.object_id == PUBLIC_ID
    assert result.payload.object_ref.object_id != result.payload.lineage.source_trace_id
    assert reader.resolve_calls == []


async def test_g2a_at06_serialized_payload_contains_public_types_only() -> None:
    gateway = FakeDatabaseGateway()
    reader = MarketEventPublicReader(gateway, {PUBLIC_ID: 123})
    result = await MarketEventPublicBoundaryService(reader, boundary()).read_event(
        MarketEventReadRequest(object_ref=OBJECT_REF, correlation_id="correlation-6")
    )
    representation = serialize(result)

    assert result.payload.object_ref == OBJECT_REF
    assert gateway.get_event_calls == [123]
    assert gateway.get_news_event_calls == [123]
    for forbidden in (
        "news_event",
        "news_id",
        "event_id",
        "gateway",
        "repository",
        "raw_event_json",
    ):
        assert forbidden not in representation


async def test_g2a_at07_market_failure_does_not_fallback_to_model_memory() -> None:
    reader = FakeEventReader(event_record(), fail=True)
    result = await service(reader).read_event(
        MarketEventReadRequest(object_ref=OBJECT_REF, correlation_id="correlation-7")
    )

    assert result.operation_status is OperationStatus.FAILURE
    assert result.data_state is DataState.UNAVAILABLE
    assert result.payload is None
    assert result.failures[0].failure_type == "MarketUnavailable"
    assert reader.read_calls == [OBJECT_REF]


async def test_g2a_at08_operation_validates_without_raw_market_db_access() -> None:
    manifests = event_capability_manifests()
    reconciliation = validate_boundary_reconciliation(boundary(), manifests)
    result = await service(FakeEventReader(event_record())).resolve_event(
        MarketEventResolveRequest(object_ref=OBJECT_REF, correlation_id="correlation-8")
    )

    assert reconciliation.valid
    assert result.operation_status is OperationStatus.SUCCESS
    assert "database_service" not in APPLICATION_SOURCE
    assert "MarketUnavailable" in APPLICATION_SOURCE


async def test_not_found_fails_closed_without_reader_substitution() -> None:
    reader = FakeEventReader(None)
    result = await service(reader).resolve_event(
        MarketEventResolveRequest(object_ref=OBJECT_REF, correlation_id="correlation-9")
    )

    assert result.operation_status is OperationStatus.FAILURE
    assert result.data_state is DataState.UNAVAILABLE
    assert result.failures[0].failure_type == "MarketObjectNotFound"
    assert reader.resolve_calls == [OBJECT_REF]


def test_no_fallback_or_mock_runtime_path_is_present() -> None:
    assert "fallback" not in APPLICATION_SOURCE.lower()
    assert "mock" not in APPLICATION_SOURCE.lower()
    assert "legacy" not in APPLICATION_SOURCE.lower()
    assert "fallback" not in READER_SOURCE.lower()
    assert "mock" not in READER_SOURCE.lower()
    assert "legacy" not in READER_SOURCE.lower()
    assert "except" not in READER_SOURCE

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from stock_processing_service.application.services.analyst_workbench.approval_gate import (
    GovernedWorkbenchProduct,
)
from stock_processing_service.application.services.market_analytical_public_boundary import (
    PRODUCT_CAPABILITY_VERSION,
    PRODUCT_OBJECT_TYPE,
    PRODUCT_READ_CAPABILITY_ID,
    GovernedProductReadError,
    MarketAnalyticalPublicBoundaryService,
    MarketGovernedProductReader,
    MarketProductReadRequest,
    MarketProductRecord,
    MarketProvenanceRecord,
    product_provenance_profile,
    product_read_capability_manifest,
)
from stock_processing_service.contracts.market_public_boundary import (
    DataState,
    IdempotencySupport,
    MarketAuthorizationRequirement,
    MarketBoundaryIdentity,
    MarketGovernanceFailure,
    MarketGovernanceState,
    MarketObjectRef,
    MarketReleaseIdentity,
    MarketResultEnvelope,
    OperationKind,
    OperationStatus,
    ProvenanceStatus,
    SideEffectClass,
    serialize,
    validate_boundary_reconciliation,
    validate_capability_manifest,
    validate_provenance_profile,
    EpistemicClass,
    ProvenanceValidationContext,
)
from stock_processing_service.infrastructure.gateway_adapters.market_governed_product_public_reader import (
    MarketGovernedProductPublicReader,
)


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
PRODUCT_ID = "wgp:2026-07-10:abcdefghij"
REVISION_ID = "rev:v1:abcdef"
OBJECT_REF = MarketObjectRef(PRODUCT_OBJECT_TYPE, PRODUCT_ID, REVISION_ID)
PRINCIPAL_ID = "user:7:reader@example.test"
APPLICATION_SOURCE = (
    Path(__file__).parents[2]
    / "application"
    / "services"
    / "market_analytical_public_boundary.py"
).read_text()
READER_SOURCE = (
    Path(__file__).parents[2]
    / "infrastructure"
    / "gateway_adapters"
    / "market_governed_product_public_reader.py"
).read_text()


def release() -> MarketReleaseIdentity:
    return MarketReleaseIdentity(
        source_identity="source:market-product:1",
        build_identity="build:market-product:1",
        artifact_identity="artifact:market-product:1",
        artifact_digest="sha256:market-product:1",
        release_manifest_ref="manifest:market-product:1",
    )


def boundary() -> MarketBoundaryIdentity:
    return MarketBoundaryIdentity(
        provider_id="market",
        public_contract_name="market-public-boundary",
        public_contract_version="1.0",
        release_identity=release(),
        supported_capabilities=(PRODUCT_READ_CAPABILITY_ID,),
        supported_object_types=(PRODUCT_OBJECT_TYPE,),
    )


def product_record() -> MarketProductRecord:
    return MarketProductRecord(
        object_ref=OBJECT_REF,
        product_id=PRODUCT_ID,
        revision_id=REVISION_ID,
        supersedes_revision_id="",
        governance_state=MarketGovernanceState.PUBLISHED,
        produced_at=NOW.replace(minute=1),
        data_cutoff=NOW,
        assumptions=("market-close-input",),
        limitations=("no-intraday-recalculation",),
        judgment_material={
            "narrative": {"main_story": "Governed public judgment"},
            "playbook": {"bias": "observe"},
        },
        provenance=MarketProvenanceRecord(
            source_refs=("market-source:1",),
            evidence_refs=(),
        ),
    )


class ControlledProductReader:
    def __init__(
        self,
        record: MarketProductRecord | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.record = record
        self.error = error
        self.calls: list[MarketObjectRef] = []

    async def read_product(
        self, object_ref: MarketObjectRef
    ) -> MarketProductRecord | None:
        self.calls.append(object_ref)
        if self.error is not None:
            raise self.error
        return self.record


class ControlledApprovalGate:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.calls: list[date] = []

    def check(self, trade_date: date):
        self.calls.append(trade_date)
        return type(
            "Approval",
            (),
            {"can_generate_report": self.available, "reason": "authority unavailable"},
        )()


class ControlledGovernedPort:
    def __init__(self, product: GovernedWorkbenchProduct | None) -> None:
        self.product = product
        self.calls: list[date] = []

    def read(self, trade_date: date) -> GovernedWorkbenchProduct | None:
        self.calls.append(trade_date)
        return self.product


def governed_product() -> GovernedWorkbenchProduct:
    return GovernedWorkbenchProduct(
        product_id=PRODUCT_ID,
        revision_id=REVISION_ID,
        governance_state=MarketGovernanceState.APPROVED.value,
        produced_at=NOW.replace(minute=1).isoformat(),
        data_cutoff=NOW.isoformat(),
        supersedes_revision_id="",
        judgment_content={"narrative": {"main_story": "Governed public judgment"}},
        provenance_refs=("market-source:1",),
        assumptions=("market-close-input",),
        limitations=("no-intraday-recalculation",),
    )


def service(
    reader: MarketGovernedProductReader,
) -> MarketAnalyticalPublicBoundaryService:
    return MarketAnalyticalPublicBoundaryService(reader, boundary(), clock=lambda: NOW)


def request(**changes) -> MarketProductReadRequest:
    values = {
        "object_ref": OBJECT_REF,
        "correlation_id": "correlation-1",
        "principal_id": PRINCIPAL_ID,
        "request_id": "request-1",
    }
    values.update(changes)
    return MarketProductReadRequest(**values)


def test_g2c_at01_declares_only_read_only_product_read() -> None:
    manifest = product_read_capability_manifest()

    assert manifest.capability_id == PRODUCT_READ_CAPABILITY_ID
    assert manifest.capability_version == PRODUCT_CAPABILITY_VERSION
    assert manifest.operation_kind is OperationKind.READ
    assert manifest.side_effect_class is SideEffectClass.READ_ONLY
    assert manifest.idempotency_support is IdempotencySupport.SUPPORTED
    assert (
        manifest.market_authorization_requirement
        is MarketAuthorizationRequirement.GOVERNANCE_PRINCIPAL
    )
    assert not any(
        (
            manifest.may_create_product,
            manifest.may_change_governed_authority,
            manifest.may_refresh_external_data,
            manifest.may_mutate_market_state,
        )
    )
    assert validate_capability_manifest(manifest).valid
    assert validate_boundary_reconciliation(boundary(), (manifest,)).valid
    assert "market.evidence.inspect" not in APPLICATION_SOURCE
    assert "market.judgment.explain" not in APPLICATION_SOURCE
    assert "market.product.compare" not in APPLICATION_SOURCE
    assert "market.analysis." not in APPLICATION_SOURCE


async def test_g2c_at02_returns_deterministic_frozen_envelope() -> None:
    result = await service(ControlledProductReader(product_record())).read_product(
        request()
    )
    representation = serialize(result)
    result_again = await service(
        ControlledProductReader(product_record())
    ).read_product(request())

    assert isinstance(result, MarketResultEnvelope)
    assert result.capability_id == PRODUCT_READ_CAPABILITY_ID
    assert result.operation_status is OperationStatus.SUCCESS
    assert result.data_state is DataState.READY
    assert result.correlation_id == "correlation-1"
    assert result.request_id == "request-1"
    assert result.payload.product_id == PRODUCT_ID
    assert result.payload.revision_id == REVISION_ID
    assert result.payload.governance_state is MarketGovernanceState.PUBLISHED
    assert result.provenance.provenance_status is ProvenanceStatus.PROVENANCE_COMPLETE
    assert serialize(result_again) == representation


async def test_g2c_at03_public_serialization_uses_public_product_shape() -> None:
    approval_gate = ControlledApprovalGate()
    governed_port = ControlledGovernedPort(governed_product())
    reader = MarketGovernedProductPublicReader(approval_gate, governed_port)
    result = await service(reader).read_product(request())
    representation = serialize(result)

    assert result.operation_status is OperationStatus.SUCCESS
    assert approval_gate.calls == [date(2026, 7, 10)]
    assert governed_port.calls == [date(2026, 7, 10)]
    assert result.payload.judgment_material == governed_product().judgment_content
    for forbidden in (
        "database",
        "repository",
        "snapshot.json",
        "approval principal",
        "ReviewSnapshot",
        "Workbench",
        "M8",
    ):
        assert forbidden not in representation


async def test_g2c_at04_ready_and_stale_do_not_refresh() -> None:
    product = governed_product()
    approval_gate = ControlledApprovalGate()
    governed_port = ControlledGovernedPort(product)
    adapter = MarketGovernedProductPublicReader(approval_gate, governed_port)
    ready = await service(adapter).read_product(request())
    stale = await service(adapter).read_product(request(as_of=NOW.replace(minute=1)))

    assert ready.operation_status is OperationStatus.SUCCESS
    assert ready.data_state is DataState.READY
    assert ready.provenance.source_refs == product.provenance_refs
    assert ready.provenance.evidence_refs == ()
    assert ready.provenance.public_object_refs == (OBJECT_REF,)
    assert stale.operation_status is OperationStatus.SUCCESS
    assert stale.data_state is DataState.STALE
    assert stale.payload.revision_id == REVISION_ID
    assert approval_gate.calls == [date(2026, 7, 10), date(2026, 7, 10)]
    assert governed_port.calls == [date(2026, 7, 10), date(2026, 7, 10)]


async def test_g2c_at05_producer_completeness_cannot_bypass_validator() -> None:
    manifest = product_read_capability_manifest()
    provenance = product_provenance_profile()
    assert validate_capability_manifest(manifest).valid

    incomplete = await service(
        ControlledProductReader(
            replace(product_record(), provenance=MarketProvenanceRecord((), ()))
        )
    ).read_product(request())
    assert incomplete.operation_status is OperationStatus.FAILURE
    assert incomplete.payload is None
    assert incomplete.failures[0].failure_type == "MarketProvenanceIncomplete"

    context = ProvenanceValidationContext(
        capability_id=PRODUCT_READ_CAPABILITY_ID,
        epistemic_class=EpistemicClass.JUDGMENT,
        governance_state=MarketGovernanceState.PUBLISHED,
        product_id=PRODUCT_ID,
    )
    assert (
        validate_provenance_profile(provenance, incomplete.provenance, context).complete
        is False
    )


async def test_g2c_at06_governance_and_authority_fail_closed() -> None:
    denied = await service(ControlledProductReader(product_record())).read_product(
        request(principal_id="anonymous")
    )
    draft = await service(
        ControlledProductReader(
            replace(product_record(), governance_state=MarketGovernanceState.DRAFT)
        )
    ).read_product(request())
    superseded = await service(
        ControlledProductReader(replace(product_record(), revision_id="rev:v2:abcdef"))
    ).read_product(request())
    unavailable_gate = ControlledApprovalGate(available=False)
    adapter = MarketGovernedProductPublicReader(
        unavailable_gate, ControlledGovernedPort(governed_product())
    )
    blocked = await service(adapter).read_product(request())

    assert denied.failures[0].failure_type == "MarketAuthorizationDenied"
    assert draft.failures[0].failure_type == "MarketGovernanceFailure"
    assert superseded.failures[0].failure_type == "MarketGovernanceFailure"
    assert blocked.failures[0].failure_type == "MarketGovernanceFailure"
    assert all(
        result.payload is None for result in (denied, draft, superseded, blocked)
    )


async def test_g2c_at07_reader_and_analysis_failures_remain_typed() -> None:
    timeout = await service(
        ControlledProductReader(error=TimeoutError("reader timed out"))
    ).read_product(request())
    unavailable = await service(
        ControlledProductReader(error=RuntimeError("reader unavailable"))
    ).read_product(request())
    governance = await service(
        ControlledProductReader(
            error=GovernedProductReadError(
                MarketGovernanceFailure("authority is invalid")
            )
        )
    ).read_product(request())
    missing = await service(ControlledProductReader(None)).read_product(request())

    assert timeout.failures[0].failure_type == "MarketTimeout"
    assert unavailable.failures[0].failure_type == "MarketUnavailable"
    assert governance.failures[0].failure_type == "MarketGovernanceFailure"
    assert missing.failures[0].failure_type == "MarketObjectNotFound"
    assert all(
        result.payload is None for result in (timeout, unavailable, governance, missing)
    )


async def test_g2c_at08_invalid_requests_fail_before_reader() -> None:
    reader = ControlledProductReader(product_record())
    market_service = service(reader)
    wrong_type = await market_service.read_product(object())
    wrong_object_type = await market_service.read_product(
        request(object_ref=MarketObjectRef("market.event", PRODUCT_ID, REVISION_ID))
    )
    private_integer_id = await market_service.read_product(
        request(object_ref=MarketObjectRef(PRODUCT_OBJECT_TYPE, 123, REVISION_ID))
    )
    missing_revision = await market_service.read_product(
        request(object_ref=MarketObjectRef(PRODUCT_OBJECT_TYPE, PRODUCT_ID))
    )

    assert wrong_type.failures[0].failure_type == "MarketContractMismatch"
    assert wrong_object_type.failures[0].failure_type == "MarketContractMismatch"
    assert private_integer_id.failures[0].failure_type == "MarketContractMismatch"
    assert missing_revision.failures[0].failure_type == "MarketContractMismatch"
    assert reader.calls == []
    with pytest.raises(ValueError, match="correlation_id"):
        request(correlation_id=" ")
    with pytest.raises(ValueError, match="timezone-aware"):
        request(as_of=datetime(2026, 9, 12, 12, 0))

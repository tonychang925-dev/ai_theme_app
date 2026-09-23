"""Julia-facing, transport-neutral Market contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .provenance import MarketProvenance


# Implementation identifiers for the current public boundary.  The architecture
# requires an inspectable contract version / boundary reference but does not
# freeze these exact literals as semantic law.
MARKET_PUBLIC_CONTRACT_VERSION = "0.4.0"
MARKET_BOUNDARY_IDENTITY_REF = "market.public"


class MarketOperationStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILURE = "FAILURE"


class MarketDataState(str, Enum):
    READY = "READY"
    PENDING = "PENDING"
    STALE = "STALE"
    EMPTY = "EMPTY"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class MarketFailureKind(str, Enum):
    UNAVAILABLE = "MarketUnavailable"
    NOT_READY = "MarketNotReady"
    CONTRACT_MISMATCH = "MarketContractMismatch"
    RELEASE_MISMATCH = "MarketReleaseMismatch"
    OBJECT_NOT_FOUND = "MarketObjectNotFound"
    EVIDENCE_UNAVAILABLE = "MarketEvidenceUnavailable"
    PROVENANCE_INCOMPLETE = "MarketProvenanceIncomplete"
    ANALYSIS_PENDING = "MarketAnalysisPending"
    ANALYSIS_PARTIAL = "MarketAnalysisPartial"
    ANALYSIS_STALE = "MarketAnalysisStale"
    ANALYSIS_FAILED = "MarketAnalysisFailed"
    GOVERNANCE_FAILURE = "MarketGovernanceFailure"
    AUTHORIZATION_DENIED = "MarketAuthorizationDenied"
    TIMEOUT = "MarketTimeout"
    INTERNAL_FAILURE = "MarketInternalFailure"


@dataclass(frozen=True)
class MarketFailure:
    kind: MarketFailureKind
    code: str
    message: str


@dataclass(frozen=True)
class CapabilityMetadata:
    capability: str
    provider: str = "market"
    permission_scope: str = "market.observe"
    side_effect: str = "READ_ONLY"
    c08_required: bool = True


CAPABILITIES = {
    name: CapabilityMetadata(name)
    for name in (
        "market.event.resolve",
        "market.event.read",
        "market.product.read",
        "market.product.linkage.read",
        "market.state.read",
        "market.stock.quote.read",
        "market.analysis.read",
    )
}


@dataclass(frozen=True)
class EventResolveRequest:
    feed_date: str | None = None
    stock_id: str | None = None
    limit: int = 20


@dataclass(frozen=True)
class EventReadRequest:
    """Exact event selector.

    ``item_id`` is the canonical source-namespaced identity emitted by resolve.
    ``event_id`` is an integer compatibility selector for the news_event
    namespace only. Exactly one selector must be supplied.
    """

    event_id: int | None = None
    item_id: str | None = None


@dataclass(frozen=True)
class ProductReadRequest:
    subject_key: str


@dataclass(frozen=True)
class ProductLinkageReadRequest:
    subject_key: str
    mapping_scope: str = "pool"
    include_leaders: bool = False
    limit: int = 100


@dataclass(frozen=True)
class MarketStateReadRequest:
    trade_date: str


@dataclass(frozen=True)
class MarketAnalysisReadRequest:
    trade_date: str


@dataclass(frozen=True)
class StockQuoteReadRequest:
    stock_id: str
    trade_date: str


@dataclass(frozen=True)
class MarketResultEnvelope:
    """Canonical Julia-facing Market result.

    Operation status and data state are deliberately independent.  Domain
    failures remain typed Market outcomes; Core execution failures live on a
    separate plane before a valid envelope exists.
    """

    contract_version: str
    capability_id: str
    request_id: str | None
    correlation_id: str
    operation_status: MarketOperationStatus
    data_state: MarketDataState
    payload: Any
    provenance: "MarketProvenance"
    failures: tuple[MarketFailure, ...]
    boundary_identity_ref: str
    runtime_observation: Any | None
    produced_at: str

    def __post_init__(self) -> None:
        if not self.contract_version:
            raise ValueError("contract_version must be non-empty")
        if not self.capability_id:
            raise ValueError("capability_id must be non-empty")
        if not self.correlation_id:
            raise ValueError("correlation_id must be non-empty")
        if not self.boundary_identity_ref:
            raise ValueError("boundary_identity_ref must be non-empty")
        if not self.produced_at:
            raise ValueError("produced_at must be non-empty")
        if (
            self.operation_status is MarketOperationStatus.FAILURE
            and self.data_state is MarketDataState.EMPTY
        ):
            raise ValueError(
                "FAILURE + EMPTY is forbidden by the Market public contract"
            )

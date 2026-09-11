from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .capabilities import MarketRuntimeObservation
from .identity import MarketBoundaryIdentity
from .provenance import MarketProvenance
from .vocabulary import DataState, OperationStatus


@dataclass(frozen=True, slots=True)
class MarketResultEnvelope:
    contract_version: str
    capability_id: str
    correlation_id: str
    operation_status: OperationStatus
    data_state: DataState
    payload: Any
    provenance: MarketProvenance
    boundary_identity_ref: MarketBoundaryIdentity
    produced_at: datetime
    request_id: str | None = None
    failures: tuple[Any, ...] = ()
    runtime_observation: MarketRuntimeObservation | None = None

    def __post_init__(self) -> None:
        if (
            self.operation_status is OperationStatus.FAILURE
            and self.data_state is DataState.EMPTY
        ):
            raise ValueError("FAILURE must not be paired with EMPTY")
        if not isinstance(self.provenance, MarketProvenance):
            raise ValueError("provenance must be MarketProvenance")
        if not isinstance(self.boundary_identity_ref, MarketBoundaryIdentity):
            raise ValueError("boundary_identity_ref must be MarketBoundaryIdentity")

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from stock_processing_service.application.services.analyst_workbench.approval_gate import (
    ApprovalGate,
)
from stock_processing_service.application.services.market_analytical_public_boundary import (
    GovernedProductReadError,
    MarketProductRecord,
    MarketProvenanceRecord,
    PRODUCT_OBJECT_TYPE,
    validate_product_object_ref,
)
from stock_processing_service.contracts.market_public_boundary import (
    MarketGovernanceFailure,
    MarketGovernanceState,
    MarketObjectRef,
)


class GovernedProductPort(Protocol):
    def read(self, trade_date: date): ...


class MarketGovernedProductPublicReader:
    def __init__(
        self,
        approval_gate: ApprovalGate,
        governed_product_port: GovernedProductPort,
    ) -> None:
        self._approval_gate = approval_gate
        self._governed_product_port = governed_product_port

    async def read_product(self, object_ref: MarketObjectRef) -> MarketProductRecord:
        if not validate_product_object_ref(object_ref):
            raise GovernedProductReadError(
                MarketGovernanceFailure("Market product authority reference is invalid")
            )
        trade_date = _trade_date(object_ref.object_id)
        approval = self._approval_gate.check(trade_date)
        if not approval.can_generate_report:
            raise GovernedProductReadError(
                MarketGovernanceFailure("Governed product authority is unavailable")
            )
        product = self._governed_product_port.read(trade_date)
        if product is None:
            raise GovernedProductReadError(
                MarketGovernanceFailure("Governed product authority is missing")
            )
        if product.product_id != object_ref.object_id:
            raise GovernedProductReadError(
                MarketGovernanceFailure("Governed product identity does not match")
            )
        if product.revision_id != object_ref.revision_id:
            raise GovernedProductReadError(
                MarketGovernanceFailure("Requested product revision is superseded")
            )
        try:
            governance_state = MarketGovernanceState(product.governance_state)
            if governance_state not in (
                MarketGovernanceState.APPROVED,
                MarketGovernanceState.PUBLISHED,
            ):
                raise ValueError("governance state is not public")
            produced_at = _aware_datetime(product.produced_at, "produced_at")
            data_cutoff = _aware_datetime(product.data_cutoff, "data_cutoff")
        except (TypeError, ValueError) as exc:
            raise GovernedProductReadError(
                MarketGovernanceFailure("Governed product authority is invalid")
            ) from exc

        try:
            return MarketProductRecord(
                object_ref=object_ref,
                product_id=product.product_id,
                revision_id=product.revision_id,
                supersedes_revision_id=product.supersedes_revision_id,
                governance_state=governance_state,
                produced_at=produced_at,
                data_cutoff=data_cutoff,
                assumptions=tuple(product.assumptions),
                limitations=tuple(product.limitations),
                judgment_material=dict(product.judgment_content),
                provenance=MarketProvenanceRecord(
                    source_refs=tuple(product.provenance_refs),
                    evidence_refs=(),
                ),
            )
        except (TypeError, ValueError) as exc:
            raise GovernedProductReadError(
                MarketGovernanceFailure("Governed product projection is invalid")
            ) from exc


def _trade_date(product_id: str) -> date:
    try:
        prefix, trade_date_text, _digest = product_id.split(":", maxsplit=2)
        if prefix != "wgp" or not _digest:
            raise ValueError("unexpected product identity prefix")
        return date.fromisoformat(trade_date_text)
    except (TypeError, ValueError) as exc:
        raise GovernedProductReadError(
            MarketGovernanceFailure("Market product identity is invalid")
        ) from exc


def _aware_datetime(value: str, field_name: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include a timezone")
    return parsed

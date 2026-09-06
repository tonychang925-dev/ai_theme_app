"""AT-R2 thin DomainIntelligenceAdapter facade.

The facade dispatches by exact provider-native operation ID only. It does not
interpret user text, call LLMs, expose HTTP/MCP transport, or import Julia Core.
"""

from __future__ import annotations

from typing import Any, Mapping

from .contracts import AdapterRequest, DomainObservationEnvelope, ValidationError
from .operations.alerts import MarketAlertsOperation
from .operations.event_read import MarketEventReadOperation
from .operations.event_resolve import MarketEventResolveOperation
from .operations.snapshot import MarketSnapshotOperation


class DomainIntelligenceAdapter:
    """Provider-native read-only adapter facade for ai_theme_app domain data."""

    def __init__(
        self,
        *,
        market_context_exporter: object | None = None,
        database_gateway: object | None = None,
        workbench_base_dir: str | None = None,
        clock: object | None = None,
    ) -> None:
        self._operations = {
            "market.snapshot": MarketSnapshotOperation(
                exporter=market_context_exporter,
                clock=clock,
            ),
            "market.alerts": MarketAlertsOperation(
                workbench_base_dir=workbench_base_dir,
                clock=clock,
            ),
            "market.event.read": MarketEventReadOperation(
                database_gateway=database_gateway,
                clock=clock,
            ),
            "market.event.resolve": MarketEventResolveOperation(
                database_gateway=database_gateway,
                clock=clock,
            ),
        }

    @property
    def supported_operations(self) -> tuple[str, ...]:
        return tuple(sorted(self._operations))

    async def execute(self, request: AdapterRequest | Mapping[str, Any]) -> DomainObservationEnvelope:
        """Execute an exact operation request and return a provider-native envelope."""
        req = request if isinstance(request, AdapterRequest) else AdapterRequest.from_dict(request)
        operation = self._operations.get(req.operation)
        if operation is None:
            # AdapterRequest currently validates the catalog first; keep this
            # branch as a defensive invariant for future catalog evolution.
            raise ValidationError(f"unsupported operation: {req.operation}")
        return await operation.execute(req)


__all__ = ["DomainIntelligenceAdapter"]

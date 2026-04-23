from __future__ import annotations

from typing import Any, Protocol

from stock_processing_service.contracts.events import EventEnvelope


class StockEventPort(Protocol):
    async def publish_stock_processing_event(self, event: EventEnvelope[Any]) -> str: ...

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str) -> str: ...


# Backward-compatible alias
EventPorts = StockEventPort

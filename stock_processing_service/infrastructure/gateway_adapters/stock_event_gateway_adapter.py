from __future__ import annotations

from dataclasses import asdict
from typing import Any

from stock_processing_service.contracts.events import DeadLetterPayload, EventEnvelope
from stock_processing_service.ports.database_gateway_stock_facade import DatabaseGatewayStockFacade


class StockEventGatewayAdapter:
    def __init__(self, db_gateway: DatabaseGatewayStockFacade) -> None:
        self._db = db_gateway

    async def publish_stock_processing_event(self, event: EventEnvelope[Any]) -> str:
        payload = asdict(event)
        return await self._db.publish_stock_processing_event(event.event_name, payload)

    async def record_dead_letter(self, event_name: str, payload: dict[str, Any], reason: str) -> str:
        dlq = DeadLetterPayload(original_event_name=event_name, reason=reason, payload_excerpt=payload)
        return await self._db.record_dead_letter(event_name, asdict(dlq), reason)

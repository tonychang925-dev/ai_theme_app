from __future__ import annotations

from typing import Any


class StockIdempotencyGatewayAdapter:
    def __init__(self, db_gateway: Any) -> None:
        self._db = db_gateway

    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        return bool(await self._db.acquire_job_idempotency(job_key, ttl_seconds))

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None) -> None:
        await self._db.mark_job_completed(job_key, metadata or {})

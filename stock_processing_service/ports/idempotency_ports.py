from __future__ import annotations

from typing import Any, Protocol


class IdempotencyPort(Protocol):
    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool: ...

    async def mark_job_completed(self, job_key: str, metadata: dict[str, Any] | None = None) -> None: ...


# Backward-compatible alias
IdempotencyPorts = IdempotencyPort

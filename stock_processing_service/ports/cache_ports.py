from __future__ import annotations

from typing import Any, Protocol


class StockCachePort(Protocol):
    async def get(self, key: str) -> Any | None: ...

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None: ...

    async def delete(self, key: str) -> int: ...

    async def invalidate_pattern(self, pattern: str) -> int: ...


# Backward-compatible alias
CachePorts = StockCachePort

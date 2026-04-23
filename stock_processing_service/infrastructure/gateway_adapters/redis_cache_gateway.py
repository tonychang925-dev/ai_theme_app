from __future__ import annotations

from typing import Any


class RedisCacheGateway:
    """Adapter for cache operations through RedisCachedManager/gateway."""

    def __init__(self, cache_client: Any) -> None:
        self._cache = cache_client

    async def get(self, key: str) -> Any | None:
        if self._cache is None:
            return None
        return await self._cache.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        if self._cache is None:
            return
        if ttl_seconds is None:
            await self._cache.set(key, value)
        else:
            await self._cache.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> int:
        if self._cache is None:
            return 0
        result = await self._cache.delete(key)
        return int(result or 0)

    async def invalidate_pattern(self, pattern: str) -> int:
        if self._cache is None:
            return 0
        result = await self._cache.invalidate_pattern(pattern)
        return int(result or 0)

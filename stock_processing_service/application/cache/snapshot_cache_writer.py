from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

from stock_processing_service.ports import StockCachePort


class SnapshotCacheWriter:
    TTL_2H = 2 * 3600
    TTL_4H = 4 * 3600
    TTL_24H = 24 * 3600
    TTL_7D = 7 * 24 * 3600

    def __init__(self, cache_port: StockCachePort | None) -> None:
        self._cache_port = cache_port

    async def write_row_cache(self, key: str, row: Any, ttl_seconds: int = TTL_24H) -> bool:
        if self._cache_port is None:
            return False
        payload = asdict(row) if is_dataclass(row) else row
        await self._cache_port.set(key, payload, ttl_seconds=ttl_seconds)
        return True

    async def write_grouped_cache(self, key: str, rows: list[Any], ttl_seconds: int = TTL_24H) -> bool:
        if self._cache_port is None:
            return False
        payload = [asdict(row) if is_dataclass(row) else row for row in rows]
        await self._cache_port.set(key, payload, ttl_seconds=ttl_seconds)
        return True

    async def write_value_cache(self, key: str, value: Any, ttl_seconds: int = TTL_24H) -> bool:
        if self._cache_port is None:
            return False
        await self._cache_port.set(key, value, ttl_seconds=ttl_seconds)
        return True

    async def write_current_version(self, prefix: str, trade_date: date, snapshot_version: str) -> bool:
        return await self.write_value_cache(
            f"{prefix}:current:{trade_date}",
            snapshot_version,
            ttl_seconds=self.TTL_24H,
        )


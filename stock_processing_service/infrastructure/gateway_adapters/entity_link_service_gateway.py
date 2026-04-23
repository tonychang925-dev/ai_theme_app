from __future__ import annotations

from typing import Any


class EntityLinkServiceGateway:
    """Adapter for entity normalization service."""

    def __init__(self, linker: Any) -> None:
        self._linker = linker

    async def map_company_to_stock(self, company_name: str) -> str | None:
        if self._linker is None:
            return None
        result = await self._linker.map_company_to_stock(company_name)
        return str(result) if result else None

    async def map_theme_to_subject_key(self, theme_name: str) -> str | None:
        if self._linker is None:
            return None
        result = await self._linker.map_theme_to_subject_key(theme_name)
        return str(result) if result else None

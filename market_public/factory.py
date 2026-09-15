"""Market-owned private composition for the Julia-facing provider."""
from __future__ import annotations

import os

from .provider import _MarketPublicProvider


class MarketPublicFactory:
    @staticmethod
    def create(*, database_url: str | None = None):
        # Precedence is explicit override > Market-specific compatibility alias
        # > deployed canonical configuration.  No implicit localhost value is
        # selected here; an absent value is passed through to the repository's
        # existing deterministic configuration behavior.
        configured_url = (
            database_url
            or os.getenv("MARKET_DATABASE_URL")
            or os.getenv("DATABASE_URL")
        )
        return _MarketPublicProvider(
            _LazyPhase1Repository(configured_url)
        )


class _LazyPhase1Repository:
    """Private adapter: import and construct the real repository on execution."""

    def __init__(self, database_url: str | None):
        self._database_url = database_url
        self._repository = None

    def _bound(self):
        if self._repository is None:
            from theme_service.repositories.phase1_read_repository import Phase1ReadRepository
            self._repository = Phase1ReadRepository(database_url=self._database_url)
        return self._repository

    async def fetch_intel_feed(self, **kwargs):
        return await self._bound().fetch_intel_feed(**kwargs)

    async def fetch_theme_detail(self, subject_key):
        return await self._bound().fetch_theme_detail(subject_key)

    async def close(self):
        if self._repository is not None:
            await self._repository.close()

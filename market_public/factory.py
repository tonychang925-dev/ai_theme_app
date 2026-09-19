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
            from .private.phase1_market_state_repository import (
                Phase1MarketStateReadRepository,
            )
            self._repository = Phase1MarketStateReadRepository(
                database_url=self._database_url
            )
        return self._repository

    async def fetch_intel_feed(self, **kwargs):
        return await self._bound().fetch_intel_feed(**kwargs)

    async def fetch_theme_detail(self, subject_key):
        return await self._bound().fetch_theme_detail(subject_key)

    async def fetch_stocks_by_theme(
        self,
        subject_key,
        mapping_scope="pool",
        include_leaders=False,
        limit=100,
    ):
        return await self._bound().fetch_stocks_by_theme(
            subject_key=subject_key,
            mapping_scope=mapping_scope,
            include_leaders=include_leaders,
            limit=limit,
        )

    async def get_existing_post_market_recap_snapshot(self, trade_date):
        return await self._bound().get_existing_post_market_recap_snapshot(trade_date)

    async def close(self):
        if self._repository is not None:
            await self._repository.close()

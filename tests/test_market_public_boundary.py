import sys
import types

import pytest

from market_public import (
    CAPABILITIES, EventReadRequest, EventResolveRequest, MarketPublicFactory,
    MarketStatus, ProductReadRequest,
)


def test_exact_capability_metadata():
    assert set(CAPABILITIES) == {"market.event.resolve", "market.event.read", "market.product.read"}
    for metadata in CAPABILITIES.values():
        assert (metadata.provider, metadata.permission_scope, metadata.side_effect, metadata.c08_required) == ("market", "market.observe", "READ_ONLY", True)


def test_factory_owns_private_composition():
    provider = MarketPublicFactory.create(database_url="postgresql://example.invalid/market")
    assert provider._repository.__class__.__name__ == "_LazyPhase1Repository"
    assert not hasattr(__import__("market_public"), "MarketPublicProvider")


class RepoFixture:
    def __init__(self):
        self.calls = []

    async def fetch_intel_feed(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("item_type") == "event" and kwargs.get("limit") == 200:
            return [{"item_id": "event:7:theme:1", "title": "real event"}]
        return [{"item_id": "event:8:theme:1", "title": "real resolved event"}]

    async def fetch_theme_detail(self, subject_key):
        return {"subject_key": subject_key, "theme_name": "real product"}

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_provider_unit_execution_with_isolated_repository():
    from market_public.provider import _MarketPublicProvider
    provider = _MarketPublicProvider(RepoFixture())
    assert (await provider.execute("market.event.resolve", EventResolveRequest())).status is MarketStatus.SUCCESS
    assert (await provider.execute("market.event.read", EventReadRequest(7))).data["item_id"] == "event:7:theme:1"
    assert (await provider.execute("market.product.read", ProductReadRequest("theme:1"))).data["theme_name"] == "real product"


@pytest.mark.asyncio
async def test_dependency_failure_is_typed_and_closed():
    class Broken(RepoFixture):
        async def fetch_theme_detail(self, subject_key):
            raise ConnectionError("database unavailable")
    from market_public.provider import _MarketPublicProvider
    result = await _MarketPublicProvider(Broken()).execute("market.product.read", ProductReadRequest("theme:1"))
    assert result.status is MarketStatus.DEPENDENCY_UNAVAILABLE
    assert result.data is None


@pytest.mark.asyncio
async def test_invalid_requests_do_not_fallback():
    from market_public.provider import _MarketPublicProvider
    result = await _MarketPublicProvider(RepoFixture()).execute("market.event.read", EventReadRequest(0))
    assert result.status is MarketStatus.INVALID_REQUEST
    assert result.data is None


@pytest.mark.asyncio
async def test_event_read_missing_id_is_not_found():
    from market_public.provider import _MarketPublicProvider
    result = await _MarketPublicProvider(TestRepo()).execute("market.event.read", EventReadRequest(999))
    assert result.status is MarketStatus.NOT_FOUND


@pytest.mark.asyncio
async def test_feed_date_and_limit_validation_precedes_repository():
    from market_public.provider import _MarketPublicProvider
    repo = RepoFixture()
    provider = _MarketPublicProvider(repo)
    for request in (
        EventResolveRequest(feed_date="2026-02-30"),
        EventResolveRequest(feed_date="20260201"),
        EventResolveRequest(limit=0),
        EventResolveRequest(limit=-1),
        EventResolveRequest(limit=201),
        EventResolveRequest(limit=10**9),
    ):
        result = await provider.execute("market.event.resolve", request)
        assert result.status is MarketStatus.INVALID_REQUEST
    assert repo.calls == []


@pytest.mark.asyncio
async def test_real_db_connection_failure_classification():
    from market_public.provider import _MarketPublicProvider
    class PostgresConnectionError(ConnectionError):
        pass
    class Broken(RepoFixture):
        async def fetch_theme_detail(self, subject_key):
            raise PostgresConnectionError("connection refused")
    result = await _MarketPublicProvider(Broken()).execute("market.product.read", ProductReadRequest("theme:1"))
    assert result.status is MarketStatus.DEPENDENCY_UNAVAILABLE


@pytest.mark.asyncio
async def test_stock_scoped_resolve_excludes_unfilterable_cdp_events():
    from market_public.provider import _MarketPublicProvider
    class Mixed(RepoFixture):
        async def fetch_intel_feed(self, **kwargs):
            return [
                {"item_id": "event:11:theme:1", "source_channel": "realtime_news"},
                {"item_id": "event:12:theme:1", "source_channel": "jyhf_cdp"},
            ]
    result = await _MarketPublicProvider(Mixed()).execute(
        "market.event.resolve", EventResolveRequest(stock_id="600000")
    )
    assert result.status is MarketStatus.SUCCESS
    assert sum(row.get("source_channel") == "jyhf_cdp" for row in result.data) == 0


@pytest.mark.asyncio
async def test_real_domain_binding_without_database(monkeypatch):
    """Factory binds the current-main repository class without caller injection."""
    monkeypatch.setitem(sys.modules, "asyncpg", types.SimpleNamespace(Pool=object))
    provider = MarketPublicFactory.create(database_url="postgresql://example.invalid/market")
    real_repository = provider._repository._bound()
    assert real_repository.__class__.__name__ == "Phase1ReadRepository"
    assert real_repository.__class__.__module__ == "theme_service.repositories.phase1_read_repository"

    async def fake_detail(subject_key):
        return {"subject_key": subject_key, "source": "current-main-domain"}

    monkeypatch.setattr(real_repository, "fetch_theme_detail", fake_detail)
    result = await provider.execute("market.product.read", ProductReadRequest("theme:1"))
    assert result.status is MarketStatus.SUCCESS
    assert result.data["source"] == "current-main-domain"

import pytest

from market_public import (
    CAPABILITIES, EventReadRequest, EventResolveRequest, MarketPublicFactory,
    MarketPublicProvider, MarketStatus, ProductReadRequest,
)


def test_exact_capability_metadata():
    assert set(CAPABILITIES) == {"market.event.resolve", "market.event.read", "market.product.read"}
    for metadata in CAPABILITIES.values():
        assert (metadata.provider, metadata.permission_scope, metadata.side_effect, metadata.c08_required) == ("market", "market.observe", "READ_ONLY", True)


def test_factory_owns_private_composition():
    provider = MarketPublicFactory.create(database_url="postgresql://example.invalid/market")
    assert isinstance(provider, MarketPublicProvider)
    assert provider._repository.__class__.__name__ == "_LazyPhase1Repository"


class Repo:
    async def fetch_intel_feed(self, **kwargs):
        if kwargs.get("item_type") == "event" and kwargs.get("limit") == 100:
            return [{"event_id": 7, "title": "real event"}]
        return [{"event_id": 8, "title": "real resolved event"}]

    async def fetch_theme_detail(self, subject_key):
        return {"subject_key": subject_key, "theme_name": "real product"}

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_real_domain_execution_through_public_provider():
    provider = MarketPublicProvider(Repo())
    assert (await provider.execute("market.event.resolve", EventResolveRequest())).status is MarketStatus.SUCCESS
    assert (await provider.execute("market.event.read", EventReadRequest(7))).data["event_id"] == 7
    assert (await provider.execute("market.product.read", ProductReadRequest("theme:1"))).data["theme_name"] == "real product"


@pytest.mark.asyncio
async def test_dependency_failure_is_typed_and_closed():
    class Broken(Repo):
        async def fetch_theme_detail(self, subject_key):
            raise ConnectionError("database unavailable")
    result = await MarketPublicProvider(Broken()).execute("market.product.read", ProductReadRequest("theme:1"))
    assert result.status is MarketStatus.DEPENDENCY_UNAVAILABLE
    assert result.data is None


@pytest.mark.asyncio
async def test_invalid_requests_do_not_fallback():
    result = await MarketPublicProvider(Repo()).execute("market.event.read", EventReadRequest(0))
    assert result.status is MarketStatus.INVALID_REQUEST
    assert result.data is None

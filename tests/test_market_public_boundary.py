import sys
import types
from dataclasses import replace

import pytest

import market_public
from market_public import (
    CAPABILITIES,
    EventReadRequest,
    EventResolveRequest,
    MarketDataState,
    MarketFailureKind,
    MarketOperationStatus,
    MarketProvenance,
    MarketProvenanceProfile,
    MarketProvenanceStatus,
    MarketPublicFactory,
    MarketReleaseIdentity,
    ProductReadRequest,
    ProvenancePredicate,
)


def test_exact_capability_metadata():
    assert set(CAPABILITIES) == {
        "market.event.resolve",
        "market.event.read",
        "market.product.read",
        "market.product.linkage.read",
        "market.state.read",
        "market.stock.quote.read",
    }
    for metadata in CAPABILITIES.values():
        assert (
            metadata.provider,
            metadata.permission_scope,
            metadata.side_effect,
            metadata.c08_required,
        ) == ("market", "market.observe", "READ_ONLY", True)


def test_public_exports_use_canonical_result_truth_only():
    assert hasattr(market_public, "MarketResultEnvelope")
    assert hasattr(market_public, "MarketOperationStatus")
    assert hasattr(market_public, "MarketDataState")
    assert hasattr(market_public, "MarketFailureKind")
    assert not hasattr(market_public, "MarketResult")
    assert not hasattr(market_public, "MarketStatus")


def test_factory_owns_private_composition():
    provider = MarketPublicFactory.create(
        database_url="postgresql://example.invalid/market"
    )
    assert provider._repository.__class__.__name__ == "_LazyPhase1Repository"
    assert not hasattr(__import__("market_public"), "MarketPublicProvider")


def test_database_url_only_factory_binding(monkeypatch):
    monkeypatch.delenv("MARKET_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://deployed/market")
    provider = MarketPublicFactory.create()
    assert provider._repository._database_url == "postgresql://deployed/market"


def test_explicit_database_url_precedence(monkeypatch):
    monkeypatch.setenv("MARKET_DATABASE_URL", "postgresql://market/override")
    monkeypatch.setenv("DATABASE_URL", "postgresql://deployed/market")
    provider = MarketPublicFactory.create(database_url="postgresql://explicit/market")
    assert provider._repository._database_url == "postgresql://explicit/market"


def test_market_database_url_precedes_database_url(monkeypatch):
    monkeypatch.setenv("MARKET_DATABASE_URL", "postgresql://market/override")
    monkeypatch.setenv("DATABASE_URL", "postgresql://deployed/market")
    provider = MarketPublicFactory.create()
    assert provider._repository._database_url == "postgresql://market/override"


def test_no_database_env_preserves_repository_default(monkeypatch):
    monkeypatch.delenv("MARKET_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    provider = MarketPublicFactory.create()
    assert provider._repository._database_url is None


class RepoFixture:
    def __init__(self):
        self.calls = []

    async def fetch_intel_feed(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("item_type") == "event" and kwargs.get("limit") == 200:
            return [{"item_id": "event:7:theme:1", "title": "real event"}]
        return [{"item_id": "event:8:theme:1", "title": "real resolved event"}]

    async def fetch_intel_event_by_item_id(self, item_id):
        self.calls.append({"exact_item_id": item_id})
        if item_id == "event:7:theme:1":
            return {"item_id": item_id, "title": "real event"}
        return None

    async def fetch_intel_event_by_event_id(self, event_id):
        self.calls.append({"exact_news_event_id": event_id})
        if event_id == 7:
            return {"item_id": "event:7:theme:1", "title": "real event"}
        return None

    async def fetch_theme_detail(self, subject_key):
        return {"subject_key": subject_key, "theme_name": "real product"}

    async def close(self):
        pass


@pytest.mark.asyncio
async def test_provider_unit_execution_with_isolated_repository():
    from market_public.provider import _MarketPublicProvider

    provider = _MarketPublicProvider(RepoFixture())

    resolved = await provider.execute("market.event.resolve", EventResolveRequest())
    assert resolved.operation_status is MarketOperationStatus.SUCCESS
    assert resolved.data_state is MarketDataState.READY
    assert resolved.payload[0]["item_id"] == "event:8:theme:1"

    event = await provider.execute("market.event.read", EventReadRequest(7))
    assert event.operation_status is MarketOperationStatus.SUCCESS
    assert event.data_state is MarketDataState.READY
    assert event.payload["item_id"] == "event:7:theme:1"

    product = await provider.execute(
        "market.product.read", ProductReadRequest("theme:1")
    )
    assert product.operation_status is MarketOperationStatus.SUCCESS
    assert product.data_state is MarketDataState.READY
    assert product.payload["theme_name"] == "real product"


@pytest.mark.asyncio
async def test_event_resolve_valid_zero_match_is_success_empty():
    class Empty(RepoFixture):
        async def fetch_intel_feed(self, **kwargs):
            return []

    from market_public.provider import _MarketPublicProvider

    result = await _MarketPublicProvider(Empty()).execute(
        "market.event.resolve", EventResolveRequest()
    )
    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.EMPTY
    assert result.payload == []
    assert result.failures == ()


@pytest.mark.asyncio
async def test_dependency_failure_is_typed_and_closed():
    class Broken(RepoFixture):
        async def fetch_theme_detail(self, subject_key):
            raise ConnectionError("database unavailable")

    from market_public.provider import _MarketPublicProvider

    result = await _MarketPublicProvider(Broken()).execute(
        "market.product.read", ProductReadRequest("theme:1")
    )
    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.UNAVAILABLE
    assert result.payload is None
    assert result.failures[0].kind is MarketFailureKind.UNAVAILABLE


@pytest.mark.asyncio
async def test_invalid_requests_are_contract_mismatch_not_applicable():
    from market_public.provider import _MarketPublicProvider

    result = await _MarketPublicProvider(RepoFixture()).execute(
        "market.event.read", EventReadRequest(0)
    )
    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.NOT_APPLICABLE
    assert result.payload is None
    assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH


@pytest.mark.asyncio
async def test_unknown_capability_is_contract_mismatch_not_applicable():
    from market_public.provider import _MarketPublicProvider

    result = await _MarketPublicProvider(RepoFixture()).execute(
        "market.unknown", object()
    )
    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.NOT_APPLICABLE
    assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH


@pytest.mark.asyncio
async def test_event_read_missing_id_is_object_not_found_not_applicable():
    from market_public.provider import _MarketPublicProvider

    result = await _MarketPublicProvider(RepoFixture()).execute(
        "market.event.read", EventReadRequest(999)
    )
    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.NOT_APPLICABLE
    assert result.failures[0].kind is MarketFailureKind.OBJECT_NOT_FOUND


@pytest.mark.asyncio
async def test_event_id_is_news_only_and_never_falls_back_to_jyhf_identity():
    from market_public.provider import _MarketPublicProvider

    class JyhfAtNewsId(RepoFixture):
        async def fetch_intel_event_by_item_id(self, item_id):
            self.calls.append({"exact_item_id": item_id})
            if item_id == "event:jyhf_cdp:999":
                return {"item_id": item_id, "title": "JYHF event"}
            return None

    repo = JyhfAtNewsId()
    result = await _MarketPublicProvider(repo).execute(
        "market.event.read", EventReadRequest(999)
    )

    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.NOT_APPLICABLE
    assert result.payload is None
    assert result.failures[0].kind is MarketFailureKind.OBJECT_NOT_FOUND
    assert result.failures[0].code == "event_not_found"
    assert repo.calls == [{"exact_news_event_id": 999}]
    assert (
        sum(call.get("exact_item_id") == "event:jyhf_cdp:999" for call in repo.calls)
        == 0
    )


@pytest.mark.asyncio
async def test_event_read_uses_exact_namespaced_identity_without_feed_scan():
    from market_public.provider import _MarketPublicProvider

    repo = RepoFixture()
    result = await _MarketPublicProvider(repo).execute(
        "market.event.read", EventReadRequest(item_id="event:7:theme:1")
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.payload["item_id"] == "event:7:theme:1"
    assert repo.calls == [{"exact_item_id": "event:7:theme:1"}]


@pytest.mark.asyncio
async def test_event_read_requires_exactly_one_selector_and_rejects_malformed_identity():
    from market_public.provider import _MarketPublicProvider

    repo = RepoFixture()
    provider = _MarketPublicProvider(repo)
    for request in (
        EventReadRequest(),
        EventReadRequest(event_id=7, item_id="event:7:theme:1"),
        EventReadRequest(item_id="event:7"),
        EventReadRequest(item_id="raw:event:7"),
    ):
        result = await provider.execute("market.event.read", request)
        assert result.operation_status is MarketOperationStatus.FAILURE
        assert result.data_state is MarketDataState.NOT_APPLICABLE
        assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH
    assert repo.calls == []


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
        assert result.operation_status is MarketOperationStatus.FAILURE
        assert result.data_state is MarketDataState.NOT_APPLICABLE
        assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH
    assert repo.calls == []


@pytest.mark.asyncio
async def test_real_db_connection_failure_classification():
    from market_public.provider import _MarketPublicProvider

    class PostgresConnectionError(ConnectionError):
        pass

    class Broken(RepoFixture):
        async def fetch_theme_detail(self, subject_key):
            raise PostgresConnectionError("connection refused")

    result = await _MarketPublicProvider(Broken()).execute(
        "market.product.read", ProductReadRequest("theme:1")
    )
    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.UNAVAILABLE
    assert result.failures[0].kind is MarketFailureKind.UNAVAILABLE


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
    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert sum(row.get("source_channel") == "jyhf_cdp" for row in result.payload) == 0


@pytest.mark.asyncio
async def test_request_and_correlation_identity_are_preserved_when_supplied():
    from market_public.provider import _MarketPublicProvider

    result = await _MarketPublicProvider(RepoFixture()).execute(
        "market.product.read",
        ProductReadRequest("theme:1"),
        request_id="req-1",
        correlation_id="corr-1",
    )
    assert result.request_id == "req-1"
    assert result.correlation_id == "corr-1"
    assert result.provenance.correlation_id == "corr-1"


@pytest.mark.asyncio
async def test_current_provider_does_not_fabricate_release_provenance_or_failure():
    from market_public.provider import _MarketPublicProvider

    result = await _MarketPublicProvider(RepoFixture()).execute(
        "market.product.read", ProductReadRequest("theme:1")
    )
    assert result.provenance.market_release_identity is None
    assert result.provenance.provenance_status is MarketProvenanceStatus.INCOMPLETE
    assert result.failures == ()


def test_unselected_provenance_profile_remains_incomplete():
    provenance = MarketProvenance(
        None,
        produced_at="2026-09-17T00:00:00+00:00",
        capability_call_ref="market.product.read",
    )
    assert provenance.provenance_status is MarketProvenanceStatus.INCOMPLETE


def test_provenance_complete_is_mechanically_derived_from_profile():
    profile = MarketProvenanceProfile(
        profile_id="test.release.required",
        applies_to=("market.product.read",),
        predicates=(ProvenancePredicate.MARKET_RELEASE_IDENTITY_PRESENT,),
        incomplete_behavior="PRESERVE_INCOMPLETE",
    )

    incomplete = MarketProvenance(
        profile,
        produced_at="2026-09-17T00:00:00+00:00",
        capability_call_ref="market.product.read",
    )
    assert incomplete.provenance_status is MarketProvenanceStatus.INCOMPLETE

    release = MarketReleaseIdentity(
        source_identity="source",
        build_identity="build",
        artifact_identity="artifact",
        artifact_digest="digest",
        release_manifest_ref="manifest",
    )
    complete = MarketProvenance(
        profile,
        produced_at="2026-09-17T00:00:00+00:00",
        market_release_identity=release,
        capability_call_ref="market.product.read",
    )
    assert complete.provenance_status is MarketProvenanceStatus.COMPLETE


@pytest.mark.asyncio
async def test_failure_empty_combination_is_forbidden():
    from market_public.provider import _MarketPublicProvider

    result = await _MarketPublicProvider(RepoFixture()).execute(
        "market.product.read", ProductReadRequest("theme:1")
    )
    with pytest.raises(ValueError, match=r"FAILURE \+ EMPTY"):
        replace(
            result,
            operation_status=MarketOperationStatus.FAILURE,
            data_state=MarketDataState.EMPTY,
        )


@pytest.mark.asyncio
async def test_real_domain_binding_without_database(monkeypatch):
    """Factory binds the current-main repository class without caller injection."""
    from theme_service.repositories.phase1_read_repository import Phase1ReadRepository

    monkeypatch.setitem(sys.modules, "asyncpg", types.SimpleNamespace(Pool=object))
    provider = MarketPublicFactory.create(
        database_url="postgresql://example.invalid/market"
    )
    real_repository = provider._repository._bound()
    assert isinstance(real_repository, Phase1ReadRepository)

    async def fake_detail(subject_key):
        return {"subject_key": subject_key, "source": "current-main-domain"}

    monkeypatch.setattr(real_repository, "fetch_theme_detail", fake_detail)
    result = await provider.execute(
        "market.product.read", ProductReadRequest("theme:1")
    )
    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.payload["source"] == "current-main-domain"

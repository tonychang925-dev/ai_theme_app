from datetime import date

import pytest

from market_public import (
    EventReadRequest,
    MARKET_PUBLIC_CONTRACT_VERSION,
    MarketDataState,
    MarketFailureKind,
    MarketStateReadRequest,
    MarketOperationStatus,
    ProductLinkageReadRequest,
)
from market_public.factory import MarketPublicFactory
from market_public.provider import _MarketPublicProvider
from market_public.private.phase1_market_state_repository import (
    Phase1MarketStateReadRepository,
)


class IntegrationRepository:
    def __init__(self, linkage_rows=None, recap_row=object(), errors=None):
        self.linkage_rows = linkage_rows or []
        self.recap_row = recap_row
        self.errors = errors or {}
        self.linkage_calls = []
        self.recap_calls = []
        self.exact_event_calls = []
        self.news_event_id_exists = False

    async def fetch_intel_feed(self, **kwargs):
        return []

    async def fetch_intel_event_by_item_id(self, item_id):
        self.exact_event_calls.append(("item_id", item_id))
        return {"item_id": item_id, "title": "exact event"}

    async def fetch_intel_event_by_event_id(self, event_id):
        self.exact_event_calls.append(("event_id", event_id))
        if not self.news_event_id_exists:
            return None
        return {"item_id": f"event:{event_id}:9043089", "title": "exact news event"}

    async def fetch_theme_detail(self, subject_key):
        return None

    async def fetch_stocks_by_theme(self, **kwargs):
        self.linkage_calls.append(kwargs)
        if "linkage" in self.errors:
            raise self.errors["linkage"]
        return self.linkage_rows

    async def get_existing_post_market_recap_snapshot(self, trade_date):
        self.recap_calls.append(trade_date)
        if "recap" in self.errors:
            raise self.errors["recap"]
        return self.recap_row

    async def close(self):
        pass


class FakeRepositoryConnection:
    def __init__(self, row):
        self.row = row
        self.queries = []

    async def fetchrow(self, sql, *args):
        self.queries.append((sql, args))
        return self.row

    async def fetch(self, sql, *args):
        self.queries.append((sql, args))
        return [self.row] if self.row is not None else []


class FakeRepositoryPool:
    def __init__(self, row):
        self.connection = FakeRepositoryConnection(row)

    def acquire(self):
        return self

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback):
        return None


class DateSensitiveConnection(FakeRepositoryConnection):
    async def fetchrow(self, sql, *args):
        assert args and isinstance(args[0], date) and not isinstance(args[0], str)
        return await super().fetchrow(sql, *args)


def linkage_row(**overrides):
    row = {
        "subject_key": "solid-state-battery",
        "theme_id": 1,
        "theme_name": "固态电池",
        "stock_id": "600000",
        "stock_name": "示例股份",
        "relation_type_candidate": "leader",
        "mapping_scope": "pool",
        "source_type": "jyhf_children_leader",
        "reason": "leader linkage",
        "remark": "repository remark",
        "confidence": 0.92,
        "top": 1,
        "sort": 2,
        "stock_remark": "stock remark",
        "detail_html": "<b>forbidden</b>",
        "price": 12.34,
        "pct_chg": 5.67,
    }
    row.update(overrides)
    return row


def overview(**overrides):
    values = {
        "up_count": 2400,
        "down_count": 1600,
        "limit_up_total": 37,
        "limit_down_total": 8,
        "total_amount": 12345,
    }
    values.update(overrides)
    return values


def recap_row(**overrides):
    row = {
        "trade_date": date(2026, 9, 18),
        "snapshot_version": "post_market_recap.v2",
        "payload": {"market_overview_review": overview()},
    }
    row.update(overrides)
    return row


def provider(repository):
    return _MarketPublicProvider(repository)


def test_public_contract_adds_exactly_two_new_capabilities():
    from market_public import CAPABILITIES

    assert MARKET_PUBLIC_CONTRACT_VERSION == "0.3.2"
    assert set(CAPABILITIES) == {
        "market.event.resolve",
        "market.event.read",
        "market.product.read",
        "market.product.linkage.read",
        "market.state.read",
        "market.stock.quote.read",
    }


@pytest.mark.asyncio
async def test_linkage_scopes_and_include_leaders_reach_repository():
    repository = IntegrationRepository([linkage_row()])
    result = await provider(repository).execute(
        "market.product.linkage.read",
        ProductLinkageReadRequest(
            "solid-state-battery",
            mapping_scope="leader_overlay",
            include_leaders=True,
            limit=2,
        ),
        request_id="request-1",
        correlation_id="correlation-1",
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert repository.linkage_calls == [
        {
            "subject_key": "solid-state-battery",
            "mapping_scope": "leader_overlay",
            "include_leaders": True,
            "limit": 2,
        }
    ]
    assert result.request_id == "request-1"
    assert result.correlation_id == "correlation-1"
    assert result.provenance.correlation_id == "correlation-1"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mapping_scope", "expected_scope"),
    [("pool", "pool"), ("leader_overlay", "leader_overlay"), ("all", "all")],
)
async def test_linkage_mapping_scopes(mapping_scope, expected_scope):
    repository = IntegrationRepository([linkage_row()])

    result = await provider(repository).execute(
        "market.product.linkage.read",
        ProductLinkageReadRequest("solid-state-battery", mapping_scope=mapping_scope),
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert repository.linkage_calls[0]["mapping_scope"] == expected_scope


@pytest.mark.asyncio
async def test_linkage_ready_payload_is_exact_narrow_projection():
    repository = IntegrationRepository([linkage_row()])

    result = await provider(repository).execute(
        "market.product.linkage.read",
        ProductLinkageReadRequest("solid-state-battery", mapping_scope="all"),
    )

    assert result.payload == [
        {
            "subject_key": "solid-state-battery",
            "theme_id": 1,
            "theme_name": "固态电池",
            "stock_id": "600000",
            "stock_name": "示例股份",
            "relation_type_candidate": "leader",
            "mapping_scope": "pool",
            "source_type": "jyhf_children_leader",
            "reason": "leader linkage",
            "remark": "repository remark",
            "confidence": 0.92,
            "top": 1,
            "sort": 2,
            "stock_remark": "stock remark",
        }
    ]
    assert result.provenance.source_refs == ("jyhf_children_leader",)


@pytest.mark.asyncio
async def test_linkage_empty_is_success_empty():
    repository = IntegrationRepository()

    result = await provider(repository).execute(
        "market.product.linkage.read",
        ProductLinkageReadRequest("solid-state-battery"),
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.EMPTY
    assert result.payload == []
    assert result.failures == ()


@pytest.mark.asyncio
async def test_linkage_invalid_request_and_bound_precede_repository():
    repository = IntegrationRepository()

    provider_instance = provider(repository)
    result = await provider_instance.execute(
        "market.product.linkage.read",
        ProductLinkageReadRequest("subject", mapping_scope="invalid", limit=1),
    )

    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.NOT_APPLICABLE
    assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH
    assert result.failures[0].code == "invalid_request"
    assert repository.linkage_calls == []

    for limit in (0, 201, True, "10"):
        bounded = await provider_instance.execute(
            "market.product.linkage.read",
            ProductLinkageReadRequest("subject", limit=limit),
        )
        assert bounded.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH
        assert repository.linkage_calls == []


@pytest.mark.asyncio
async def test_linkage_dependency_and_internal_failure_planes():
    dependency_repository = IntegrationRepository(
        errors={"linkage": ConnectionError("database unavailable")}
    )
    internal_repository = IntegrationRepository(
        errors={"linkage": RuntimeError("query bug")}
    )

    dependency = await provider(dependency_repository).execute(
        "market.product.linkage.read",
        ProductLinkageReadRequest("subject"),
    )
    internal = await provider(internal_repository).execute(
        "market.product.linkage.read",
        ProductLinkageReadRequest("subject"),
    )

    assert dependency.failures[0].kind is MarketFailureKind.UNAVAILABLE
    assert dependency.failures[0].code == "repository_unavailable"
    assert internal.failures[0].kind is MarketFailureKind.INTERNAL_FAILURE
    assert internal.failures[0].code == "repository_internal_failure"
    assert dependency.payload is None
    assert internal.payload is None


@pytest.mark.asyncio
async def test_linkage_projection_data_integrity_failure_is_public_internal():
    repository = IntegrationRepository([linkage_row(stock_id=None)])

    result = await provider(repository).execute(
        "market.product.linkage.read",
        ProductLinkageReadRequest("solid-state-battery"),
    )

    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.UNAVAILABLE
    assert result.failures[0].kind is MarketFailureKind.INTERNAL_FAILURE
    assert result.failures[0].code == "projection_data_integrity_failure"
    assert result.payload is None


@pytest.mark.asyncio
async def test_state_ready_projects_exact_facts_and_source_identity():
    repository = IntegrationRepository(recap_row=recap_row())

    result = await provider(repository).execute(
        "market.state.read",
        MarketStateReadRequest("2026-09-18"),
        request_id="state-request",
        correlation_id="state-correlation",
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.payload == {
        "trade_date": "2026-09-18",
        "breadth": {
            "up_count": 2400,
            "down_count": 1600,
            "up_ratio": 0.6,
            "limit_up_count": 37,
            "limit_down_count": 8,
            "turnover_yi": 1.23,
        },
        "source": "post_market_recap_snapshot.payload.market_overview_review",
        "snapshot_version": "post_market_recap.v2",
    }
    assert repository.recap_calls == ["2026-09-18"]
    assert result.request_id == "state-request"
    assert result.correlation_id == "state-correlation"
    assert result.provenance.source_refs == (
        "post_market_recap_snapshot.payload.market_overview_review",
    )


@pytest.mark.asyncio
async def test_state_ready_supports_wrapped_persisted_recap_shape():
    repository = IntegrationRepository(
        recap_row=recap_row(
            payload={"recap_doc": {"market_overview_review": overview()}}
        )
    )

    result = await provider(repository).execute(
        "market.state.read",
        MarketStateReadRequest("2026-09-18"),
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.payload["trade_date"] == "2026-09-18"
    assert (
        result.payload["source"]
        == "post_market_recap_snapshot.payload.recap_doc.market_overview_review"
    )
    assert result.provenance.source_refs == (
        "post_market_recap_snapshot.payload.recap_doc.market_overview_review",
    )


@pytest.mark.asyncio
async def test_state_zero_facts_are_preserved():
    repository = IntegrationRepository(
        recap_row=recap_row(
            payload={
                "market_overview_review": overview(
                    up_count=0,
                    down_count=0,
                    limit_up_total=0,
                    limit_down_total=0,
                    total_amount=0,
                )
            }
        )
    )

    result = await provider(repository).execute(
        "market.state.read",
        MarketStateReadRequest("2026-09-18"),
    )

    assert result.payload["breadth"] == {
        "up_count": 0,
        "down_count": 0,
        "up_ratio": 0,
        "limit_up_count": 0,
        "limit_down_count": 0,
        "turnover_yi": 0.0,
    }


@pytest.mark.asyncio
async def test_state_missing_snapshot_is_success_empty_without_failure():
    repository = IntegrationRepository(recap_row=None)

    result = await provider(repository).execute(
        "market.state.read",
        MarketStateReadRequest("2026-09-18"),
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.EMPTY
    assert result.payload is None
    assert result.failures == ()
    assert repository.recap_calls == ["2026-09-18"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item_id",
    ["event:8410:9043089", "event:jyhf_cdp:166793"],
)
async def test_event_read_roundtrips_source_namespaced_identity_without_feed_scan(
    item_id,
):
    repository = IntegrationRepository()

    result = await provider(repository).execute(
        "market.event.read",
        EventReadRequest(item_id=item_id),
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.payload == {"item_id": item_id, "title": "exact event"}
    assert repository.exact_event_calls == [("item_id", item_id)]


@pytest.mark.asyncio
async def test_event_id_reads_exact_news_event_only():
    repository = IntegrationRepository()
    repository.news_event_id_exists = True

    result = await provider(repository).execute(
        "market.event.read",
        EventReadRequest(event_id=8410),
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.payload == {
        "item_id": "event:8410:9043089",
        "title": "exact news event",
    }
    assert repository.exact_event_calls == [("event_id", 8410)]


@pytest.mark.asyncio
async def test_event_id_news_miss_never_calls_exact_jyhf_identity():
    repository = IntegrationRepository()

    result = await provider(repository).execute(
        "market.event.read",
        EventReadRequest(event_id=166793),
    )

    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.NOT_APPLICABLE
    assert result.payload is None
    assert result.failures[0].kind is MarketFailureKind.OBJECT_NOT_FOUND
    assert result.failures[0].code == "event_not_found"
    assert repository.exact_event_calls == [("event_id", 166793)]
    assert ("item_id", "event:jyhf_cdp:166793") not in repository.exact_event_calls


@pytest.mark.asyncio
async def test_state_invalid_date_precedes_exact_date_repository_call():
    repository = IntegrationRepository()

    result = await provider(repository).execute(
        "market.state.read",
        MarketStateReadRequest("2026-9-18"),
    )

    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.NOT_APPLICABLE
    assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH
    assert repository.recap_calls == []


@pytest.mark.asyncio
async def test_state_malformed_negative_and_mismatched_facts_fail_closed():
    malformed = IntegrationRepository(
        recap_row=recap_row(payload={"recap_doc": {"market_overview_review": []}})
    )
    negative = IntegrationRepository(
        recap_row=recap_row(payload={"market_overview_review": overview(up_count=-1)})
    )
    mismatched = IntegrationRepository(
        recap_row=recap_row(trade_date=date(2026, 9, 17))
    )

    for repository in (malformed, negative, mismatched):
        result = await provider(repository).execute(
            "market.state.read",
            MarketStateReadRequest("2026-09-18"),
        )
        assert result.operation_status is MarketOperationStatus.FAILURE
        assert result.data_state is MarketDataState.UNAVAILABLE
        assert result.failures[0].kind is MarketFailureKind.INTERNAL_FAILURE
        assert result.failures[0].code == "market_overview_review_invalid"
        assert result.payload is None


@pytest.mark.asyncio
async def test_state_conflicting_direct_and_wrapped_reviews_fail_closed():
    direct = overview(up_count=2400)
    wrapped = overview(up_count=2399)
    repository = IntegrationRepository(
        recap_row=recap_row(
            payload={
                "market_overview_review": direct,
                "recap_doc": {"market_overview_review": wrapped},
            }
        )
    )

    result = await provider(repository).execute(
        "market.state.read",
        MarketStateReadRequest("2026-09-18"),
    )

    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.UNAVAILABLE
    assert result.failures[0].kind is MarketFailureKind.INTERNAL_FAILURE
    assert result.failures[0].code == "market_overview_review_invalid"
    assert "conflict" in result.failures[0].message
    assert result.payload is None


@pytest.mark.asyncio
async def test_state_non_finite_amount_is_data_integrity_failure():
    repository = IntegrationRepository(
        recap_row=recap_row(
            payload={
                "market_overview_review": overview(
                    total_amount=float("inf"),
                )
            }
        )
    )

    result = await provider(repository).execute(
        "market.state.read",
        MarketStateReadRequest("2026-09-18"),
    )

    assert result.failures[0].kind is MarketFailureKind.INTERNAL_FAILURE
    assert result.failures[0].code == "market_overview_review_invalid"
    assert "total_amount" in result.failures[0].message


@pytest.mark.asyncio
async def test_state_dependency_failure_is_typed_unavailable():
    repository = IntegrationRepository(errors={"recap": ConnectionError("down")})

    result = await provider(repository).execute(
        "market.state.read",
        MarketStateReadRequest("2026-09-18"),
    )

    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.UNAVAILABLE
    assert result.failures[0].kind is MarketFailureKind.UNAVAILABLE
    assert result.failures[0].code == "repository_unavailable"


@pytest.mark.asyncio
async def test_factory_lazy_repository_exposes_both_private_read_paths():
    factory_repository = MarketPublicFactory.create(
        database_url="postgresql://example.invalid/market"
    )._repository
    bound = IntegrationRepository()
    factory_repository._repository = bound

    await factory_repository.fetch_stocks_by_theme(
        subject_key="subject",
        mapping_scope="all",
        include_leaders=True,
        limit=3,
    )
    await factory_repository.get_existing_post_market_recap_snapshot("2026-09-18")
    await factory_repository.fetch_intel_event_by_item_id("event:8410:9043089")
    await factory_repository.fetch_intel_event_by_event_id(8410)

    assert bound.linkage_calls == [
        {
            "subject_key": "subject",
            "mapping_scope": "all",
            "include_leaders": True,
            "limit": 3,
        }
    ]
    assert bound.recap_calls == ["2026-09-18"]
    assert bound.exact_event_calls == [
        ("item_id", "event:8410:9043089"),
        ("event_id", 8410),
    ]


@pytest.mark.asyncio
async def test_phase1_recap_read_is_exact_date_without_latest_fallback():
    repository = Phase1MarketStateReadRepository(
        database_url="postgresql://example.invalid/market"
    )
    pool = FakeRepositoryPool(recap_row())
    pool.connection = DateSensitiveConnection(recap_row())
    repository._pool = pool

    result = await repository.get_existing_post_market_recap_snapshot("2026-09-18")

    assert result["trade_date"] == date(2026, 9, 18)
    sql, args = pool.connection.queries[0]
    assert args == (date(2026, 9, 18),)
    assert "FROM post_market_recap_snapshot" in sql
    assert "WHERE trade_date = $1::date" in sql
    assert "LIMIT 1" in sql
    assert "MAX(" not in sql


@pytest.mark.asyncio
async def test_phase1_exact_event_reads_are_identity_bound_not_top_n_scans():
    repository = Phase1MarketStateReadRepository(
        database_url="postgresql://example.invalid/market"
    )
    pool = FakeRepositoryPool(None)
    repository._pool = pool

    await repository.fetch_intel_event_by_item_id("event:8410:9043089")
    await repository.fetch_intel_event_by_item_id("event:jyhf_cdp:166793")
    await repository.fetch_intel_event_by_event_id(8410)

    sql_values = [sql for sql, _ in pool.connection.queries]
    assert any("ne.id = $1::bigint" in sql for sql in sql_values)
    assert any(
        "subject_history_staging" in sql and "id = $1::bigint" in sql
        for sql in sql_values
    )
    event_id_sql = sql_values[-1]
    assert "FROM news_event ne" in event_id_sql
    assert "subject_history_staging" not in event_id_sql
    assert all("LIMIT 200" not in sql for sql in sql_values)

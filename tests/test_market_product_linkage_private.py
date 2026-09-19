from dataclasses import asdict, fields

import pytest

from market_public.private.product_linkage import (
    PRODUCT_LINKAGE_ROW_FIELDS,
    MarketProductLinkageReader,
    ProductLinkageRequest,
    ProductLinkageStatus,
)


class RepositoryFixture:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.calls = []

    async def fetch_stocks_by_theme(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.rows


def repository_row(stock_id="600000", **overrides):
    row = {
        "subject_key": "solid-state-battery",
        "theme_id": 1,
        "theme_name": "固态电池",
        "stock_id": stock_id,
        "stock_name": "示例股份",
        "relation_type_candidate": "leader",
        "mapping_scope": "leader_overlay",
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


@pytest.mark.asyncio
async def test_pool_request_uses_repository_scope():
    repository = RepositoryFixture([repository_row(mapping_scope="pool")])
    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery", mapping_scope="pool")
    )

    assert result.status is ProductLinkageStatus.READY
    assert repository.calls == [
        {
            "subject_key": "solid-state-battery",
            "mapping_scope": "pool",
            "include_leaders": False,
            "limit": 100,
        }
    ]
    assert result.rows[0].mapping_scope == "pool"


@pytest.mark.asyncio
async def test_leader_overlay_request_uses_repository_scope():
    repository = RepositoryFixture([repository_row()])
    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery", mapping_scope="leader_overlay")
    )

    assert result.status is ProductLinkageStatus.READY
    assert repository.calls[0]["mapping_scope"] == "leader_overlay"
    assert result.rows[0].relation_type_candidate == "leader"


@pytest.mark.asyncio
async def test_all_request_uses_repository_scope():
    repository = RepositoryFixture([repository_row(mapping_scope="all")])
    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery", mapping_scope="all")
    )

    assert result.status is ProductLinkageStatus.READY
    assert repository.calls[0]["mapping_scope"] == "all"
    assert result.rows[0].mapping_scope == "all"


@pytest.mark.asyncio
async def test_include_leaders_is_forwarded_and_defaults_to_false():
    repository = RepositoryFixture([repository_row()])
    reader = MarketProductLinkageReader(repository)

    await reader.read(ProductLinkageRequest("solid-state-battery", include_leaders=True, limit=2))
    await reader.read(ProductLinkageRequest("solid-state-battery", limit=2))

    assert [call["include_leaders"] for call in repository.calls] == [True, False]


@pytest.mark.asyncio
async def test_repository_order_is_preserved_without_reordering():
    rows = [
        repository_row("600003", sort=3),
        repository_row("600001", sort=1),
        repository_row("600002", sort=2),
    ]
    repository = RepositoryFixture(rows)

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery", limit=3)
    )

    assert [row.stock_id for row in result.rows] == ["600003", "600001", "600002"]


@pytest.mark.asyncio
async def test_repository_deduplication_is_preserved_without_second_dedup():
    rows = [
        repository_row("600001"),
        repository_row("600002"),
    ]
    repository = RepositoryFixture(rows)

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery", mapping_scope="all", limit=2)
    )

    assert len(result.rows) == 2
    assert [row.stock_id for row in result.rows] == ["600001", "600002"]


@pytest.mark.asyncio
async def test_empty_linkage_is_valid_empty_evidence():
    repository = RepositoryFixture([])

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("subject")
    )

    assert result.status is ProductLinkageStatus.EMPTY
    assert result.rows == ()
    assert result.failure is None


@pytest.mark.asyncio
async def test_invalid_mapping_scope_fails_typed_validation_before_repository():
    repository = RepositoryFixture()

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("subject", mapping_scope="everything")
    )

    assert result.status is ProductLinkageStatus.INVALID_REQUEST
    assert result.rows == ()
    assert result.failure.code == "invalid_request"
    assert "mapping_scope" in result.failure.message
    assert repository.calls == []


@pytest.mark.asyncio
async def test_repository_failure_remains_typed_failure():
    repository = RepositoryFixture(error=ConnectionError("database unavailable"))

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("subject")
    )

    assert result.status is ProductLinkageStatus.DEPENDENCY_UNAVAILABLE
    assert result.rows == ()
    assert result.failure.code == "repository_unavailable"
    assert result.failure.message == "database unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("query bug"), ValueError("bad row")])
async def test_non_dependency_repository_failure_is_internal(error):
    repository = RepositoryFixture(error=error)

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("subject")
    )

    assert result.status is ProductLinkageStatus.INTERNAL_FAILURE
    assert result.rows == ()
    assert result.failure.code == "repository_internal_failure"


@pytest.mark.asyncio
async def test_missing_stock_id_is_projection_data_integrity_failure():
    repository = RepositoryFixture([repository_row(stock_id=None)])

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery")
    )

    assert result.status is ProductLinkageStatus.INTERNAL_FAILURE
    assert result.rows == ()
    assert result.failure.code == "projection_data_integrity_failure"
    assert "stock_id" in result.failure.message


@pytest.mark.asyncio
async def test_blank_source_type_is_projection_data_integrity_failure():
    repository = RepositoryFixture([repository_row(source_type=" ")])

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery")
    )

    assert result.status is ProductLinkageStatus.INTERNAL_FAILURE
    assert result.rows == ()
    assert result.failure.code == "projection_data_integrity_failure"
    assert "source_type" in result.failure.message


@pytest.mark.asyncio
async def test_cross_subject_repository_row_fails_closed():
    repository = RepositoryFixture([repository_row(subject_key="other-subject")])

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery")
    )

    assert result.status is ProductLinkageStatus.INTERNAL_FAILURE
    assert result.rows == ()
    assert result.failure.code == "projection_data_integrity_failure"
    assert "subject_key" in result.failure.message


@pytest.mark.asyncio
async def test_nullable_descriptive_repository_fields_remain_valid():
    repository = RepositoryFixture(
        [repository_row(reason=None, remark=None, top=None, sort=None, stock_remark=None)]
    )

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery")
    )

    assert result.status is ProductLinkageStatus.READY
    assert result.rows[0].reason is None
    assert result.rows[0].remark is None
    assert result.rows[0].top is None
    assert result.rows[0].sort is None
    assert result.rows[0].stock_remark is None


@pytest.mark.asyncio
async def test_forbidden_fields_are_absent_from_every_row():
    rows = [repository_row("600001"), repository_row("600002", price=99.0, pct_chg=-1.0)]
    repository = RepositoryFixture(rows)

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("solid-state-battery", mapping_scope="all", limit=2)
    )

    assert tuple(field.name for field in fields(result.rows[0])) == PRODUCT_LINKAGE_ROW_FIELDS
    for row in result.rows:
        projected = asdict(row)
        assert set(projected) == set(PRODUCT_LINKAGE_ROW_FIELDS)
        assert projected["relation_type_candidate"] == "leader"
        assert projected["source_type"] == "jyhf_children_leader"
        assert projected["confidence"] == 0.92
        assert "detail_html" not in projected
        assert "price" not in projected
        assert "pct_chg" not in projected


@pytest.mark.asyncio
async def test_repository_failure_has_no_fallback_or_synthetic_result():
    repository = RepositoryFixture(error=ConnectionError("one deterministic source"))

    result = await MarketProductLinkageReader(repository).read(
        ProductLinkageRequest("subject", limit=1)
    )

    assert len(repository.calls) == 1
    assert result.status is ProductLinkageStatus.DEPENDENCY_UNAVAILABLE
    assert result.rows == ()


@pytest.mark.asyncio
async def test_bounded_limit_validation_rejects_invalid_values():
    repository = RepositoryFixture()
    reader = MarketProductLinkageReader(repository)

    low = await reader.read(ProductLinkageRequest("subject", limit=0))
    high = await reader.read(ProductLinkageRequest("subject", limit=201))

    assert low.status is ProductLinkageStatus.INVALID_REQUEST
    assert high.status is ProductLinkageStatus.INVALID_REQUEST
    assert repository.calls == []

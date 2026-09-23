from datetime import date
import json

import pytest

from market_public import (
    CAPABILITIES,
    MarketAnalysisReadRequest,
    MarketDataState,
    MarketFailureKind,
    MarketOperationStatus,
    MarketProvenanceStatus,
)
from market_public.provider import _MarketPublicProvider


class AnalysisRepository:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error
        self.calls = []

    async def get_existing_post_market_recap_snapshot(self, trade_date):
        self.calls.append(trade_date)
        if self.error is not None:
            raise self.error
        return self.row

    async def close(self):
        pass


def analytical_payload():
    return {
        "trade_date": "2026-05-15",
        "snapshot_id": "recap-snapshot-1",
        "market_regime_review": {
            "broad_market_regime": "震荡偏弱",
            "short_term_sentiment": "修复初期",
            "mainline_environment": "缩容轮动",
        },
        "mainline_states": [
            {
                "theme_name": "AI 应用",
                "lifecycle": "主升",
                "state": "active",
                "strong_stock_count": 8,
            }
        ],
        "watchlists": [{"stock_name": "示例股份", "reason": "缩量回踩"}],
        "post_market_setup_plan": {
            "summary": {"watch_date": "2026-05-16", "focus": "AI 应用承接"}
        },
    }


def analytical_row(**overrides):
    row = {
        "trade_date": date(2026, 5, 15),
        "snapshot_version": "post_market_recap.v2",
        "batch_id": "batch-1",
        "trace_id": "trace-1",
        "payload": analytical_payload(),
    }
    row.update(overrides)
    return row


def provider(repository):
    return _MarketPublicProvider(repository)


@pytest.mark.asyncio
async def test_analysis_read_projects_reused_evidence_chain():
    repository = AnalysisRepository(analytical_row())
    result = await provider(repository).execute(
        "market.analysis.read",
        MarketAnalysisReadRequest(trade_date="2026-05-15"),
        request_id="analysis-read",
        correlation_id="analysis-correlation",
    )

    assert repository.calls == ["2026-05-15"]
    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.READY
    assert result.capability_id == "market.analysis.read"
    assert result.payload["schema_version"] == "market.analysis.v1"
    assert result.payload["trade_date"] == "2026-05-15"
    assert result.payload["source"]["snapshot_ref"] == "post_market_recap_snapshot"
    assert result.payload["source"]["snapshot_version"] == "post_market_recap.v2"
    assert result.payload["source"]["source_snapshot_ids"] == ["recap-snapshot-1"]
    assert result.payload["source_bundle_id"].startswith("mkb:2026-05-15:")
    assert result.payload["evidence_snapshot_id"].startswith("mes:2026-05-15:")
    assert result.payload["content_hash"]

    evidence = {item["key"]: item for item in result.payload["evidence"]}
    assert evidence["market.broad_market_regime"]["value"] == "震荡偏弱"
    assert evidence["market.short_term_sentiment"]["value"] == "修复初期"
    assert evidence["mainline.0.name"]["value"] == "AI 应用"
    assert evidence["mainline.0.lifecycle"]["value"] == "主升"
    assert evidence["calendar.next_trade_date"]["value"] == "2026-05-16"
    assert all(
        item["ref"]["ref_id"]
        and item["ref"]["source_module"]
        and item["ref"]["source_path"]
        and item["ref"]["source_snapshot_id"]
        for item in result.payload["evidence"]
    )

    coverage = {item["module"]: item for item in result.payload["module_coverage"]}
    assert coverage["market_regime_review"]["status"] == "ready"
    assert coverage["watchlists"]["status"] == "ready"
    assert "engine_summary" in result.payload["quality"]["missing_modules"]
    assert result.payload["quality"]["status"] == "partial"
    assert result.payload["review_maturity"] == {
        "available": False,
        "source_mode": "unavailable",
        "source": "not_bound",
        "reason": ("review maturity is not present in the canonical recap payload"),
    }
    assert result.provenance.provenance_status is MarketProvenanceStatus.INCOMPLETE
    assert result.provenance.source_refs
    assert result.provenance.evidence_refs
    assert result.provenance.data_cutoff == result.payload["as_of"]


@pytest.mark.asyncio
async def test_analysis_read_preserves_canonical_review_maturity_without_fabrication():
    payload = analytical_payload()
    payload.update(
        {
            "source_mode": "formal",
            "approved": True,
            "approved_at": "2026-05-15T10:00:00+00:00",
            "approved_by": "analyst",
        }
    )
    repository = AnalysisRepository(analytical_row(payload=payload))
    result = await provider(repository).execute(
        "market.analysis.read", MarketAnalysisReadRequest("2026-05-15")
    )

    maturity = result.payload["review_maturity"]
    assert maturity["available"] is True
    assert maturity["source"] == "canonical_recap"
    assert maturity["fields"]["source_mode"] == "formal"
    assert maturity["fields"]["approved"] is True
    assert maturity["fields"]["approved_by"] == "analyst"


@pytest.mark.asyncio
async def test_analysis_read_missing_exact_date_is_success_empty_without_fallback():
    repository = AnalysisRepository()
    result = await provider(repository).execute(
        "market.analysis.read", MarketAnalysisReadRequest("2026-07-10")
    )

    assert result.operation_status is MarketOperationStatus.SUCCESS
    assert result.data_state is MarketDataState.EMPTY
    assert result.payload is None
    assert result.failures == ()
    assert repository.calls == ["2026-07-10"]


@pytest.mark.asyncio
@pytest.mark.parametrize("trade_date", ["", "2026-5-15", "not-a-date", None])
async def test_analysis_read_rejects_noncanonical_dates(trade_date):
    repository = AnalysisRepository(analytical_row())
    result = await provider(repository).execute(
        "market.analysis.read", MarketAnalysisReadRequest(trade_date)
    )

    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.NOT_APPLICABLE
    assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH
    assert result.failures[0].code == "invalid_request"
    assert repository.calls == []


@pytest.mark.asyncio
async def test_analysis_read_rejects_wrong_request_type():
    result = await provider(AnalysisRepository()).execute(
        "market.analysis.read", {"trade_date": "2026-05-15"}
    )
    assert result.failures[0].kind is MarketFailureKind.CONTRACT_MISMATCH


@pytest.mark.asyncio
async def test_analysis_read_dependency_failure_is_typed_unavailable():
    repository = AnalysisRepository(error=ConnectionError("database down"))
    result = await provider(repository).execute(
        "market.analysis.read", MarketAnalysisReadRequest("2026-05-15")
    )
    assert result.operation_status is MarketOperationStatus.FAILURE
    assert result.data_state is MarketDataState.UNAVAILABLE
    assert result.failures[0].kind is MarketFailureKind.UNAVAILABLE
    assert result.failures[0].code == "repository_unavailable"


@pytest.mark.asyncio
async def test_analysis_read_fails_closed_on_malformed_or_conflicting_source():
    for row in (
        analytical_row(payload="not-json"),
        analytical_row(payload={"unrelated": {}}),
        analytical_row(trade_date=date(2026, 5, 14)),
        analytical_row(
            payload={
                **analytical_payload(),
                "approved": False,
                "recap_doc": {"approved": True},
            }
        ),
    ):
        result = await provider(AnalysisRepository(row)).execute(
            "market.analysis.read", MarketAnalysisReadRequest("2026-05-15")
        )
        assert result.operation_status is MarketOperationStatus.FAILURE
        assert result.data_state is MarketDataState.UNAVAILABLE
        assert result.failures[0].kind is MarketFailureKind.INTERNAL_FAILURE
        assert result.failures[0].code == "market_analysis_source_invalid"
        assert result.payload is None


@pytest.mark.asyncio
async def test_analysis_projection_is_deterministic_json_and_private_boundary_safe():
    repository = AnalysisRepository(analytical_row())
    first = await provider(repository).execute(
        "market.analysis.read", MarketAnalysisReadRequest("2026-05-15")
    )
    second = await provider(repository).execute(
        "market.analysis.read", MarketAnalysisReadRequest("2026-05-15")
    )

    assert first.payload == second.payload
    encoded = json.dumps(first.payload, ensure_ascii=False, sort_keys=True)
    assert "repository" not in encoded
    assert "gateway" not in encoded
    assert "asyncpg" not in encoded
    assert CAPABILITIES["market.analysis.read"].side_effect == "READ_ONLY"

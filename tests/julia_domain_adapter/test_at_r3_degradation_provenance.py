"""AT-R3 Degradation + Provenance tests.

TC-AT-R3-001: snapshot normal success.
TC-AT-R3-002: alerts normal success and legitimate empty.
TC-AT-R3-003: single/optional source failure -> partial.
TC-AT-R3-004: multiple source failures preserve successful material.
TC-AT-R3-005: required source missing -> unavailable.
TC-AT-R3-006: DB unavailable -> unavailable, never success-empty.
TC-AT-R3-007: Redis unavailable explicit failure.
TC-AT-R3-008: upstream exception -> error, never success-empty.
TC-AT-R3-009: timeout -> UPSTREAM_TIMEOUT.
TC-AT-R3-010: stale source -> data_state=stale.
TC-AT-R3-011: schema mismatch -> SCHEMA_MISMATCH.
TC-AT-R3-012: every cognition-supporting source has provenance/freshness.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_processing_service.application.services.analyst_workbench.snapshot import ReviewSnapshot
from stock_processing_service.application.services.julia_domain_adapter import DomainIntelligenceAdapter
from stock_processing_service.application.services.julia_domain_adapter.contracts import AdapterErrorCode, AdapterRequest

CST = timezone(timedelta(hours=8))


class FixedClock:
    def now(self):
        return datetime(2026, 8, 26, 15, 30, tzinfo=CST)


class FakeExporter:
    def __init__(self, result=None, exc: BaseException | None = None):
        self.result = result
        self.exc = exc

    async def export(self, trade_date: str):
        if self.exc:
            raise self.exc
        return self.result


def _request(operation: str, arguments: dict | None = None) -> AdapterRequest:
    return AdapterRequest(
        operation=operation,
        arguments=arguments or {"trade_date": "2026-08-26"},
        correlation_id="corr-at-r3",
        idempotency_key="idem-at-r3",
        requested_at="2026-08-26T10:00:00+08:00",
        schema_version="1.0",
    )


def _snapshot_payload(**overrides) -> dict:
    payload = {
        "schema_version": "market-context.v1",
        "provider": "ai_theme_app",
        "trade_date": "2026-08-26",
        "status": "live",
        "market_state": {"theme_count": 2, "mainline_count": 1},
        "themes": [{"subject_key": "theme-ai", "theme_name": "AI"}],
        "quality": {"coverage": 1.0, "source_quality": 0.9},
        "source_records": [
            {
                "source_type": "database",
                "source_name": "theme_cycle_judgement_v2",
                "source_ref": "trade_date=2026-08-26",
                "as_of": "2026-08-26",
                "freshness": "fresh",
                "status": "success",
                "provenance": {"row_count": 2},
            }
        ],
    }
    payload.update(overrides)
    return payload


def _write_snapshot(base: Path, *, attention_level: str = "HIGH", session_status: str = "APPROVED", approved: bool = True, hash_ok: bool = True) -> None:
    trade_date = date(2026, 8, 26)
    snap = ReviewSnapshot(
        trade_date=trade_date,
        snapshot_version=1,
        based_on_draft_version=1,
        approved=approved,
        approved_at="2026-08-26T15:10:00+08:00" if approved else "",
        approved_by="analyst" if approved else "",
        approval_mode="analyst_approved",
        source_mode="formal",
        cognition_cards=[
            {
                "subject_name": "AI",
                "stage_judgement": "active",
                "attention_level": attention_level,
                "attention_score": 3200,
                "confidence": 0.82,
                "analyst_reviewed": True,
                "evidence_refs": ["ref-1"],
            }
        ],
        narrative={"summary": "结构活跃"},
    )
    snap.snapshot_hash = snap.compute_hash() if hash_ok else "bad-hash"
    d = base / trade_date.isoformat()
    d.mkdir(parents=True)
    (d / "session.json").write_text(json.dumps({"trade_date": trade_date.isoformat(), "status": session_status}), encoding="utf-8")
    (d / "snapshot.json").write_text(json.dumps(snap.to_dict(), ensure_ascii=False), encoding="utf-8")


def _assert_not_success_empty(result):
    assert not (result.status == "success" and result.data_state == "empty"), result.to_dict()


@pytest.mark.asyncio
async def test_tc_at_r3_001_snapshot_normal_success_has_source_provenance():
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(_snapshot_payload()), clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.status == "success"
    assert result.data_state == "normal"
    assert result.failures == []
    assert result.source_records[0].source_name == "theme_cycle_judgement_v2"
    assert result.source_records[0].freshness == "fresh"
    assert result.source_records[0].provenance["row_count"] == 2


@pytest.mark.asyncio
async def test_tc_at_r3_002_alerts_normal_and_legitimate_empty_are_distinct(tmp_path):
    _write_snapshot(tmp_path, attention_level="HIGH")
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())
    normal = await adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26", "min_attention_level": "HIGH"}))
    assert normal.status == "success"
    assert normal.data_state == "normal"
    assert normal.payload["alerts"]

    empty = await adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26", "min_attention_level": "CRITICAL"}))
    assert empty.status == "success"
    assert empty.data_state == "empty"
    assert empty.failures == []
    assert empty.payload["claim_count"] == 1
    assert empty.source_records[0].status == "success"


@pytest.mark.asyncio
async def test_tc_at_r3_003_single_optional_source_failure_yields_partial():
    raw = _snapshot_payload(missing_sources=["money_flow_enhanced"], status="partial")
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(raw), clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.status == "partial"
    assert result.data_state == "normal"
    assert result.payload["themes"]
    assert result.failures[0].source_name == "money_flow_enhanced"
    assert result.failures[0].code == AdapterErrorCode.UPSTREAM_UNAVAILABLE.value


@pytest.mark.asyncio
async def test_tc_at_r3_004_multiple_source_failures_preserve_successful_material():
    raw = _snapshot_payload(
        status="partial",
        missing_sources=["money_flow_enhanced", "redis_alert_stream"],
        failures=[{"source_name": "postgres_metrics", "code": "UPSTREAM_TIMEOUT", "message": "query timed out", "retryable": True}],
    )
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(raw), clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.status == "partial"
    assert result.payload["market_state"]["theme_count"] == 2
    assert {failure.source_name for failure in result.failures} == {"money_flow_enhanced", "redis_alert_stream", "postgres_metrics"}
    assert any(record.source_name == "theme_cycle_judgement_v2" and record.status == "success" for record in result.source_records)
    assert any(record.source_name == "redis_alert_stream" and record.failure for record in result.source_records)


@pytest.mark.asyncio
async def test_tc_at_r3_005_required_alert_source_missing_is_unavailable_not_empty_success(tmp_path):
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())

    result = await adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26"}))

    assert result.status == "unavailable"
    assert result.data_state == "empty"
    assert result.failures
    _assert_not_success_empty(result)


@pytest.mark.asyncio
async def test_tc_at_r3_006_db_unavailable_is_explicit_failure_not_success_empty():
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(exc=ConnectionError("postgres unavailable")), clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.status == "unavailable"
    assert result.data_state == "empty"
    assert result.failures[0].code == AdapterErrorCode.UPSTREAM_UNAVAILABLE.value
    _assert_not_success_empty(result)


@pytest.mark.asyncio
async def test_tc_at_r3_007_redis_unavailable_is_explicit_source_failure():
    raw = _snapshot_payload(
        status="partial",
        missing_sources=["redis_alert_stream"],
        quality={"coverage": 0.75},
    )
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(raw), clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.status == "partial"
    redis_failure = [failure for failure in result.failures if failure.source_name == "redis_alert_stream"][0]
    assert redis_failure.code == AdapterErrorCode.UPSTREAM_UNAVAILABLE.value
    assert redis_failure.details["dependency"] == "redis"


@pytest.mark.asyncio
async def test_tc_at_r3_008_upstream_exception_is_error_not_success_empty():
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(exc=RuntimeError("boom")), clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.status == "error"
    assert result.data_state == "empty"
    assert result.failures[0].code == AdapterErrorCode.INTERNAL_ERROR.value
    _assert_not_success_empty(result)


@pytest.mark.asyncio
async def test_tc_at_r3_009_timeout_has_explicit_upstream_timeout_code():
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(exc=TimeoutError("slow source")), clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.status == "unavailable"
    assert result.data_state == "empty"
    assert result.failures[0].code == AdapterErrorCode.UPSTREAM_TIMEOUT.value
    assert result.failures[0].retryable is True


@pytest.mark.asyncio
async def test_tc_at_r3_010_stale_snapshot_marks_envelope_and_sources_stale():
    raw = _snapshot_payload(trade_date="2026-08-25", freshness="stale")
    adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(raw), clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot", {"trade_date": "2026-08-26"}))

    assert result.status == "success"
    assert result.data_state == "stale"
    assert all(record.freshness == "stale" for record in result.source_records)


@pytest.mark.asyncio
async def test_tc_at_r3_011_schema_mismatch_is_explicit_for_snapshot_and_alerts(tmp_path):
    snapshot_adapter = DomainIntelligenceAdapter(market_context_exporter=FakeExporter(["bad"]), clock=FixedClock())
    snapshot_result = await snapshot_adapter.execute(_request("market.snapshot"))
    assert snapshot_result.status == "error"
    assert snapshot_result.failures[0].code == AdapterErrorCode.SCHEMA_MISMATCH.value

    d = tmp_path / "2026-08-26"
    d.mkdir()
    (d / "session.json").write_text('{"trade_date":"2026-08-26","status":"APPROVED"}', encoding="utf-8")
    (d / "snapshot.json").write_text('{not-json', encoding="utf-8")
    alerts_adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())
    alerts_result = await alerts_adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26"}))
    assert alerts_result.status == "error"
    assert alerts_result.failures[0].code == AdapterErrorCode.SCHEMA_MISMATCH.value


@pytest.mark.asyncio
async def test_tc_at_r3_012_validation_failure_preserves_concrete_source_failure_code(tmp_path):
    _write_snapshot(tmp_path, attention_level="HIGH", session_status="DRAFT_READY", approved=True)
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())

    result = await adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26"}))

    assert result.status == "unavailable"
    assert result.data_state == "empty"
    assert result.failures[0].code == AdapterErrorCode.UPSTREAM_UNAVAILABLE.value
    assert "session_not_approved" in result.failures[0].details["validation_errors"]
    assert result.source_records[0].failure.code == AdapterErrorCode.UPSTREAM_UNAVAILABLE.value

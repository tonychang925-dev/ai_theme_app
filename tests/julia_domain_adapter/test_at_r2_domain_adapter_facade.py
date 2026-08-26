"""AT-R2 Domain Adapter Facade tests.

TC-AT-R2-001: market.snapshot exact dispatch.
TC-AT-R2-002: market.alerts exact dispatch.
TC-AT-R2-003: unknown operation rejected.
TC-AT-R2-004: successful truthful source can emit success envelope.
TC-AT-R2-005: adapter does not use legacy lossy wrappers for empty/failure states.
TC-AT-R2-006: no NLP routing, Julia import, transport, or cross-repo path dependency.
TC-AT-R2-007: read-only behavior for facade operations.
"""

from __future__ import annotations

import ast
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
from stock_processing_service.application.services.julia_domain_adapter.contracts import (
    AdapterRequest,
    ValidationError,
)

CONTRACT_DIR = ROOT / "stock_processing_service" / "application" / "services" / "julia_domain_adapter"
CST = timezone(timedelta(hours=8))


class FixedClock:
    def now(self):
        return datetime(2026, 8, 26, 15, 30, tzinfo=CST)


class FakeMarketContextExporter:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    async def export(self, trade_date: str):
        self.calls.append(trade_date)
        return self.payload


def _request(operation: str, arguments: dict | None = None) -> AdapterRequest:
    return AdapterRequest(
        operation=operation,
        arguments=arguments or {"trade_date": "2026-08-26"},
        correlation_id="corr-at-r2",
        idempotency_key="idem-at-r2",
        requested_at="2026-08-26T10:00:00+08:00",
        schema_version="1.0",
    )


def _write_approved_snapshot(base: Path, *, attention_level: str = "HIGH") -> None:
    trade_date = date(2026, 8, 26)
    snap = ReviewSnapshot(
        trade_date=trade_date,
        snapshot_version=1,
        based_on_draft_version=1,
        approved=True,
        approved_at="2026-08-26T15:10:00+08:00",
        approved_by="analyst",
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
    snap.snapshot_hash = snap.compute_hash()
    d = base / trade_date.isoformat()
    d.mkdir(parents=True)
    (d / "session.json").write_text(json.dumps({"trade_date": trade_date.isoformat(), "status": "APPROVED"}), encoding="utf-8")
    (d / "snapshot.json").write_text(json.dumps(snap.to_dict(), ensure_ascii=False), encoding="utf-8")


@pytest.mark.asyncio
async def test_tc_at_r2_001_market_snapshot_exact_dispatch_success():
    exporter = FakeMarketContextExporter({
        "schema_version": "market-context.v1",
        "provider": "ai_theme_app",
        "trade_date": "2026-08-26",
        "status": "live",
        "market_state": {"theme_count": 1},
        "themes": [{"subject_key": "theme-ai", "theme_name": "AI"}],
        "quality": {"coverage": 1.0, "source_quality": 0.9},
    })
    adapter = DomainIntelligenceAdapter(market_context_exporter=exporter, clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.operation == "market.snapshot"
    assert result.status == "success"
    assert result.data_state == "normal"
    assert result.correlation_id == "corr-at-r2"
    assert exporter.calls == ["2026-08-26"]
    assert result.source_records[0].source_name == "market_context_exporter"


@pytest.mark.asyncio
async def test_tc_at_r2_002_market_alerts_exact_dispatch_success(tmp_path):
    _write_approved_snapshot(tmp_path, attention_level="HIGH")
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())

    result = await adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26", "min_attention_level": "HIGH"}))

    assert result.operation == "market.alerts"
    assert result.status == "success"
    assert result.data_state == "normal"
    assert result.payload["alerts"][0]["attention_level"] == "HIGH"
    assert result.source_records[0].source_name == "analyst_workbench_snapshot"


@pytest.mark.asyncio
async def test_tc_at_r2_003_unknown_operation_rejected_before_dispatch():
    adapter = DomainIntelligenceAdapter(clock=FixedClock())
    with pytest.raises(ValidationError, match="unsupported operation"):
        await adapter.execute({"operation": "market.intent.resolve", "arguments": {}, "schema_version": "1.0"})


@pytest.mark.asyncio
async def test_tc_at_r2_004_alerts_success_empty_only_after_valid_source_execution(tmp_path):
    _write_approved_snapshot(tmp_path, attention_level="LOW")
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())

    result = await adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26", "min_attention_level": "HIGH"}))

    assert result.status == "success"
    assert result.data_state == "empty"
    assert result.failures == []
    assert result.payload["claim_count"] == 1
    assert result.source_records[0].status == "success"
    assert result.diagnostics["empty_reason"] == "no claims at or above requested attention level"


@pytest.mark.asyncio
async def test_tc_at_r2_005_lossy_missing_alert_source_does_not_become_success_empty(tmp_path):
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())

    result = await adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26", "min_attention_level": "HIGH"}))

    assert result.status == "unavailable"
    assert result.data_state == "empty"
    assert result.failures
    assert result.payload == {}
    assert result.source_records[0].status == "failed"


@pytest.mark.asyncio
async def test_tc_at_r2_006_snapshot_partial_preserves_missing_source_failure():
    exporter = FakeMarketContextExporter({
        "schema_version": "market-context.v1",
        "provider": "ai_theme_app",
        "trade_date": "2026-08-26",
        "status": "partial",
        "market_state": {"theme_count": 1},
        "themes": [{"subject_key": "theme-ai"}],
        "missing_sources": ["money_flow_enhanced"],
        "quality": {"coverage": 0.66},
    })
    adapter = DomainIntelligenceAdapter(market_context_exporter=exporter, clock=FixedClock())

    result = await adapter.execute(_request("market.snapshot"))

    assert result.status == "partial"
    assert result.data_state == "normal"
    assert result.failures[0].source_name == "money_flow_enhanced"
    assert any(record.source_name == "money_flow_enhanced" and record.status == "failed" for record in result.source_records)


def test_tc_at_r2_007_facade_scope_has_no_forbidden_runtime_boundaries():
    forbidden_import_roots = {"julia_core", "julia_ai_assistant", "fastapi", "mcp"}
    forbidden_call_names = {"list_active_alerts", "review_market_snapshot", "query_theme_status"}
    forbidden_text = [
        "/Users/admin/julia_core",
        "/Users/admin/julia_ai_assistant",
        "market.intent.resolve",
        "natural_language",
        "semantic_router",
        "user_text",
        "execute_order",
        "modify_strategy",
    ]

    for path in CONTRACT_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in forbidden_text:
            assert needle not in text, f"forbidden text {needle} in {path}"
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_import_roots, f"forbidden import {alias.name} in {path}"
            elif isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in forbidden_import_roots, f"forbidden import from {node.module} in {path}"
            elif isinstance(node, ast.Call):
                func = node.func
                name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
                assert name not in forbidden_call_names, f"forbidden legacy wrapper call {name} in {path}"


@pytest.mark.asyncio
async def test_tc_at_r2_008_facade_does_not_write_when_reading_alerts(tmp_path):
    _write_approved_snapshot(tmp_path, attention_level="HIGH")
    before = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    adapter = DomainIntelligenceAdapter(workbench_base_dir=str(tmp_path), clock=FixedClock())

    await adapter.execute(_request("market.alerts", {"trade_date": "2026-08-26", "min_attention_level": "HIGH"}))

    after = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert after == before

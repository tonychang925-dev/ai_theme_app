"""PR4.2.31b Eastmoney fund-flow capability audit guard."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Eastmoney_Fund_Flow_Capability_Audit.md"
A_STOCK_DATA_DIR = PROJECT_ROOT / "stock_processing_service" / "integrations" / "a_stock_data"


def test_eastmoney_fund_flow_capability_audit_document_exists() -> None:
    """TC-ID: PR4.2.31b-capability-audit-doc."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "PR4.2.31b Eastmoney Fund Flow Capability Audit" in content
    assert "Status: Audit + endpoint probe only" in content
    assert "There is no local `EastmoneyFundFlowClient`" in content
    assert "Verify live endpoint before collector" in content


def test_capability_audit_requires_period_and_market_scope_decision() -> None:
    """TC-ID: PR4.2.31b-period-market-scope-precondition."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "frequency" in content
    assert "window" in content
    assert "Do not use `period_type=5D`" in content
    assert "DAILY" in content
    assert "INTRADAY" in content
    assert "market_scope" in content
    assert "CN_A" in content
    assert "source_version" in content
    assert "Period And Window Semantics" in content


def test_capability_audit_forbids_evidence_to_intelligence_shortcuts() -> None:
    """TC-ID: PR4.2.31b-forbidden-paths."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "eastmoney_fund_flow.main_net_inflow\n  -> institution_attention" in content
    assert "stock_fund_flow_snapshot.large_net_inflow_yuan\n  -> short_term_attack_style" in content
    assert "stock_fund_flow_snapshot\n  -> ReviewDocument.capital.institution" in content
    assert "analyst report truth label\n  -> stock_fund_flow_snapshot" in content


def test_local_a_stock_data_has_no_fund_flow_collector_yet() -> None:
    """TC-ID: PR4.2.31b-local-inventory-no-live-collector."""
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in A_STOCK_DATA_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
    )

    assert "EastmoneyFundFlowClient" not in source
    assert "CollectEastmoneyFundFlowJob" not in source
    assert "stock_fund_flow_snapshot" not in source


def test_next_step_is_collector_only_not_review_document() -> None:
    """TC-ID: PR4.2.31b-next-step-collector-only."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "PR4.2.31c-1 Endpoint Probe" in content
    assert "must only print capability JSON" in content
    assert "PR4.2.31c-2 scope must remain collector-only" in content
    assert "forbidden: ReviewDocument, UI, institution/hot-money producers" in content
    assert "fallback estimates" in content


def test_probe_output_contract_is_documented() -> None:
    """TC-ID: PR4.2.31c1-probe-output-contract-doc."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "probe_eastmoney_fund_flow_fields.py" in content
    assert '"source_version": "eastmoney_fund_flow_f62_mapping_v1"' in content
    assert '"frequency": "DAILY"' in content
    assert '"window": "1D"' in content
    assert "https://push2.eastmoney.com/api/qt/clist/get" in content
    assert "http://push2.eastmoney.com/api/qt/clist/get" in content
    assert "`production_write_allowed=false`" in content
    assert "defaults to `trust_env=false`" in content
    assert "`--trust-env`" in content
    assert "proxy environment diagnostics" in content
    assert '"production_write_allowed"' not in content

"""PR4.2.31d Eastmoney push2his fund-flow adapter audit guards."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Eastmoney_Push2His_Fund_Flow_Adapter_Audit.md"


def test_eastmoney_push2his_adapter_audit_document_exists() -> None:
    """TC-ID: PR4.2.31d-push2his-audit-doc-exists."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "PR4.2.31d Eastmoney Push2His Fund Flow Adapter Audit" in content
    assert "Audit only. No production logic changes." in content
    assert "eastmoney_stock_fflow_daykline" in content
    assert "vendor_defined_order_size_proxy" in content


def test_push2his_is_canonical_daily_stock_fund_flow_source() -> None:
    """TC-ID: PR4.2.31d-push2his-canonical-source."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "push2his.eastmoney.com/api/qt/stock/fflow/daykline/get" in content
    assert "f51: date" in content
    assert "f52: net_inflow_yuan" in content
    assert "f53: small_net_inflow_yuan" in content
    assert "f54: medium_net_inflow_yuan" in content
    assert "f55: large_net_inflow_yuan" in content
    assert "f56: super_large_net_inflow_yuan" in content


def test_clist_and_sina_are_not_canonical_daily_replacements() -> None:
    """TC-ID: PR4.2.31d-noncanonical-source-guards."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "Why Push2His, Not Clist" in content
    assert "clist/get live ranking\n  -> stock_fund_flow_snapshot canonical daily history" in content
    assert "sina_fund_flow partial fields\n  -> complete stock_fund_flow_snapshot replacement" in content
    assert "Sina is not a full replacement for Eastmoney daykline evidence" in content


def test_push2his_audit_forbids_evidence_to_intelligence_shortcuts() -> None:
    """TC-ID: PR4.2.31d-push2his-forbidden-intelligence-shortcuts."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "eastmoney_fund_flow.net_inflow_yuan > 0\n  -> institution_attention" in content
    assert "eastmoney_fund_flow.large_net_inflow_yuan > 0\n  -> hot_money_style" in content
    assert "analyst report truth label\n  -> stock_fund_flow_snapshot" in content
    assert "Do not connect frontend or ReviewDocument yet." in content


def test_push2his_next_stage_is_source_arbitration_then_theme_evidence() -> None:
    """TC-ID: PR4.2.31d-push2his-next-stage-sequence."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "PR4.2.31e Evidence Source Arbitration" in content
    assert "PR4.2.32 Theme Fund Flow Evidence" in content
    assert "Only after theme-level evidence exists" in content

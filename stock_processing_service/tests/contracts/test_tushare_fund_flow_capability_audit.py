"""PR4.2.31e Tushare fund-flow capability audit guards."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Tushare_Fund_Flow_Capability_Audit.md"


def test_tushare_fund_flow_capability_audit_document_exists() -> None:
    """TC-ID: PR4.2.31e-tushare-audit-doc-exists."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "PR4.2.31e Tushare Fund Flow Capability Audit" in content
    assert "No collector, ReviewDocument, frontend" in content
    assert "production_write_allowed: false" in content


def test_tushare_audit_lists_core_interfaces() -> None:
    """TC-ID: PR4.2.31e-tushare-core-interfaces."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "tushare.moneyflow_ths" in content
    assert "tushare.moneyflow_cnt_ths" in content
    assert "tushare.moneyflow_hsgt" in content
    assert "tushare.moneyflow" in content


def test_tushare_audit_defines_source_ownership() -> None:
    """TC-ID: PR4.2.31e-tushare-source-ownership."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "stock_fund_flow_snapshot:" in content
    assert "primary_post_market_source: tushare.moneyflow_ths" in content
    assert "theme_fund_flow_snapshot:" in content
    assert "primary_post_market_source: tushare.moneyflow_cnt_ths" in content


def test_tushare_audit_forbids_direct_intelligence_mapping() -> None:
    """TC-ID: PR4.2.31e-tushare-forbidden-intelligence-shortcuts."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "tushare.moneyflow_ths.net_amount > 0\n  -> institution_attention" in content
    assert "tushare.moneyflow_cnt_ths.net_amount > 0\n  -> hot_money_style" in content
    assert "Tushare fund-flow\n  -> Evidence Layer" in content


def test_tushare_audit_records_direct_network_test_note() -> None:
    """TC-ID: PR4.2.31e-tushare-direct-network-note."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "Run with VPN disabled / direct domestic route" in content

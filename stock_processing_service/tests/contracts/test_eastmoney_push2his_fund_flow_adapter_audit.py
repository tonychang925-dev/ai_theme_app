"""PR4.2.31d-1 Eastmoney official client reverse audit guards."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Eastmoney_Push2His_Fund_Flow_Adapter_Audit.md"


def test_eastmoney_push2his_adapter_audit_document_exists() -> None:
    """TC-ID: PR4.2.31d1-push2his-audit-doc-exists."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "PR4.2.31d-1 Eastmoney Official Client Reverse Audit" in content
    assert "No ReviewDocument, frontend, source" in content
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


def test_push2his_audit_records_a_stock_data_request_shape() -> None:
    """TC-ID: PR4.2.31d1-a-stock-data-request-shape."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "stock_fund_flow_120d(code)" in content
    assert "python_source_files: []" in content
    assert "documented code-block reference" in content
    assert "fields2: f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f62,f63,f64,f65" in content
    assert "Origin: https://quote.eastmoney.com" in content
    assert "session_reuse: true" in content
    assert "min_interval: \">=1s + jitter\"" in content


def test_push2his_audit_records_akshare_as_separate_variant() -> None:
    """TC-ID: PR4.2.31d1-akshare-variant-separated."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "AKShare Reference Difference" in content
    assert "ut: b2884a393a59ad64002292a3e90d46a5" in content
    assert "klt: \"101\"" in content
    assert "The production client should not silently\nmix variants" in content


def test_push2his_audit_requires_browser_har_field_diff() -> None:
    """TC-ID: PR4.2.31d2-browser-har-diff-fields."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "Required HAR comparison fields" in content
    assert "  - Cookie" in content
    assert "  - cb" in content
    assert "  - invt" in content
    assert "  - http_version" in content


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


def test_push2his_next_stage_is_official_request_verification_then_theme_evidence() -> None:
    """TC-ID: PR4.2.31d1-push2his-next-stage-sequence."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "PR4.2.31d-2 Eastmoney Official Request Verification" in content
    assert "compare with browser network capture when available" in content
    assert "PR4.2.32 Theme Fund Flow Evidence" in content
    assert "Only after theme-level evidence exists" in content

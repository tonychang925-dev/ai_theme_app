"""PR4.2.31a stock fund-flow evidence source ownership guard."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Stock_Fund_Flow_Evidence_Contract.md"
SQL_PATH = PROJECT_ROOT / "database_service" / "scripts" / "create_stock_fund_flow_snapshot.sql"
MODULE_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "application"
    / "services"
    / "capital_evidence"
    / "stock_fund_flow.py"
)


def test_stock_fund_flow_evidence_contract_document_exists() -> None:
    """TC-ID: PR4.2.31a-stock-fund-flow-contract-doc."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "PR4.2.31a Stock Fund Flow Evidence Contract" in content
    assert "Contract + normalizer only" in content
    assert "stock_fund_flow_snapshot" in content
    assert "VENDOR_DEFINED_ORDER_SIZE_FLOW" in content


def test_stock_fund_flow_snapshot_schema_is_daily_evidence_not_truth_table() -> None:
    """TC-ID: PR4.2.31a-stock-fund-flow-schema."""
    sql = SQL_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS stock_fund_flow_snapshot" in sql
    assert "trade_date DATE NOT NULL" in sql
    assert "net_inflow_yuan" in sql
    assert "super_large_net_inflow_yuan" in sql
    assert "large_net_inflow_yuan" in sql
    assert "medium_net_inflow_yuan" in sql
    assert "small_net_inflow_yuan" in sql
    assert "source_version TEXT NOT NULL DEFAULT ''" in sql
    assert "frequency TEXT NOT NULL DEFAULT 'DAILY'" in sql
    assert '"window" TEXT NOT NULL DEFAULT \'1D\'' in sql
    assert "market_scope TEXT NOT NULL DEFAULT 'CN_A'" in sql
    assert 'PRIMARY KEY (trade_date, stock_code, source_name, source_endpoint, source_version, frequency, "window", market_scope)' in sql
    assert "uq_stock_fund_flow_snapshot_identity" in sql
    assert "stock_daily_snapshot" not in sql


def test_forbidden_paths_are_documented() -> None:
    """TC-ID: PR4.2.31a-stock-fund-flow-forbidden-paths."""
    content = DOC_PATH.read_text(encoding="utf-8")

    assert "stock_fund_flow_snapshot.net_inflow_yuan > 0\n  -> institution_attention" in content
    assert "stock_fund_flow_snapshot.large_net_inflow_yuan > 0\n  -> short_term_attack_style" in content
    assert "stock_fund_flow_snapshot\n  -> ReviewDocument.capital.institution" in content
    assert "stock_fund_flow_snapshot\n  -> ReviewDocument.capital.hot_money" in content


def test_normalizer_module_does_not_emit_style_or_participant_identity() -> None:
    """TC-ID: PR4.2.31a-stock-fund-flow-no-style-output."""
    source = MODULE_PATH.read_text(encoding="utf-8")

    assert "institution_style" not in source
    assert "hot_money_style" not in source
    assert "institution_attention" not in source
    assert "short_term_attack_style" not in source
    assert "participant_type" in source
    assert "vendor_order_size_proxy" in source

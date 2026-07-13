"""PR4.2.31a stock fund-flow evidence contract tests."""

from __future__ import annotations

from datetime import date

from stock_processing_service.application.services.capital_evidence.stock_fund_flow import (
    EastmoneyStockFundFlowNormalizer,
    SOURCE_EASTMONEY_FUND_FLOW,
)


def test_eastmoney_stock_fund_flow_normalizer_preserves_order_size_facts() -> None:
    """TC-ID: PR4.2.31a-stock-fund-flow-normalizer."""
    row = {
        "f12": "002747",
        "f14": "埃斯顿",
        "f62": 123_450_000,
        "f66": 50_000_000,
        "f72": 30_000_000,
        "f78": -10_000_000,
        "f84": -20_000_000,
    }

    evidence = EastmoneyStockFundFlowNormalizer().normalize_row(row, date(2026, 7, 9))

    assert evidence.trade_date == date(2026, 7, 9)
    assert evidence.stock_code == "002747"
    assert evidence.stock_name == "埃斯顿"
    assert evidence.net_inflow_yuan == 123_450_000
    assert evidence.super_large_net_inflow_yuan == 50_000_000
    assert evidence.large_net_inflow_yuan == 30_000_000
    assert evidence.medium_net_inflow_yuan == -10_000_000
    assert evidence.small_net_inflow_yuan == -20_000_000
    assert evidence.source_name == SOURCE_EASTMONEY_FUND_FLOW
    assert evidence.source_endpoint == "eastmoney_stock_fund_flow"
    assert evidence.source_quality == "VENDOR_DEFINED_ORDER_SIZE_FLOW"
    assert evidence.quality == "OK"
    assert evidence.diagnostics["identity_inference"] is False
    assert evidence.diagnostics["participant_type"] == "unknown"
    assert evidence.diagnostics["semantics"] == "vendor_order_size_proxy"


def test_stock_fund_flow_evidence_row_has_no_identity_labels() -> None:
    """TC-ID: PR4.2.31a-stock-fund-flow-no-identity-labels."""
    evidence = EastmoneyStockFundFlowNormalizer().normalize_row(
        {"stock_code": "002747", "stock_name": "埃斯顿", "net_inflow": 1},
        date(2026, 7, 9),
    )

    row = evidence.to_row()

    assert "institution" not in row
    assert "hot_money" not in row
    assert "style" not in row
    assert row["net_inflow_yuan"] == 1
    assert row["source_name"] == "eastmoney_fund_flow"


def test_stock_fund_flow_missing_net_inflow_is_missing_not_default_zero() -> None:
    """TC-ID: PR4.2.31a-stock-fund-flow-missing-fail-closed."""
    evidence = EastmoneyStockFundFlowNormalizer().normalize_row(
        {"stock_code": "002747", "stock_name": "埃斯顿"},
        date(2026, 7, 9),
    )

    assert evidence.net_inflow_yuan is None
    assert evidence.quality == "MISSING"
    assert "net_inflow_yuan" in evidence.diagnostics["missing"]


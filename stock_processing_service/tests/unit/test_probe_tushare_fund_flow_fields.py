"""PR4.2.31e Tushare fund-flow capability probe tests."""

from __future__ import annotations

from stock_processing_service.scripts.probe_tushare_fund_flow_fields import (
    FORBIDDEN_INTERPRETATIONS,
    INTERFACE_FIELD_CONTRACTS,
    normalize_trade_date,
    probe_tushare_fund_flow,
    summarize_interface_error,
    summarize_records,
)


def test_tushare_fund_flow_contract_lists_core_interfaces() -> None:
    """TC-ID: PR4.2.31e-tushare-fund-flow-interface-contract."""
    assert set(INTERFACE_FIELD_CONTRACTS) == {
        "moneyflow",
        "moneyflow_ths",
        "moneyflow_cnt_ths",
        "moneyflow_hsgt",
    }
    assert INTERFACE_FIELD_CONTRACTS["moneyflow_ths"]["source_endpoint"] == "tushare.moneyflow_ths"
    assert INTERFACE_FIELD_CONTRACTS["moneyflow_cnt_ths"]["role"] == "concept_fund_flow_ths"


def test_tushare_probe_normalizes_trade_date() -> None:
    """TC-ID: PR4.2.31e-tushare-date-normalization."""
    assert normalize_trade_date("2026-07-09") == "20260709"
    assert normalize_trade_date("20260709") == "20260709"


def test_tushare_moneyflow_ths_supported_summary() -> None:
    """TC-ID: PR4.2.31e-tushare-moneyflow-ths-supported."""
    result = summarize_records(
        "moneyflow_ths",
        [
            {
                "trade_date": "20260709",
                "ts_code": "300223.SZ",
                "name": "北京君正",
                "net_amount": 123.0,
                "net_d5_amount": 456.0,
                "buy_lg_amount": 1.0,
                "buy_lg_amount_rate": 0.1,
                "buy_md_amount": 2.0,
                "buy_md_amount_rate": 0.2,
                "buy_sm_amount": 3.0,
                "buy_sm_amount_rate": 0.3,
            }
        ],
    )

    assert result["capability"] == "SUPPORTED"
    assert result["production_write_allowed"] is False
    assert result["semantics"] == "vendor_defined_order_size_or_cross_border_flow"
    assert result["row_count"] == 1


def test_tushare_partial_fields_are_marked_partial_supported() -> None:
    """TC-ID: PR4.2.31e-tushare-partial-fields."""
    result = summarize_records("moneyflow_cnt_ths", [{"trade_date": "20260709", "name": "机器人"}])

    assert result["capability"] == "PARTIAL_SUPPORTED"
    assert "net_amount" in result["missing_expected_fields"]
    assert result["production_write_allowed"] is False


def test_tushare_interface_error_is_fail_closed() -> None:
    """TC-ID: PR4.2.31e-tushare-interface-error-fail-closed."""
    result = summarize_interface_error("moneyflow_hsgt", RuntimeError("permission denied"))

    assert result["capability"] == "UNKNOWN"
    assert result["error_type"] == "RuntimeError"
    assert result["production_write_allowed"] is False


def test_tushare_missing_token_probe_does_not_write() -> None:
    """TC-ID: PR4.2.31e-tushare-missing-token-no-write."""
    result = probe_tushare_fund_flow(token="", trade_date="2026-07-09", ts_code="300223.SZ")

    assert result["capability"] == "UNKNOWN"
    assert result["supported_interfaces"] == []
    assert result["production_write_allowed"] is False
    assert "moneyflow_ths" in result["interfaces"]
    assert any("institution_attention" in item for item in result["forbidden_interpretations"])
    assert FORBIDDEN_INTERPRETATIONS

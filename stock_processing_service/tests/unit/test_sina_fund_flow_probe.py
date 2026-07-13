"""PR4.2.31d Sina fund-flow backup probe tests."""

from __future__ import annotations

from stock_processing_service.scripts.probe_sina_fund_flow_fields import (
    FIELD_ALIASES,
    SINA_DAILY_URLS,
    parse_sina_payload,
    sina_symbol,
    summarize_sina_capability,
)


def test_sina_probe_contract_constants() -> None:
    """TC-ID: PR4.2.31d-sina-probe-contract-constants."""
    assert SINA_DAILY_URLS == (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs",
        "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs",
    )
    assert sina_symbol("300223") == "sz300223"
    assert sina_symbol("002747.SZ") == "sz002747"
    assert sina_symbol("600520.SH") == "sh600520"
    assert "net_inflow_yuan" in FIELD_ALIASES
    assert "super_large_net_inflow_yuan" in FIELD_ALIASES


def test_sina_probe_parses_jsonp_payload() -> None:
    """TC-ID: PR4.2.31d-sina-probe-jsonp-parse."""
    payload = parse_sina_payload(
        'callback([{"opendate":"2026-07-09","netamount":"100.0","r0_net":"60.0",'
        '"r1_net":"30.0","r2_net":"-10.0","r3_net":"20.0"}]);'
    )

    assert isinstance(payload, list)
    assert payload[0]["opendate"] == "2026-07-09"


def test_sina_probe_summarizes_supported_fixture() -> None:
    """TC-ID: PR4.2.31d-sina-probe-supported-fixture."""
    payload = [
        {
            "opendate": "2026-07-09",
            "netamount": "100.0",
            "r0_net": "60.0",
            "r1_net": "30.0",
            "r2_net": "-10.0",
            "r3_net": "20.0",
        }
    ]

    result = summarize_sina_capability(payload, request_url="fixture://sina", stock_code="300223")

    assert result["source_name"] == "sina_fund_flow"
    assert result["capability"] == "SUPPORTED"
    assert result["frequency"] == "DAILY"
    assert result["window"] == "1D"
    assert result["semantics"] == "vendor_defined_order_size_proxy"
    assert result["production_write_allowed"] is False
    assert result["resolved_field_mapping"]["net_inflow_yuan"]["raw_key"] == "netamount"
    assert result["examples"][0]["fund_flow_fields"]["super_large_net_inflow_yuan"] == "60.0"


def test_sina_probe_unknown_when_required_fields_missing() -> None:
    """TC-ID: PR4.2.31d-sina-probe-unknown-incomplete-fields."""
    result = summarize_sina_capability(
        [{"opendate": "2026-07-09", "netamount": "100.0"}],
        request_url="fixture://sina",
        stock_code="300223",
    )

    assert result["capability"] == "UNKNOWN"
    assert result["production_write_allowed"] is False

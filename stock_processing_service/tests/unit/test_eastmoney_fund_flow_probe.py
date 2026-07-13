"""PR4.2.31c-1 Eastmoney fund-flow probe tests."""

from __future__ import annotations

from stock_processing_service.scripts.probe_eastmoney_fund_flow_fields import (
    EASTMONEY_HEADERS,
    EM_BASE_URLS,
    FIELD_MAPPING,
    build_probe_params,
    proxy_env_diagnostics,
    summarize_all_fetch_errors,
    summarize_capability,
)


def test_probe_requests_order_size_fund_flow_fields() -> None:
    """TC-ID: PR4.2.31c1-probe-request-fields."""
    params = build_probe_params(page_size=5)

    assert params["fields"] == "f12,f14,f62,f66,f72,f78,f84"
    assert params["fid"] == "f62"
    assert params["pz"] == 5
    assert "m:0+t:6" in params["fs"]


def test_probe_uses_eastmoney_headers_and_multiple_candidate_urls() -> None:
    """TC-ID: PR4.2.31c1b-probe-connection-hardening."""
    assert EM_BASE_URLS == (
        "https://push2.eastmoney.com/api/qt/clist/get",
        "http://push2.eastmoney.com/api/qt/clist/get",
    )
    assert EASTMONEY_HEADERS["Referer"] == "https://quote.eastmoney.com/"
    assert "Mozilla/5.0" in EASTMONEY_HEADERS["User-Agent"]


def test_probe_summarizes_supported_fund_flow_fixture() -> None:
    """TC-ID: PR4.2.31c1-probe-supported-fixture."""
    payload = {
        "data": {
            "diff": [
                {
                    "f12": "300223",
                    "f14": "北京君正",
                    "f62": 100.0,
                    "f66": 20.0,
                    "f72": 30.0,
                    "f78": -10.0,
                    "f84": -40.0,
                }
            ]
        }
    }

    result = summarize_capability(payload, request_url="fixture://fund-flow")

    assert result["capability"] == "SUPPORTED"
    assert result["production_write_allowed"] is False
    assert result["frequency"] == "DAILY"
    assert result["window"] == "1D"
    assert result["market_scope"] == "CN_A"
    assert result["source_version"] == "eastmoney_fund_flow_f62_mapping_v1"
    assert result["field_mapping"] == FIELD_MAPPING
    assert result["field_candidate_counts"] == {
        "f62": 1,
        "f66": 1,
        "f72": 1,
        "f78": 1,
        "f84": 1,
    }


def test_probe_does_not_treat_partial_fields_as_supported() -> None:
    """TC-ID: PR4.2.31c1-probe-partial-fields-fail-closed."""
    payload = {"data": {"diff": [{"f12": "300223", "f14": "北京君正", "f62": 100.0}]}}

    result = summarize_capability(payload, request_url="fixture://partial")

    assert result["capability"] == "UNAVAILABLE"
    assert result["production_write_allowed"] is False
    assert result["decision"] == "Stock fund-flow capability is not proven by this response; do not add collector."


def test_probe_reports_all_candidate_url_errors_without_allowing_writes() -> None:
    """TC-ID: PR4.2.31c1b-probe-all-errors-fail-closed."""
    result = summarize_all_fetch_errors(
        [
            {"request_url": EM_BASE_URLS[0], "error_type": "RemoteProtocolError", "error": "disconnect"},
            {"request_url": EM_BASE_URLS[1], "error_type": "ConnectTimeout", "error": "timeout"},
        ]
    )

    assert result["capability"] == "UNKNOWN"
    assert result["production_write_allowed"] is False
    assert result["candidate_urls"] == list(EM_BASE_URLS)
    assert result["errors"][0]["error_type"] == "RemoteProtocolError"


def test_probe_proxy_env_diagnostics_are_boolean(monkeypatch) -> None:
    """TC-ID: PR4.2.31c1c-probe-proxy-env-diagnostics."""
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:7890")
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    diagnostics = proxy_env_diagnostics()

    assert diagnostics["HTTPS_PROXY"] is True
    assert diagnostics["HTTP_PROXY"] is False

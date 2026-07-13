"""PR4.2.31c-1 Eastmoney fund-flow probe tests."""

from __future__ import annotations

from stock_processing_service.scripts.probe_eastmoney_fund_flow_fields import (
    FIELD_MAPPING,
    build_probe_params,
    summarize_capability,
)


def test_probe_requests_order_size_fund_flow_fields() -> None:
    """TC-ID: PR4.2.31c1-probe-request-fields."""
    params = build_probe_params(page_size=5)

    assert params["fields"] == "f12,f14,f62,f66,f72,f78,f84"
    assert params["fid"] == "f62"
    assert params["pz"] == 5
    assert "m:0+t:6" in params["fs"]


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


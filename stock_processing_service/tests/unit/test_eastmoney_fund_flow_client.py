"""PR4.2.31c-3 Eastmoney fund-flow client tests."""

from __future__ import annotations

from stock_processing_service.integrations.a_stock_data.clients.eastmoney_fund_flow_client import (
    DAYKLINE_ENDPOINT,
    SOURCE_NAME,
    default_fund_flow_policy,
    secid_from_stock_code,
)


def test_eastmoney_fund_flow_client_contract_constants() -> None:
    """TC-ID: PR4.2.31c3-client-contract-constants."""
    assert SOURCE_NAME == "eastmoney_fund_flow"
    assert DAYKLINE_ENDPOINT == "eastmoney_stock_fflow_daykline"
    assert secid_from_stock_code("300223") == "0.300223"
    assert secid_from_stock_code("002747.SZ") == "0.002747"
    assert secid_from_stock_code("600520.SH") == "1.600520"


def test_eastmoney_fund_flow_default_policy_is_conservative() -> None:
    """TC-ID: PR4.2.31c4-fund-flow-conservative-source-policy."""
    policy = default_fund_flow_policy()

    assert policy.min_interval_ms >= 2500
    assert policy.jitter_ms >= 1000
    assert policy.max_retries >= 3
    assert policy.backoff == "exponential"
    assert policy.session_reuse is False
    assert policy.accept == "*/*"
    assert policy.connection == "close"

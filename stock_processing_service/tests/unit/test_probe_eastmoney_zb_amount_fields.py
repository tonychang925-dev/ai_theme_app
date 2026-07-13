"""PR4.2.28d Eastmoney ZB amount-field verification probe tests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from stock_processing_service.scripts.probe_eastmoney_zb_amount_fields import (
    build_zb_probe_params,
    summarize_capability,
    summarize_fetch_error,
)


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = PROJECT_ROOT / "stock_processing_service" / "tests" / "fixtures"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def test_zb_probe_requests_amount_candidate_fields() -> None:
    """TC-ID: PR4.2.28d-zb-probe-requests-f6."""
    params = build_zb_probe_params(date(2026, 7, 9), 30)

    assert params["date"] == "20260709"
    assert "f6" in params["fields"].split(",")
    assert "f62" in params["fields"].split(",")
    assert "f116" in params["fields"].split(",")


def test_zb_probe_reports_supported_when_amount_field_exists() -> None:
    """TC-ID: PR4.2.28d-zb-probe-supported-fixture."""
    summary = summarize_capability(_fixture("eastmoney_zb_pool_with_f6.json"))

    assert summary["endpoint"] == "getTopicZBPool"
    assert summary["capability"] == "SUPPORTED"
    assert summary["amount_candidate_counts"] == {"amount": 1}
    assert summary["examples"][0]["code"] == "605006"
    assert summary["examples"][0]["amount_fields"]["amount"] == 1161153713.0


def test_zb_probe_reports_unavailable_without_amount_field() -> None:
    """TC-ID: PR4.2.28d-zb-probe-unavailable-fixture."""
    summary = summarize_capability(_fixture("eastmoney_zb_pool_without_amount.json"))

    assert summary["capability"] == "UNAVAILABLE"
    assert summary["amount_candidate_counts"] == {}
    assert summary["examples"] == []
    assert "keep BoardPoolSnapshot.zb.amount_yi MISSING" in summary["decision"]


def test_zb_probe_reports_unknown_on_live_fetch_error() -> None:
    """TC-ID: PR4.2.28d-zb-probe-network-error-is-structured."""
    summary = summarize_fetch_error(TimeoutError("connect timeout"))

    assert summary["capability"] == "UNKNOWN"
    assert summary["error_type"] == "TimeoutError"
    assert summary["amount_candidate_counts"] == {}
    assert "not verified" in summary["decision"]

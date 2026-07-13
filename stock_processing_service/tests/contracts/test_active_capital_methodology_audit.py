"""PR4.2.24a Active Capital methodology audit guard.

TC-ID: PR4.2.24a-active-capital-methodology

This is an audit-only contract test. It locks the business definition before
any producer or UI changes are allowed.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Active_Capital_Methodology_Audit.md"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_active_capital_audit_document_exists() -> None:
    assert DOC_PATH.exists()
    content = _doc()
    assert "Active Capital Methodology Audit" in content
    assert "ActiveCapitalProducer" in content
    assert "2707亿" in content
    assert "5058.28亿" in content


def test_active_capital_is_not_market_turnover() -> None:
    content = _doc()
    assert "`active_capital`" in content
    assert "analyst-style short-term active capital estimate" in content
    assert "market_turnover\n  -> active_capital" in content


def test_fixed_multiplier_is_forbidden_as_truth_model() -> None:
    content = _doc()
    assert "current fixed multiplier | 2.04" in content
    assert "hidden fixed multiplier is forbidden" in content
    assert "limit_up_pool_turnover\n  -> fixed_factor(2.04)\n  -> active_capital" in content


def test_capital_trend_must_not_use_total_turnover() -> None:
    content = _doc()
    assert "trend_series.capital[].amount = total_turnover_yi / 10000" in content
    assert 'trend_series.capital[].unit = "yi"' in content
    assert "trend_series.capital\n  -> total_turnover_yi / 10000" in content


def test_stale_golden_values_are_not_production_truth() -> None:
    content = _doc()
    assert "capital.active_amount = 5058.28" in content
    assert "Golden Replay must be treated as stale for these fields" in content
    assert "stale golden value 5058.28\n  -> production truth" in content

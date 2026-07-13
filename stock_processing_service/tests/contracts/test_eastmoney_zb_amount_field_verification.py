"""PR4.2.28d Eastmoney ZB amount field verification guard."""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Eastmoney_ZB_Amount_Field_Verification.md"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_eastmoney_zb_amount_verification_document_exists() -> None:
    assert DOC_PATH.exists()
    content = _doc()
    assert "Eastmoney ZB Amount Field Verification" in content
    assert "PR4.2.28d Eastmoney ZB Amount Field Verification" in content
    assert "probe_eastmoney_zb_amount_fields.py" in content


def test_verification_is_not_production_change() -> None:
    content = _doc()
    assert "Do not modify production data flow yet" in content
    assert "does not persist data" in content
    assert "not used by ReviewDocument generation" in content


def test_live_probe_supported_but_persistence_still_required() -> None:
    content = _doc()
    assert '"capability": "SUPPORTED"' in content
    assert '"amount": 1480394240' in content
    assert "verified as `SUPPORTED`" in content
    assert "persisted 2026-07-09\n`eastmoney_board_pool_daily` rows still have `ZB.amount = 0`" in content
    assert "`BoardPoolSnapshot.zb.amount_yi` remains `MISSING`" in content


def test_forbidden_paths_prevent_runtime_or_estimated_usage() -> None:
    content = _doc()
    assert "live endpoint amount\n  -> runtime ReviewDocument generation" in content
    assert "ZB.turnover_rate\n  -> ZB.amount_yi" in content
    assert "analyst_report.active_capital_yi\n  -> production active_capital.value_yi" in content
    assert "Use runtime Eastmoney response directly in ReviewDocument generation" in content

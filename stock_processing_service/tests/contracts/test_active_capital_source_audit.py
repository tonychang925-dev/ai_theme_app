"""PR4.2.28a Active Capital source audit guard.

TC-ID: PR4.2.28a-active-capital-source-audit

This is an audit-only contract test. It locks the source ownership boundary for
the next ActiveCapitalProducer PR and prevents future agents from treating
nearby capital/theme evidence as the active-capital truth source.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "Active_Capital_Source_Audit.md"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_active_capital_source_audit_document_exists() -> None:
    assert DOC_PATH.exists()
    content = _doc()
    assert "Active Capital Source Audit" in content
    assert "PR4.2.28a Active Capital Source Audit" in content
    assert "ActiveCapitalProducer" in content
    assert "2707 亿" in content
    assert "5058.28 亿" in content
    assert "86.86%" in content


def test_current_fixed_multiplier_path_is_documented_and_forbidden() -> None:
    content = _doc()
    assert "fixed multiplier 2.04" in content
    assert "implied analyst factor vs THS+SDS pool | 1.092" in content
    assert "limit_up_pool_turnover\n  -> fixed_factor(2.04)\n  -> active_capital" in content
    assert "reintroducing the `2.04`\nmultiplier" in content


def test_board_pool_owner_must_be_selected_before_implementation() -> None:
    content = _doc()
    assert "Which concrete board-pool source" in content
    assert "sealed and touched/fried\n   stocks with turnover for historical dates" in content
    assert "Proceed to `PR4.2.28b Active Capital Producer` only after selecting the concrete\nboard-pool owner" in content


def test_theme_sources_are_evidence_not_amount_owner() -> None:
    content = _doc()
    assert "`subject_stock_daily_snapshot` can support theme distribution and evidence" in content
    assert "not a clean amount source" in content
    assert "`theme_capital_flow` must not be used as the active-capital amount owner" in content
    assert "theme_capital_flow\n  -> active_amount" in content


def test_dragon_tiger_and_frontend_are_forbidden_active_amount_sources() -> None:
    content = _doc()
    assert "`dragon_tiger_object` | 0 rows" in content
    assert "`hot_money_trading_activity` | 0 rows" in content
    assert "dragon_tiger rows missing\n  -> inferred hot_money amount" in content
    assert "frontend formatting\n  -> active amount correction" in content


def test_hardcoded_analyst_truth_is_forbidden() -> None:
    content = _doc()
    assert "Add contract tests for component output and `2026-07-09 -> 2707`" in content
    assert "date == 2026-07-09\n  -> hardcoded 2707" in content

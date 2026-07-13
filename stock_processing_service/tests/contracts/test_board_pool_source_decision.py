"""PR4.2.28b-pre BoardPool source decision guard.

TC-ID: PR4.2.28b-pre-board-pool-source-decision

This audit-only guard freezes the BoardPoolSnapshot source owner before
ActiveCapitalProducer implementation. It prevents active capital from being
rebuilt from runtime APIs, fixed multipliers, or analyst truth labels.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "BoardPool_Source_Decision.md"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_board_pool_source_decision_document_exists() -> None:
    assert DOC_PATH.exists()
    content = _doc()
    assert "BoardPool Source Decision" in content
    assert "PR4.2.28b-pre BoardPool Source Owner Decision" in content
    assert "BoardPoolSnapshot" in content
    assert "eastmoney_board_pool_daily" in content


def test_eastmoney_board_pool_is_owner_but_not_final_active_capital() -> None:
    content = _doc()
    assert "Use `eastmoney_board_pool_daily` as the persisted source owner" in content
    assert "`ZT.amount` is a valid component, not the final active-capital value" in content
    assert "Do not implement `ActiveCapitalProducer` until `BoardPoolSnapshot` exposes" in content


def test_20260709_amount_gap_and_zb_missing_amount_are_locked() -> None:
    content = _doc()
    assert "| `ZT` | 75 | 75 | 2479.55 亿 |" in content
    assert "| `ZB` | 17 | 0 | 0 亿 |" in content
    assert "| Analyst active capital | 2707 亿 |" in content
    assert "| Remaining gap | 227.45 亿 |" in content
    assert "`ZB` exists as a stock set, but amount is missing" in content


def test_runtime_api_is_rejected_for_review_document_generation() -> None:
    content = _doc()
    assert "Call Eastmoney/a-stock-data from `ActiveCapitalProducer` at generation time" in content
    assert "Rejected for ReviewDocument generation" in content
    assert "runtime Eastmoney API\n  -> ReviewDocument artifact" in content


def test_forbidden_paths_block_multiplier_and_truth_label_leakage() -> None:
    content = _doc()
    assert "ZT.amount\n  -> fixed_factor\n  -> active_capital" in content
    assert "analyst_report.active_capital_yi\n  -> production active_amount" in content
    assert "theme_capital_flow\n  -> active_capital.value_yi" in content
    assert "Hardcode `2707`" in content


def test_next_pr_is_board_pool_amount_completeness_not_full_capital_model() -> None:
    content = _doc()
    assert "PR4.2.28b BoardPoolSnapshot Amount Completeness" in content
    assert "Keep `ActiveCapitalProducer` disabled or degraded until amount-complete" in content
    assert "Add diagnostics proving `ZB.amount_yi` is missing for 2026-07-09" in content

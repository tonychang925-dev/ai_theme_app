"""PR4.2.28c BoardPool amount completion audit guard.

TC-ID: PR4.2.28c-board-pool-amount-completion-audit

This is audit-only. It locks the finding that ZB/YZT amount is missing from the
persisted board-pool payload and prevents active capital from being computed
from sealed ZT amount alone.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = PROJECT_ROOT / "docs" / "architecture" / "BoardPool_Amount_Completion_Audit.md"


def _doc() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_board_pool_amount_completion_audit_document_exists() -> None:
    assert DOC_PATH.exists()
    content = _doc()
    assert "BoardPool Amount Completion Audit" in content
    assert "PR4.2.28c BoardPool ZB/YZT Amount Source Audit" in content
    assert "active_capital:" in content
    assert "quality: DEGRADED" in content


def test_zt_is_not_active_capital_without_zb_amount() -> None:
    content = _doc()
    assert "ZT.amount_yi = 2479.55" in content
    assert "今日所有涨停及触及涨停个股成交量之和 = 2707 亿" in content
    assert "ZT.amount_yi\n  -> active_capital.value_yi" in content


def test_raw_json_audit_locks_zb_and_yzt_missing_amount() -> None:
    content = _doc()
    assert "`ZB.raw_json` does not currently contain `amount`" in content
    assert "`YZT.raw_json` does not currently contain today amount" in content
    assert "persisted payload is missing amount fields" in content


def test_eastmoney_zb_f6_gap_is_documented() -> None:
    content = _doc()
    assert "`fetch_zt_pool` requests:" in content
    assert "f12,f14,f2,f3,f4,f6" in content
    assert "`fetch_zb_pool` requests:" in content
    assert "It does not request `f6`" in content
    assert "does not prove that `getTopicZBPool` supports `f6`" in content


def test_quote_join_requires_explicit_amount_adapter() -> None:
    content = _doc()
    assert "Acceptable only with an explicit `BoardPoolAmountAdapter`" in content
    assert "`stock_daily_snapshot.amount` with\n  `qian_yuan -> yi`" in content
    assert "an explicit unit adapter is mandatory" in content


def test_next_pr_is_zb_amount_verification_not_active_capital_output() -> None:
    content = _doc()
    assert "PR4.2.28d Eastmoney ZB Amount Field Verification" in content
    assert "Probe `getTopicZBPool` with `f6` included in fields" in content
    assert "Modify active capital output" in content
    assert "Hardcode `2707`" in content

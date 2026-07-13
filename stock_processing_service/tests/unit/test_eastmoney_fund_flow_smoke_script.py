"""PR4.2.31c-4 fund-flow smoke script tests."""

from __future__ import annotations

from datetime import date
import sys

from stock_processing_service.scripts import run_eastmoney_fund_flow_smoke
from stock_processing_service.scripts.run_eastmoney_fund_flow_smoke import (
    _progress,
    _summarize_rows,
    _summarize_run_health,
)


def test_smoke_script_adds_project_root_to_syspath() -> None:
    """TC-ID: PR4.2.31c4-smoke-script-import-path."""
    assert str(run_eastmoney_fund_flow_smoke.PROJECT_ROOT) in sys.path


def test_smoke_summary_detects_identity_duplicates_and_required_fields() -> None:
    """TC-ID: PR4.2.31c4-smoke-summary-contract."""
    row = {
        "trade_date": date(2026, 7, 9),
        "stock_code": "300223",
        "source_name": "eastmoney_fund_flow",
        "source_endpoint": "eastmoney_stock_fflow_daykline",
        "source_version": "eastmoney_fflow_daykline_f52_v1",
        "frequency": "DAILY",
        "window": "1D",
        "market_scope": "CN_A",
        "net_inflow_yuan": 100,
        "super_large_net_inflow_yuan": 60,
        "large_net_inflow_yuan": 30,
        "medium_net_inflow_yuan": -10,
        "small_net_inflow_yuan": 20,
        "quality": "OK",
    }

    summary = _summarize_rows([row, dict(row)])

    assert summary["row_count"] == 2
    assert summary["duplicate_identity_count"] == 1
    assert summary["missing_required"] == []
    assert summary["quality_counts"] == {"OK": 2}


def test_smoke_progress_can_be_disabled(capsys) -> None:
    """TC-ID: PR4.2.31c4-smoke-progress-visibility."""
    _progress("[smoke] visible", enabled=True)
    visible = capsys.readouterr()
    assert "[smoke] visible" in visible.err

    _progress("[smoke] hidden", enabled=False)
    hidden = capsys.readouterr()
    assert hidden.err == ""


class _Result:
    def __init__(self, affected_rows: int, warnings: list[str] | None = None) -> None:
        self.affected_rows = affected_rows
        self.warnings = warnings or []


def test_smoke_run_health_marks_stale_readback() -> None:
    """TC-ID: PR4.2.31c4-smoke-run-health-stale-readback."""
    health = _summarize_run_health(
        ["300223", "002747"],
        [
            ("300223", _Result(0, ["transient"])),
            ("002747", _Result(0, ["transient"])),
        ],
        [{"stock_code": "300223"}],
    )

    assert health["live_success_stock_codes"] == []
    assert health["live_failed_stock_codes"] == ["002747", "300223"]
    assert health["readback_stock_codes"] == ["300223"]
    assert health["stale_readback_stock_codes"] == ["300223"]
    assert health["missing_readback_stock_codes"] == ["002747"]
    assert health["all_requested_stocks_collected_live"] is False

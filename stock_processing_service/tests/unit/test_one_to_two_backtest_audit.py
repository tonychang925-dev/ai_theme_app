from __future__ import annotations

import pytest

import scripts.check_one_to_two_backtest_audit as audit_mod
from scripts.check_one_to_two_backtest_audit import build_backtest_audit_report


def _base_run_row() -> dict[str, object]:
    return {
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
    }


def _base_snapshot_row(**overrides: object) -> dict[str, object]:
    row = {
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
        "stock_id": "600367.SH",
        "subject_key": "mainline_ai",
        "source_trace": {"source_table": "w2s_backtest_feature_snapshot"},
    }
    row.update(overrides)
    return row


def _base_signal_row(**overrides: object) -> dict[str, object]:
    row = {
        "signal_id": "sig-001",
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
        "trade_date": "2026-06-04",
        "signal_session": "post_market",
        "available_at": "2026-06-04T15:30:00",
        "tradable_at": "2026-06-05T09:30:00",
        "stock_id": "600367.SH",
        "source_table": "w2s_backtest_feature_snapshot",
        "direction": "long_watch",
        "tradable": False,
    }
    row.update(overrides)
    return row


def _base_validation_row(**overrides: object) -> dict[str, object]:
    row = {
        "signal_id": "sig-001",
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
        "trade_date": "2026-06-04",
        "stock_id": "600367.SH",
        "outcome_label": "A_SEALED_SECOND_BOARD_REAL",
        "outcome_source": "real_intraday",
    }
    row.update(overrides)
    return row


def _base_summary_row(**overrides: object) -> dict[str, object]:
    row = {
        "run_id": "run-001",
        "experiment_id": "all",
        "sample_count": 1,
    }
    row.update(overrides)
    return row


def test_one_to_two_backtest_audit_passes_on_unified_tables() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[_base_signal_row()],
        validation_rows=[_base_validation_row()],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is True
    assert report["contract"]["run_present"] is True
    assert report["contract"]["no_buy_signal"] is True
    assert report["contract"]["signal_session_post_market"] is True
    assert report["contract"]["direction_long_watch"] is True
    assert report["contract"]["tradable_false_only"] is True
    assert report["contract"]["signal_validation_mapped"] is True
    assert report["contract"]["validation_outcome_present"] is True
    assert report["snapshot"]["total_rows"] == 1
    assert report["signal"]["source_table_counts"]["w2s_backtest_feature_snapshot"] == 1


def test_one_to_two_backtest_audit_rejects_empty_snapshot_strategy_id() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row(strategy_id="")],
        signal_rows=[_base_signal_row()],
        validation_rows=[_base_validation_row()],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is False
    assert "snapshot_strategy_ids" in "".join(report["errors"])


def test_one_to_two_backtest_audit_rejects_wrong_signal_session() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[_base_signal_row(signal_session="intraday")],
        validation_rows=[_base_validation_row()],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is False
    assert "signal_session_mismatch" in report["errors"]


def test_one_to_two_backtest_audit_rejects_tradable_true() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[_base_signal_row(tradable=True)],
        validation_rows=[_base_validation_row()],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is False
    assert "tradable_true_forbidden" in report["errors"]


def test_one_to_two_backtest_audit_rejects_invalid_post_market_timestamps() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[
            _base_signal_row(
                available_at="2026-06-04T15:00:00",
                tradable_at="2026-06-05T10:00:00",
            )
        ],
        validation_rows=[_base_validation_row()],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is False
    assert "available_at_invalid" in report["errors"]
    assert "tradable_at_invalid" in report["errors"]


def test_one_to_two_backtest_audit_rejects_missing_outcome_source() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[_base_signal_row()],
        validation_rows=[_base_validation_row(outcome_source="")],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is False
    assert "outcome_source_missing" in report["errors"]


def test_one_to_two_backtest_audit_rejects_orphan_validation() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[_base_signal_row()],
        validation_rows=[_base_validation_row(signal_id="sig-002")],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is False
    assert "orphan_validation_rows" in "".join(report["errors"])


def test_one_to_two_backtest_audit_rejects_missing_validation_for_signal() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[_base_signal_row(signal_id="sig-002")],
        validation_rows=[_base_validation_row()],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is False
    assert "validation_missing_for_signal" in "".join(report["errors"])


@pytest.mark.asyncio
async def test_one_to_two_backtest_audit_rejects_missing_strategy_id_column(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_table_has_column(conn, table_name: str, column_name: str) -> bool:
        if table_name == "w2s_backtest_feature_snapshot" and column_name == "strategy_id":
            return False
        return True

    monkeypatch.setattr(audit_mod, "_table_has_column", _fake_table_has_column)

    class _Conn:
        async def fetch(self, *args, **kwargs):  # pragma: no cover - not reached
            return []

        async def close(self):  # pragma: no cover - not reached
            return None

    with pytest.raises(RuntimeError, match="BACKTEST_SNAPSHOT_STRATEGY_ID_MISSING"):
        await audit_mod._require_backtest_schema_contract(_Conn())

from __future__ import annotations

from datetime import date

import pytest

import scripts.check_one_to_two_backtest_audit as audit_mod
from scripts.check_one_to_two_backtest_audit import build_backtest_audit_report
from stock_processing_service.domain.services.one_to_two_rule_config import DEFAULT_RULE_VERSION


def _base_run_row() -> dict[str, object]:
    return {
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": DEFAULT_RULE_VERSION,
    }


def _base_snapshot_row(**overrides: object) -> dict[str, object]:
    row = {
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": DEFAULT_RULE_VERSION,
        "stock_id": "600367.SH",
        "subject_key": "mainline_ai",
        "source_trace": {"source_table": "w2s_backtest_feature_snapshot"},
    }
    row.update(overrides)
    return row


def _mixed_version_snapshot_row(**overrides: object) -> dict[str, object]:
    row = _base_snapshot_row(strategy_version="one_to_two_v1.1_post_market_plan")
    row.update(overrides)
    return row


def _base_signal_row(**overrides: object) -> dict[str, object]:
    row = {
        "signal_id": "sig-001",
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": DEFAULT_RULE_VERSION,
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


def _mixed_version_signal_row(**overrides: object) -> dict[str, object]:
    row = _base_signal_row(strategy_version="one_to_two_v1.1_post_market_plan")
    row.update(overrides)
    return row


def _base_validation_row(**overrides: object) -> dict[str, object]:
    row = {
        "signal_id": "sig-001",
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": DEFAULT_RULE_VERSION,
        "trade_date": "2026-06-04",
        "stock_id": "600367.SH",
        "outcome_label": "A_SEALED_SECOND_BOARD_REAL",
        "outcome_source": "real_intraday",
    }
    row.update(overrides)
    return row


def _mixed_version_validation_row(**overrides: object) -> dict[str, object]:
    row = _base_validation_row(strategy_version="one_to_two_v1.1_post_market_plan")
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
        strategy_version=DEFAULT_RULE_VERSION,
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
        strategy_version=DEFAULT_RULE_VERSION,
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
        strategy_version=DEFAULT_RULE_VERSION,
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
        strategy_version=DEFAULT_RULE_VERSION,
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
        strategy_version=DEFAULT_RULE_VERSION,
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
        strategy_version=DEFAULT_RULE_VERSION,
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
        strategy_version=DEFAULT_RULE_VERSION,
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
        strategy_version=DEFAULT_RULE_VERSION,
    )

    assert report["ok"] is False
    assert "validation_missing_for_signal" in "".join(report["errors"])


def test_one_to_two_backtest_audit_rejects_mixed_snapshot_strategy_version() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row(), _mixed_version_snapshot_row(snapshot_id="snap-002")],
        signal_rows=[_base_signal_row()],
        validation_rows=[_base_validation_row()],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version=DEFAULT_RULE_VERSION,
    )

    assert report["ok"] is False
    assert "snapshot_strategy_versions" in "".join(report["errors"])


def test_one_to_two_backtest_audit_rejects_mixed_signal_strategy_version() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[_base_signal_row(), _mixed_version_signal_row(signal_id="sig-002")],
        validation_rows=[_base_validation_row(), _mixed_version_validation_row(signal_id="sig-002")],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version=DEFAULT_RULE_VERSION,
    )

    assert report["ok"] is False
    assert "signal_strategy_versions" in "".join(report["errors"])


def test_one_to_two_backtest_audit_rejects_mixed_validation_strategy_version() -> None:
    report = build_backtest_audit_report(
        run_row=_base_run_row(),
        snapshot_rows=[_base_snapshot_row()],
        signal_rows=[_base_signal_row()],
        validation_rows=[_base_validation_row(), _mixed_version_validation_row(signal_id="sig-002")],
        summary_rows=[_base_summary_row()],
        strategy_id="one_to_two",
        strategy_version=DEFAULT_RULE_VERSION,
    )

    assert report["ok"] is False
    assert "validation_strategy_versions" in "".join(report["errors"])


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


@pytest.mark.asyncio
async def test_run_audit_queries_by_strategy_version(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_version = DEFAULT_RULE_VERSION

    class _Conn:
        def __init__(self) -> None:
            self.calls: list[tuple[str, list[object]]] = []

        async def fetch(self, sql, *params):
            self.calls.append((str(sql), list(params)))
            normalized = " ".join(str(sql).lower().split())
            if "from w2s_backtest_run" in normalized:
                return [
                    {
                        "run_id": "run-001",
                        "strategy_id": "one_to_two",
                        "strategy_version": expected_version,
                        "start_date": date(2026, 6, 4),
                        "end_date": date(2026, 6, 5),
                    }
                ]
            if "from w2s_backtest_feature_snapshot" in normalized:
                return [_base_snapshot_row()]
            if "from strategy_signal_daily" in normalized:
                return [_base_signal_row()]
            if "from strategy_signal_validation" in normalized:
                return [_base_validation_row()]
            if "from stock_daily_snapshot" in normalized and "trade_date >=" in normalized:
                return [{"trade_date": date(2026, 6, 4)}, {"trade_date": date(2026, 6, 5)}]
            if "from stock_daily_snapshot" in normalized and "trade_date >" in normalized and "limit 1" in normalized:
                return [{"trade_date": date(2026, 6, 5)}]
            if "from stock_daily_snapshot" in normalized and "trade_date =" in normalized:
                return [
                    {
                        "trade_date": date(2026, 6, 5),
                        "stock_id": "600367.SH",
                        "stock_name": "红星发展",
                        "open_price": 10,
                        "high_price": 10,
                        "low_price": 10,
                        "close_price": 10,
                        "pre_close": 9.09,
                        "pct_chg": 10.0,
                        "volume": 1,
                        "amount": 1,
                    }
                ]
            return []

        async def close(self):
            return None

    conn = _Conn()

    async def _fake_connect(*args, **kwargs):
        return conn

    monkeypatch.setattr(audit_mod.asyncpg, "connect", _fake_connect)
    async def _fake_resolve_table_name(conn, table_name: str) -> str:
        return table_name

    async def _fake_require_backtest_schema_contract(conn) -> None:
        return None

    monkeypatch.setattr(audit_mod, "_resolve_table_name", _fake_resolve_table_name)
    monkeypatch.setattr(audit_mod, "_require_backtest_schema_contract", _fake_require_backtest_schema_contract)

    report = await audit_mod.run_audit("run-001", "postgres://test", strategy_id="one_to_two")

    assert report["ok"] is True
    assert any(
        "strategy_version = $3::text" in sql
        for sql, _params in conn.calls
        if "from w2s_backtest_feature_snapshot" in sql.lower()
    )
    assert any(
        "strategy_version = $3::text" in sql
        for sql, _params in conn.calls
        if "from strategy_signal_daily" in sql.lower()
    )
    assert any(
        "strategy_version = $3::text" in sql
        for sql, _params in conn.calls
        if "from strategy_signal_validation" in sql.lower()
    )

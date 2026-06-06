from __future__ import annotations

from scripts.check_one_to_two_backtest_audit import build_backtest_audit_report


def test_one_to_two_backtest_audit_passes_on_unified_tables() -> None:
    report = build_backtest_audit_report(
        run_row={
            "run_id": "run-001",
            "strategy_id": "one_to_two",
            "strategy_version": "one_to_two_v1.0_post_market_plan",
        },
        snapshot_rows=[
            {
                "run_id": "run-001",
                "strategy_id": "one_to_two",
                "strategy_version": "one_to_two_v1.0_post_market_plan",
                "stock_id": "600367.SH",
                "source_trace": {"source_table": "w2s_backtest_feature_snapshot"},
            }
        ],
        signal_rows=[
            {
                "run_id": "run-001",
                "strategy_id": "one_to_two",
                "strategy_version": "one_to_two_v1.0_post_market_plan",
                "stock_id": "600367.SH",
                "source_table": "w2s_backtest_feature_snapshot",
                "direction": "long_watch",
            }
        ],
        validation_rows=[
            {
                "run_id": "run-001",
                "strategy_id": "one_to_two",
                "strategy_version": "one_to_two_v1.0_post_market_plan",
                "stock_id": "600367.SH",
                "outcome_label": "A_SEALED_SECOND_BOARD_REAL",
            }
        ],
        summary_rows=[
            {
                "run_id": "run-001",
                "experiment_id": "all",
                "sample_count": 1,
            }
        ],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is True
    assert report["contract"]["run_present"] is True
    assert report["contract"]["no_buy_signal"] is True
    assert report["snapshot"]["total_rows"] == 1
    assert report["signal"]["source_table_counts"]["w2s_backtest_feature_snapshot"] == 1


def test_one_to_two_backtest_audit_rejects_buy_tokens() -> None:
    report = build_backtest_audit_report(
        run_row={
            "run_id": "run-001",
            "strategy_id": "one_to_two",
            "strategy_version": "one_to_two_v1.0_post_market_plan",
        },
        snapshot_rows=[],
        signal_rows=[
            {
                "run_id": "run-001",
                "strategy_id": "one_to_two",
                "strategy_version": "one_to_two_v1.0_post_market_plan",
                "stock_id": "600367.SH",
                "direction": "buy",
                "source_table": "w2s_backtest_feature_snapshot",
            }
        ],
        validation_rows=[
            {
                "run_id": "run-001",
                "strategy_id": "one_to_two",
                "strategy_version": "one_to_two_v1.0_post_market_plan",
                "stock_id": "600367.SH",
                "outcome_label": "A_SEALED_SECOND_BOARD_REAL",
            }
        ],
        summary_rows=[
            {
                "run_id": "run-001",
                "experiment_id": "all",
                "sample_count": 1,
            }
        ],
        strategy_id="one_to_two",
        strategy_version="one_to_two_v1.0_post_market_plan",
    )

    assert report["ok"] is False
    assert "missing_snapshot_rows" in report["errors"]
    assert "buy_tokens_present" in report["errors"]

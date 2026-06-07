from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.backtest.one_to_two_backtest_validation_summary_service import (
    OneToTwoBacktestValidationSummaryService,
)


class _Client:
    def __init__(self, rows: dict[str, list[dict[str, object]]]) -> None:
        self.rows = rows
        self.calls: list[tuple[str, list[object]]] = []

    async def execute_query(self, sql, params):
        self.calls.append((sql, list(params)))
        normalized = " ".join(str(sql).lower().split())
        if "from w2s_backtest_run" in normalized:
            return self.rows.get("run", [])
        if "from w2s_backtest_feature_snapshot" in normalized:
            return self.rows.get("snapshots", [])
        if "from strategy_signal_daily" in normalized:
            return self.rows.get("signals", [])
        if "from strategy_signal_validation" in normalized:
            return self.rows.get("validations", [])
        if "select distinct trade_date from stock_daily_snapshot" in normalized and "trade_date >=" in normalized and "trade_date <=" in normalized:
            return self.rows.get("calendar", [])
        if "select distinct trade_date from stock_daily_snapshot" in normalized and "trade_date >" in normalized and "limit 1" in normalized:
            return self.rows.get("next_trade_date", [])
        if "from stock_daily_snapshot" in normalized and "trade_date =" in normalized:
            key = f"bar:{params[0]}:{params[1]}"
            return self.rows.get(key, [])
        return []


class _Gateway:
    def __init__(self, rows: dict[str, list[dict[str, object]]]) -> None:
        self._client = _Client(rows)


def _snapshot(
    *,
    snapshot_id: str,
    trade_date: str,
    stock_id: str,
    decision: str,
    subject_key: str = "mainline_ai",
    is_20cm: bool = False,
    veto_reason: str = "no_mainline",
    authenticity_level: str | None = None,
    has_golden_spider: bool | None = None,
) -> dict[str, object]:
    raw_feature_json: dict[str, object] = {"decision": decision, "veto_reasons": [veto_reason]}
    derived_feature_json: dict[str, object] = {"decision": decision, "veto_reasons": [veto_reason]}
    if authenticity_level is not None:
        raw_feature_json["subject_authenticity"] = {"level": authenticity_level, "score": 81.0}
        derived_feature_json["subject_authenticity"] = {"level": authenticity_level, "score": 81.0}
    if has_golden_spider is not None:
        raw_feature_json["kline_pattern_quality"] = {"has_golden_spider": has_golden_spider, "score": 68.0 if has_golden_spider else 32.0}
        derived_feature_json["kline_pattern_quality"] = {"has_golden_spider": has_golden_spider, "score": 68.0 if has_golden_spider else 32.0}
    return {
        "snapshot_id": snapshot_id,
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
        "candidate_trade_date": trade_date,
        "confirm_trade_date": "2026-06-05",
        "stock_id": stock_id,
        "subject_key": subject_key,
        "is_20cm": is_20cm,
        "derived_feature_json": derived_feature_json,
        "raw_feature_json": raw_feature_json,
        "source_trace": {"source_table": "w2s_backtest_feature_snapshot"},
    }


def _signal(snapshot_id: str, stock_id: str, trade_date: str) -> dict[str, object]:
    return {
        "signal_id": f"sig-{snapshot_id}",
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
        "trade_date": trade_date,
        "signal_session": "post_market",
        "available_at": "2026-06-04T15:30:00",
        "tradable_at": "2026-06-05T09:30:00",
        "stock_id": stock_id,
        "source_id": snapshot_id,
        "direction": "long_watch",
        "tradable": False,
        "signal_level": "focus",
        "score": 93.2,
    }


def _validation(signal_id: str, stock_id: str, trade_date: str, outcome_label: str, outcome_source: str) -> dict[str, object]:
    return {
        "signal_id": signal_id,
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
        "trade_date": trade_date,
        "stock_id": stock_id,
        "outcome_label": outcome_label,
        "outcome_source": outcome_source,
    }


@pytest.mark.asyncio
async def test_one_to_two_backtest_validation_summary_reports_core_metrics() -> None:
    rows = {
        "run": [
            {
                "run_id": "run-001",
                "strategy_id": "one_to_two",
                "strategy_version": "one_to_two_v1.0_post_market_plan",
                "start_date": date(2026, 6, 4),
                "end_date": date(2026, 6, 5),
            }
        ],
        "snapshots": [
            _snapshot(snapshot_id="snap-focus", trade_date="2026-06-04", stock_id="600367.SH", decision="focus"),
            _snapshot(snapshot_id="snap-observe", trade_date="2026-06-04", stock_id="600368.SH", decision="observe_only", veto_reason="weak_theme", authenticity_level="related", has_golden_spider=False),
            _snapshot(snapshot_id="snap-pending", trade_date="2026-06-05", stock_id="600369.SH", decision="pending_review_only", veto_reason="missing_confirmation"),
            _snapshot(snapshot_id="snap-reject", trade_date="2026-06-04", stock_id="600370.SH", decision="reject", veto_reason="mainline_missing"),
        ],
        "signals": [
            _signal("snap-focus", "600367.SH", "2026-06-04"),
            _signal("snap-observe", "600368.SH", "2026-06-04"),
            _signal("snap-pending", "600369.SH", "2026-06-05"),
        ],
        "validations": [
            _validation("sig-snap-focus", "600367.SH", "2026-06-04", "A_SEALED_SECOND_BOARD_PROXY", "daily_close_proxy"),
            _validation("sig-snap-observe", "600368.SH", "2026-06-04", "B_TOUCHED_BUT_BROKEN", "daily_high_proxy"),
            _validation("sig-snap-pending", "600369.SH", "2026-06-05", "C_FAILED_NO_TOUCH", "daily_close_proxy"),
        ],
        "calendar": [
            {"trade_date": date(2026, 6, 4)},
            {"trade_date": date(2026, 6, 5)},
        ],
        "bar:2026-06-05:600370.SH": [
            {
                "trade_date": date(2026, 6, 5),
                "stock_id": "600370.SH",
                "open_price": 10,
                "high_price": 11,
                "low_price": 9.8,
                "close_price": 11,
                "pre_close": 10,
                "pct_chg": 10.0,
            }
        ],
        "next_trade_date": [
            {"trade_date": date(2026, 6, 5)}
        ],
    }
    service = OneToTwoBacktestValidationSummaryService(_Gateway(rows))

    report = await service.build("run-001")

    assert report["total_days"] == 2
    assert report["empty_days"] == 0
    assert report["non_empty_days"] == 2
    assert report["focus_count"] == 1
    assert report["observe_count"] == 1
    assert report["pending_count"] == 1
    assert report["reject_count"] == 1
    assert report["focus_second_board_rate"] == 1.0
    assert report["observe_second_board_rate"] == 0.0
    assert report["pending_second_board_rate"] == 0.0
    assert report["reject_false_negative_rate"] == 1.0
    assert report["outcome_label_counts"]["A_SEALED_SECOND_BOARD_PROXY"] == 2
    assert report["outcome_label_counts"]["B_TOUCHED_BUT_BROKEN"] == 1
    assert report["outcome_label_counts"]["C_FAILED_NO_TOUCH"] == 1
    assert report["outcome_source_counts"]["daily_close_proxy"] == 3
    assert report["outcome_source_counts"]["daily_high_proxy"] == 1
    assert report["authenticity_level_counts"]["related"] == 1
    assert report["authenticity_level_counts"]["unknown"] == 3
    assert report["golden_spider_counts"]["false"] == 4
    assert report["reject_reason_false_negative_distribution"]["mainline_missing"] == 1
    assert report["decision_breakdown"]["focus"]["success_rate"] == 1.0
    assert report["decision_breakdown"]["observe_only"]["success_rate"] == 0.0
    assert report["decision_breakdown"]["pending_review_only"]["success_rate"] == 0.0
    assert report["decision_breakdown"]["observe_only"]["authenticity_level_counts"]["related"] == 1
    assert report["decision_breakdown"]["observe_only"]["golden_spider_counts"]["false"] == 1
    assert report["summary_rows"][0]["experiment_id"] == "one_to_two_overall"

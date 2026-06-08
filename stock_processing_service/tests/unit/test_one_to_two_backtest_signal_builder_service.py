from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from stock_processing_service.application.services.backtest.one_to_two_backtest_signal_builder_service import (
    OneToTwoBacktestSignalBuilderService,
)
from stock_processing_service.domain.services.one_to_two_rule_config import DEFAULT_RULE_VERSION


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object]]] = []

    async def execute_query(self, sql, params):
        self.calls.append((sql, list(params)))
        return []


class _Gateway:
    def __init__(self, snapshots: list[dict[str, object]]) -> None:
        self._client = _Client()
        self._snapshots = snapshots

    async def get_w2s_backtest_feature_snapshots_by_run(self, run_id: str) -> list[dict[str, object]]:
        return [dict(row) for row in self._snapshots if row.get("run_id") == run_id]


def _snapshot(**overrides: object) -> dict[str, object]:
    row = {
        "snapshot_id": "snap-001",
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": DEFAULT_RULE_VERSION,
        "candidate_trade_date": date(2026, 6, 4),
        "confirm_trade_date": date(2026, 6, 5),
        "stock_id": "600367.SH",
        "stock_name": "红星发展",
        "subject_key": "mainline_ai",
        "theme_name": "主线AI",
        "pool_entry_type": "focus",
        "candidate_score": "93.2",
        "candidate_type": "one_to_two",
        "weak_type": "",
        "support_type": "",
        "support_strength": None,
        "is_leader": True,
        "rank_order": 1,
        "recent_limit_up_count": None,
        "prior7_limitup_days": None,
        "prior7_strong_days": None,
        "leader_role_proxy": "focus",
        "leader_score_proxy": "93.2",
        "two_board_quality_score": "91.5",
        "board_type": "start",
        "is_20cm": False,
        "mainline_strength_score": "88.0",
        "fade_watch": False,
        "fade_confirmed": False,
        "cycle_state": "start",
        "auction_feature_mode": "one_to_two_backtest",
        "auction_open_pct": None,
        "auction_amount": None,
        "auction_score": "93.2",
        "confirm_level": "focus",
        "confirmation_score": "93.2",
        "auction_feature_quality": "complete",
        "missing_features": [],
        "bull_stock_score": None,
        "raw_feature_json": {},
        "derived_feature_json": {"decision": "focus", "final_score": "93.2"},
        "source_trace": {"source_chain": "stock_processing_service.one_to_two_setup_plan"},
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_one_to_two_backtest_signal_builder_emits_watch_only_signals() -> None:
    gw = _Gateway(
        [
            _snapshot(snapshot_id="snap-001", pool_entry_type="focus", derived_feature_json={"decision": "focus", "final_score": "93.2"}),
            _snapshot(
                snapshot_id="snap-002",
                stock_id="600368.SH",
                subject_key="mainline_ai",
                pool_entry_type="observe_only",
                derived_feature_json={"decision": "observe_only", "final_score": "80.1"},
            ),
            _snapshot(
                snapshot_id="snap-003",
                stock_id="600369.SH",
                subject_key="mainline_ai",
                pool_entry_type="pending_review_only",
                derived_feature_json={"decision": "pending_review_only", "final_score": "66.0"},
            ),
            _snapshot(
                snapshot_id="snap-004",
                stock_id="600370.SH",
                subject_key="mainline_ai",
                pool_entry_type="reject",
                derived_feature_json={"decision": "reject", "final_score": "10.0"},
            ),
        ]
    )
    service = OneToTwoBacktestSignalBuilderService(gw)

    report = await service.build("run-001")

    assert report["signal_count"] == 3
    assert report["written"] == 3
    assert len(gw._client.calls) == 4
    delete_sql, delete_params = gw._client.calls[0]
    assert "DELETE FROM strategy_signal_daily" in delete_sql
    assert "strategy_id" in delete_sql
    assert delete_params == ["run-001", "one_to_two"]

    insert_sql, insert_params = gw._client.calls[1]
    assert "INSERT INTO strategy_signal_daily" in insert_sql
    assert insert_params[2] == "one_to_two"
    assert insert_params[5] == "post_market"
    assert insert_params[12] == "long_watch"
    assert insert_params[13] is False
    assert insert_params[14] == "focus"
    assert insert_params[18] == "one_to_two_backtest"
    assert insert_params[25] == "w2s_backtest_feature_snapshot"
    assert insert_params[27] == DEFAULT_RULE_VERSION
    available_at = insert_params[6]
    tradable_at = insert_params[7]
    assert isinstance(available_at, datetime)
    assert isinstance(tradable_at, datetime)
    assert available_at == datetime(2026, 6, 4, 15, 30)
    assert tradable_at == datetime(2026, 6, 5, 9, 30)

    signal_levels = [call[1][14] for call in gw._client.calls[1:]]
    assert signal_levels == ["focus", "observe_only", "pending_review_only"]
    first_signal_id = gw._client.calls[1][1][0]

    await service.build("run-001")
    second_signal_id = gw._client.calls[5][1][0]
    assert first_signal_id == second_signal_id


@pytest.mark.asyncio
async def test_one_to_two_backtest_signal_builder_delete_failure_raises() -> None:
    class _BrokenClient(_Client):
        async def execute_query(self, sql, params):
            if str(sql).startswith("DELETE"):
                raise RuntimeError("delete boom")
            return await super().execute_query(sql, params)

    gw = _Gateway([_snapshot()])
    gw._client = _BrokenClient()
    service = OneToTwoBacktestSignalBuilderService(gw)

    with pytest.raises(RuntimeError, match="failed to delete existing one_to_two signals"):
        await service.build("run-001")


@pytest.mark.asyncio
async def test_one_to_two_backtest_signal_builder_rejects_missing_snapshot_strategy_id() -> None:
    gw = _Gateway(
        [
            _snapshot(strategy_id=""),
        ]
    )
    service = OneToTwoBacktestSignalBuilderService(gw)

    with pytest.raises(RuntimeError, match="snapshot strategy_id missing"):
        await service.build("run-001")


@pytest.mark.asyncio
async def test_one_to_two_backtest_signal_builder_rejects_missing_confirm_trade_date() -> None:
    gw = _Gateway(
        [
            _snapshot(confirm_trade_date=None),
        ]
    )
    service = OneToTwoBacktestSignalBuilderService(gw)

    with pytest.raises(RuntimeError, match="missing confirm_trade_date"):
        await service.build("run-001")

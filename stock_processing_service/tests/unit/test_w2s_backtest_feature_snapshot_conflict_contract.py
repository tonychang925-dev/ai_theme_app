from __future__ import annotations

import asyncio
from datetime import date

from database_service.scripts.apply_w2s_backtest_tables import DDL_STATEMENTS
from stock_processing_service.application.services.backtest.w2s_feature_snapshot_service import (
    W2SFeatureSnapshotService,
)


def test_w2s_backtest_feature_snapshot_ddl_uses_plain_unique_index() -> None:
    ddl = "\n".join(DDL_STATEMENTS)

    assert "confirm_trade_date DATE NOT NULL DEFAULT DATE '1900-01-01'" in ddl
    assert "subject_key VARCHAR(64) NOT NULL DEFAULT ''" in ddl
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uniq_backtest_snapshot_strategy_stock_subject" in ddl
    assert "COALESCE(confirm_trade_date" not in ddl
    assert "COALESCE(subject_key" not in ddl
    assert "UNIQUE(run_id, strategy_id, strategy_version, candidate_trade_date, confirm_trade_date, stock_id, subject_key)" not in ddl


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object]]] = []

    async def execute_query(self, sql, params):
        self.calls.append((sql, list(params)))
        return []


class _Gateway:
    def __init__(self) -> None:
        self._client = _Client()


def _snapshot_row(**overrides):
    row = {
        "snapshot_id": "snap-001",
        "run_id": "run-001",
        "strategy_id": "one_to_two",
        "strategy_version": "one_to_two_v1.0_post_market_plan",
        "candidate_trade_date": date(2026, 6, 4),
        "confirm_trade_date": None,
        "stock_id": "600367.SH",
        "stock_name": "S",
        "subject_key": None,
        "theme_name": "T",
        "candidate_id": None,
        "pool_entry_type": "",
        "candidate_score": None,
        "candidate_type": "",
        "weak_type": "",
        "support_type": "",
        "support_strength": None,
        "is_leader": False,
        "rank_order": None,
        "recent_limit_up_count": None,
        "prior7_limitup_days": None,
        "prior7_strong_days": None,
        "leader_role_proxy": "",
        "leader_score_proxy": None,
        "two_board_quality_score": None,
        "board_type": "",
        "is_20cm": False,
        "mainline_strength_score": None,
        "fade_watch": False,
        "fade_confirmed": False,
        "cycle_state": "",
        "auction_feature_mode": "",
        "auction_open_pct": None,
        "auction_amount": None,
        "auction_score": None,
        "confirm_level": "",
        "confirmation_score": None,
        "auction_feature_quality": "",
        "missing_features": [],
        "bull_stock_score": None,
        "raw_feature_json": {},
        "derived_feature_json": {},
        "source_trace": {},
        "confirm_source": "missing",
        "confirm_level_detail": "",
        "weak_type_quality": "",
    }
    row.update(overrides)
    return row


def test_w2s_backtest_feature_snapshot_raw_sql_normalizes_null_keys() -> None:
    gw = _Gateway()
    service = W2SFeatureSnapshotService(read_ports=object(), gateway=gw)

    written = asyncio.run(service._write_via_raw_sql([_snapshot_row()]))

    assert written == 1
    sql, params = gw._client.calls[0]
    assert "ON CONFLICT (run_id, strategy_id, strategy_version, candidate_trade_date, confirm_trade_date, stock_id, subject_key)" in sql
    assert params[5] == date(1900, 1, 1)
    assert params[8] == ""


def test_w2s_backtest_feature_snapshot_raw_sql_normalizes_null_subject_key() -> None:
    gw = _Gateway()
    service = W2SFeatureSnapshotService(read_ports=object(), gateway=gw)

    written = asyncio.run(service._write_via_raw_sql([_snapshot_row(subject_key=None)]))

    assert written == 1
    _, params = gw._client.calls[0]
    assert params[8] == ""


def test_w2s_backtest_feature_snapshot_raw_sql_uses_conflict_update_clause() -> None:
    gw = _Gateway()
    service = W2SFeatureSnapshotService(read_ports=object(), gateway=gw)

    written = asyncio.run(service._write_via_raw_sql([_snapshot_row()]))

    assert written == 1
    sql, _ = gw._client.calls[0]
    assert "ON CONFLICT (run_id, strategy_id, strategy_version, candidate_trade_date, confirm_trade_date, stock_id, subject_key)" in sql
    assert "DO UPDATE SET" in sql
    assert "strategy_id = EXCLUDED.strategy_id" in sql

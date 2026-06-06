from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from stock_processing_service.application.services.backtest.one_to_two_backtest_feature_snapshot_service import (
    OneToTwoBacktestFeatureSnapshotService,
)
from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoSetupPlanDTO
from stock_processing_service.contracts.dto.trade_calendar_dto import TradeCalendarDTO


class _Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object]]] = []

    async def execute_query(self, sql, params):
        self.calls.append((sql, list(params)))
        return []


class _FailingClient(_Client):
    def __init__(self, *, fail_on_delete: bool = False) -> None:
        super().__init__()
        self.fail_on_delete = fail_on_delete

    async def execute_query(self, sql, params):
        if self.fail_on_delete and str(sql).lstrip().upper().startswith("DELETE"):
            raise RuntimeError("delete boom")
        raise RuntimeError("write boom")


class _Gateway:
    def __init__(self, client: _Client | None = None) -> None:
        self._client = client or _Client()


class _ReadPort:
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO:
        return TradeCalendarDTO(
            trade_date=trade_date,
            calendar_is_open=True,
            prev_trade_date=trade_date - timedelta(days=1),
            next_trade_date=trade_date + timedelta(days=1),
        )

    async def get_post_market_report_context(self, trade_date: date) -> dict[str, object]:
        return {
            "market_regime": {"trade_mode": "normal", "allow_trade": True},
            "trading_principle": {"position_limit": 0.1},
            "pressure_by_stock": {},
            "ma_pattern_by_stock": {},
        }


class _BrokenReadPort(_ReadPort):
    async def get_post_market_report_context(self, trade_date: date) -> dict[str, object]:
        raise RuntimeError("report context boom")


class _Engine:
    async def build(self, trade_date: date, read_port, source_doc=None):
        return OneToTwoSetupPlanDTO(
            summary={"focus_count": 1, "observe_only_count": 0, "pending_review_only_count": 0, "reject_count": 1},
            items=[],
            diagnostics={},
            candidate_features=[
                {
                    "trade_date": trade_date.isoformat(),
                    "watch_date": (trade_date + timedelta(days=1)).isoformat(),
                    "stock_id": "600367.SH",
                    "stock_name": "红星发展",
                    "subject_key": "mainline_ai",
                    "subject_name": "主线AI",
                    "decision": "focus",
                    "veto_reasons": [],
                    "risk_flags": ["mainline"],
                    "first_board_quality_score": Decimal("91.5"),
                    "mainline_context_score": Decimal("88.0"),
                    "technical_structure_score": Decimal("89.0"),
                    "risk_control_score": Decimal("95.0"),
                    "final_score": Decimal("93.2"),
                    "watch_level": "focus",
                    "summary": "focus candidate",
                    "evidence_rules": ["rule-a"],
                    "data_quality_json": {"source": "unit"},
                    "source_trace_json": {"source_chain": "unit"},
                    "missing_features": [],
                },
                {
                    "trade_date": trade_date.isoformat(),
                    "watch_date": (trade_date + timedelta(days=1)).isoformat(),
                    "stock_id": "600999.SH",
                    "stock_name": "测试股份",
                    "subject_key": "mainline_ai",
                    "subject_name": "主线AI",
                    "decision": "reject",
                    "veto_reasons": ["not_mainline"],
                    "risk_flags": ["reject"],
                    "first_board_quality_score": Decimal("10.5"),
                    "mainline_context_score": Decimal("12.0"),
                    "technical_structure_score": Decimal("13.0"),
                    "risk_control_score": Decimal("14.0"),
                    "final_score": Decimal("11.2"),
                    "watch_level": "reject",
                    "summary": "reject candidate",
                    "evidence_rules": ["rule-b"],
                    "data_quality_json": {"source": "unit"},
                    "source_trace_json": {"source_chain": "unit"},
                    "missing_features": ["mainline_context"],
                },
            ],
        )


class _DQPass:
    async def check(self, start_date: date, end_date: date) -> dict[str, object]:
        return {"blocked": False}


@pytest.mark.asyncio
async def test_one_to_two_backtest_snapshot_freezes_reject_candidates() -> None:
    gw = _Gateway()
    service = OneToTwoBacktestFeatureSnapshotService(
        _ReadPort(),
        gw,
        engine=_Engine(),
        data_quality_service=_DQPass(),
    )

    report = await service.build(
        run_id="run-001",
        start_date=date(2026, 6, 4),
        end_date=date(2026, 6, 4),
        force_rebuild=False,
    )

    assert report["written"] == 2
    assert report["snapshot_count"] == 2
    assert report["focus_count"] == 1
    assert report["reject_count"] == 1
    sql, params = gw._client.calls[0]
    assert "INSERT INTO w2s_backtest_feature_snapshot" in sql
    assert params[2] == "one_to_two"
    assert params[3] == "one_to_two_v1.0_post_market_plan"
    source_trace = json.loads(params[-1])
    derived = json.loads(params[-2])
    assert source_trace["run_type"] == "backtest"
    assert derived["run_type"] == "backtest"


@pytest.mark.asyncio
async def test_one_to_two_backtest_snapshot_write_failure_raises() -> None:
    gw = _Gateway(_FailingClient())
    service = OneToTwoBacktestFeatureSnapshotService(
        _ReadPort(),
        gw,
        engine=_Engine(),
        data_quality_service=_DQPass(),
    )

    with pytest.raises(RuntimeError, match="failed to write one_to_two backtest feature snapshot"):
        await service.build(
            run_id="run-001",
            start_date=date(2026, 6, 4),
            end_date=date(2026, 6, 4),
            force_rebuild=False,
        )


@pytest.mark.asyncio
async def test_one_to_two_backtest_snapshot_force_rebuild_delete_failure_raises() -> None:
    gw = _Gateway(_FailingClient(fail_on_delete=True))
    service = OneToTwoBacktestFeatureSnapshotService(
        _ReadPort(),
        gw,
        engine=_Engine(),
        data_quality_service=_DQPass(),
    )

    with pytest.raises(RuntimeError, match="failed to delete existing one_to_two snapshots"):
        await service.build(
            run_id="run-001",
            start_date=date(2026, 6, 4),
            end_date=date(2026, 6, 4),
            force_rebuild=True,
        )


@pytest.mark.asyncio
async def test_one_to_two_backtest_snapshot_report_context_failure_raises() -> None:
    gw = _Gateway()
    service = OneToTwoBacktestFeatureSnapshotService(
        _BrokenReadPort(),
        gw,
        engine=_Engine(),
        data_quality_service=_DQPass(),
    )

    with pytest.raises(RuntimeError, match="failed to load post_market_report_context for one_to_two snapshot"):
        await service.build(
            run_id="run-001",
            start_date=date(2026, 6, 4),
            end_date=date(2026, 6, 4),
            force_rebuild=False,
        )

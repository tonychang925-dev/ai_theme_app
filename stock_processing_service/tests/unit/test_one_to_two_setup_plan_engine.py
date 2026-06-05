from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from stock_processing_service.application.services.one_to_two_setup_plan_engine import (
    OneToTwoSetupPlanEngine,
)
from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures
from stock_processing_service.contracts.dto.post_market_setup_context_dto import (
    PostMarketSetupFactContext,
    SetupFactContextBuildError,
    SourceStatus,
)
from stock_processing_service.contracts.dto.trade_calendar_dto import TradeCalendarDTO
from stock_processing_service.domain.services.one_to_two_rule_engine import OneToTwoRuleEngine


@dataclass
class _ForbiddenCall:
    name: str

    def __call__(self, *args, **kwargs):
        raise AssertionError(f"{self.name} should not be called")


class _ReadPortFake:
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO:
        return TradeCalendarDTO(
            trade_date=trade_date,
            calendar_is_open=True,
            prev_trade_date=trade_date,
            next_trade_date=trade_date,
        )

    async def get_post_market_report_context(
        self,
        trade_date: date,
        subject_keys: list[str] | None = None,
        stock_ids: list[str] | None = None,
    ) -> dict[str, object]:
        return {
            "market_regime_review": {"trade_mode": "no_trade", "allow_trade": False},
            "trading_principle": {"position_limit": 0.0},
        }

    async def get_active_confirmed_mainlines(
        self, trade_date: date | None = None, limit: int = 100
    ) -> list[dict[str, object]]:
        return []

    async def get_mainline_state_daily(
        self, trade_date: date, subject_keys: list[str]
    ) -> list[dict[str, object]]:
        return []

    async def get_subject_board_stats(self, trade_date: date) -> list[dict[str, object]]:
        return []

    async def get_stock_daily_bars_range(
        self, start_date: date, end_date: date, stock_ids: list[str] | None = None
    ) -> list[dict[str, object]]:
        return []

    async def get_subject_stock_daily_bars_range(
        self,
        start_date: date,
        end_date: date,
        stock_ids: list[str] | None = None,
        subject_keys: list[str] | None = None,
    ) -> list[dict[str, object]]:
        return []

    async def get_strong_stock_watch_view_rows(self, *args, **kwargs):
        raise AssertionError("Layer C read-model should not be called")

    async def get_w2s_candidate_inputs(self, *args, **kwargs):
        raise AssertionError("D1 read-model should not be called")

    async def get_strong_watch_seed_rows(self, *args, **kwargs):
        raise AssertionError("Layer C seed read-model should not be called")

    async def get_strong_watch_refresh_rows(self, *args, **kwargs):
        raise AssertionError("Layer C refresh read-model should not be called")


def _setup_context() -> PostMarketSetupFactContext:
    return PostMarketSetupFactContext(
        trade_date="2026-06-04",
        watch_date="2026-06-05",
        active_mainlines=[],
        strong_hotspot_subjects=[],
        active_subject_keys=set(),
        lifecycle_by_subject={},
        market_regime={"trade_mode": "no_trade", "allow_trade": False},
        trading_principle={"position_limit": 0.0},
        subject_stock_rows=[],
        stock_daily_bars=[],
        limit_up_rows=[],
        diagnostics=SourceStatus(source_status={"market_regime": "ready"}),
    )


def test_one_to_two_empty_result_is_valid() -> None:
    engine = OneToTwoSetupPlanEngine()
    result = engine.build_from_context(_setup_context())

    assert result.summary["focus_count"] == 0
    assert result.summary["observe_only_count"] == 0
    assert result.summary["pending_review_only_count"] == 0
    assert result.summary["reject_count"] == 0
    assert result.items == []
    assert result.diagnostics["empty_is_valid"] is True


@pytest.mark.asyncio
async def test_one_to_two_does_not_read_layer_c_pool() -> None:
    engine = OneToTwoSetupPlanEngine()
    fake = _ReadPortFake()

    result = await engine.build(date(2026, 6, 4), fake)

    assert result.summary["focus_count"] == 0
    assert result.items == []


def test_one_to_two_no_trade_focus_count_zero() -> None:
    engine = OneToTwoSetupPlanEngine()
    engine.candidate_service.build_fact_pool = lambda ctx: [  # type: ignore[assignment]
        OneToTwoFeatures(
            trade_date="2026-06-04",
            watch_date="2026-06-05",
            stock_id="600367.SH",
            stock_name="红星发展",
            subject_key="independent",
            subject_name="独立龙头",
            is_confirmed_mainline=True,
            is_strong_hotspot=False,
            mainline_or_hotspot_state="confirmed_mainline",
            lifecycle_state="start",
            market_trade_mode="no_trade",
            allow_trade=False,
            is_first_limit_up=True,
            is_one_word_board=False,
            is_late_seal=False,
            first_limit_time="10:18:00",
            open_board_count=1,
            turnover_rate=Decimal("0.18"),
            amount=Decimal("1000000000"),
            close_seal_amount=Decimal("50000000"),
            seal_ratio=Decimal("0.8"),
            float_mcap=Decimal("12000000000"),
            position_120=Decimal("0.3"),
            is_downtrend=False,
            near_pressure=False,
            same_subject_limit_count=3,
            same_subject_strong_count=2,
            data_quality={"missing_required": []},
            source_trace={"source": "unit"},
        )
    ]

    result = engine.build_from_context(_setup_context())

    assert result.summary["focus_count"] == 0
    assert result.items[0]["decision"] == "observe_only"
    assert "buy" not in result.items[0]["summary"].lower()
    assert "recommend_buy" not in result.items[0]["summary"].lower()


def test_one_to_two_outputs_only_plan_not_buy_signal() -> None:
    engine = OneToTwoSetupPlanEngine()
    result = engine.build_from_context(_setup_context())

    payload = result.to_dict()
    assert "buy" not in str(payload).lower()
    assert "must_buy" not in str(payload).lower()
    assert "recommend_buy" not in str(payload).lower()


def test_one_to_two_rejects_non_mainline_first_board() -> None:
    rule = OneToTwoRuleEngine().apply(
        OneToTwoFeatures(
            trade_date="2026-06-04",
            watch_date="2026-06-05",
            stock_id="600367.SH",
            stock_name="红星发展",
            subject_key="robot",
            subject_name="机器人",
            is_confirmed_mainline=False,
            is_strong_hotspot=False,
            mainline_or_hotspot_state="pending_review",
            lifecycle_state="start",
            market_trade_mode="mainline_ultra_short_only",
            allow_trade=True,
            is_first_limit_up=True,
            is_one_word_board=False,
            is_late_seal=False,
            first_limit_time="10:18:00",
            open_board_count=2,
            turnover_rate=Decimal("0.18"),
            amount=Decimal("1000000000"),
            close_seal_amount=Decimal("50000000"),
            seal_ratio=Decimal("0.8"),
            float_mcap=Decimal("12000000000"),
            position_120=Decimal("0.3"),
            is_downtrend=False,
            near_pressure=False,
            same_subject_limit_count=3,
            same_subject_strong_count=2,
            data_quality={"missing_required": []},
            source_trace={"source": "unit"},
        )
    )

    assert rule.decision == "reject"
    assert "非市场主线" in "".join(rule.veto_reasons)


def test_one_to_two_rejects_one_word_board() -> None:
    rule = OneToTwoRuleEngine().apply(
        OneToTwoFeatures(
            trade_date="2026-06-04",
            watch_date="2026-06-05",
            stock_id="600403.SH",
            stock_name="大有能源",
            subject_key="coal",
            subject_name="煤炭",
            is_confirmed_mainline=True,
            is_strong_hotspot=False,
            mainline_or_hotspot_state="confirmed_mainline",
            lifecycle_state="start",
            market_trade_mode="mainline_ultra_short_only",
            allow_trade=True,
            is_first_limit_up=True,
            is_one_word_board=True,
            is_late_seal=False,
            first_limit_time="09:25:00",
            open_board_count=0,
            turnover_rate=Decimal("0.18"),
            amount=Decimal("1000000000"),
            close_seal_amount=Decimal("50000000"),
            seal_ratio=Decimal("0.8"),
            float_mcap=Decimal("12000000000"),
            position_120=Decimal("0.3"),
            is_downtrend=False,
            near_pressure=False,
            same_subject_limit_count=3,
            same_subject_strong_count=2,
            data_quality={"missing_required": []},
            source_trace={"source": "unit"},
        )
    )

    assert rule.decision == "reject"
    assert "一字板" in "；".join(rule.veto_reasons)

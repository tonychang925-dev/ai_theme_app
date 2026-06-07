from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from stock_processing_service.application.services.one_to_two_setup_plan_engine import (
    OneToTwoSetupPlanEngine,
)
from stock_processing_service.application.jobs.build_post_market_recap_job import BuildPostMarketRecapJob
from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures
from stock_processing_service.contracts.dto.post_market_setup_context_dto import (
    PostMarketSetupFactContext,
    SetupFactContextBuildError,
    SourceStatus,
)
from stock_processing_service.contracts.dto.trade_calendar_dto import TradeCalendarDTO
from stock_processing_service.domain.services.one_to_two_rule_config import (
    OneToTwoRuleConfig,
    RULE_VERSION_V1_1,
    RULE_VERSION_V1_2,
    RULE_VERSION_V1_3,
    RULE_VERSION_V1_4,
)
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
        raise AssertionError("post_market_report_context should not be called")

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

    result = await engine.build(
        date(2026, 6, 4),
        fake,
        source_doc={
            "market_regime_review": {"trade_mode": "no_trade", "allow_trade": False},
            "trading_principle": {"position_limit": 0.0},
            "strong_hotspot_subjects": [],
            "pressure_by_stock": {},
            "ma_pattern_by_stock": {},
        },
    )

    assert result.summary["focus_count"] == 0
    assert result.items == []


def test_one_to_two_candidate_generation_uses_first_board_facts_without_strong_pool() -> None:
    engine = OneToTwoSetupPlanEngine()
    ctx = PostMarketSetupFactContext(
        trade_date="2026-05-26",
        watch_date="2026-05-27",
        active_mainlines=[{"mainline_id": "ml_HBM存储_202606", "canonical_subject_key": "9021399"}],
        strong_hotspot_subjects=[
            {"subject_key": "9021399", "theme_name": "HBM存储", "source": "confirmed_mainline"},
        ],
        active_subject_keys={"9021399"},
        lifecycle_by_subject={"9021399": {"lifecycle_state": "divergence"}},
        market_regime={"trade_mode": "normal", "allow_trade": True},
        trading_principle={"position_limit": 0.3},
        subject_stock_rows=[
            {
                "trade_date": "2026-05-26",
                "stock_id": "002579.SZ",
                "stock_name": "中京电子",
                "subject_key": "9021399",
                "subject_name": "HBM存储",
                "open_price": Decimal("13.67"),
                "high_price": Decimal("15.04"),
                "low_price": Decimal("13.67"),
                "close_price": Decimal("15.04"),
                "pct_chg": Decimal("10.02"),
                "limit_up": True,
                "is_leader": True,
                "open_board_count": 0,
                "first_limit_time": "09:41:00",
            }
        ],
        stock_daily_bars=[
            {
                "trade_date": "2026-05-24",
                "stock_id": "002579.SZ",
                "stock_name": "中京电子",
                "open_price": Decimal("12.90"),
                "high_price": Decimal("13.20"),
                "low_price": Decimal("12.60"),
                "close_price": Decimal("12.85"),
                "pre_close": Decimal("12.90"),
                "pct_chg": Decimal("-0.39"),
                "limit_up_price": Decimal("14.13"),
                "amount": Decimal("120000000"),
            },
            {
                "trade_date": "2026-05-25",
                "stock_id": "002579.SZ",
                "stock_name": "中京电子",
                "open_price": Decimal("12.88"),
                "high_price": Decimal("13.05"),
                "low_price": Decimal("12.70"),
                "close_price": Decimal("12.96"),
                "pre_close": Decimal("12.85"),
                "pct_chg": Decimal("0.86"),
                "limit_up_price": Decimal("14.26"),
                "amount": Decimal("132000000"),
            },
            {
                "trade_date": "2026-05-26",
                "stock_id": "002579.SZ",
                "stock_name": "中京电子",
                "open_price": Decimal("13.67"),
                "high_price": Decimal("15.04"),
                "low_price": Decimal("13.67"),
                "close_price": Decimal("15.04"),
                "pre_close": Decimal("13.67"),
                "pct_chg": Decimal("10.02"),
                "limit_up_price": Decimal("15.04"),
                "amount": Decimal("1557307115.83"),
            },
        ],
        limit_up_rows=[],
        subject_market_breadth={
            "9021399": {
                "subject_key": "9021399",
                "subject_limit_up_count": 2,
                "subject_strong_count": 4,
                "leader_pct_chg": 10.02,
                "member_count": 6,
                "leader_limit_up": True,
            }
        },
        confirmed_hotspot_rank={"9021399": 0},
        strong_hotspot_rank={"9021399": 0},
        subject_priority_rank={"9021399": 0},
        diagnostics=SourceStatus(source_status={"market_regime": "ready_non_empty"}),
    )

    result = engine.build_from_context(ctx)

    assert result.diagnostics["fact_pool_count"] == 1
    assert result.candidate_features[0]["stock_id"] == "002579.SZ"
    assert result.candidate_features[0]["subject_key"] == "9021399"
    assert result.candidate_features[0]["source_trace_json"]["subject_selection"]["selected_subject_key"] == "9021399"


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


def test_one_to_two_fact_pool_normalizes_stock_id_suffixes() -> None:
    engine = OneToTwoSetupPlanEngine()
    ctx = PostMarketSetupFactContext(
        trade_date="2026-05-06",
        watch_date="2026-05-07",
        active_mainlines=[{"mainline_id": "ml_AI光纤_202606", "canonical_subject_key": "9064103"}],
        strong_hotspot_subjects=[{"subject_key": "9064103", "theme_name": "AI光纤"}],
        active_subject_keys={"9064103"},
        lifecycle_by_subject={"9064103": {"lifecycle_state": "divergence"}},
        market_regime={"trade_mode": "normal", "allow_trade": True},
        trading_principle={"position_limit": 0.3},
        subject_stock_rows=[
            {
                "trade_date": "2026-05-06",
                "stock_id": "603618",
                "stock_name": "杭电股份",
                "subject_key": "9064103",
                "subject_name": "AI光纤",
                "open_price": Decimal("29.00"),
                "high_price": Decimal("31.09"),
                "low_price": Decimal("29.00"),
                "close_price": Decimal("31.09"),
                "pct_chg": Decimal("10.01"),
                "limit_up": True,
                "is_leader": True,
                "open_board_count": 0,
                "first_limit_time": "09:56:00",
            }
        ],
        stock_daily_bars=[
            {
                "trade_date": "2026-05-06",
                "stock_id": "603618.SH",
                "stock_name": "杭电股份",
                "open_price": Decimal("29.00"),
                "high_price": Decimal("31.09"),
                "low_price": Decimal("29.00"),
                "close_price": Decimal("31.09"),
                "pre_close": Decimal("28.26"),
                "pct_chg": Decimal("10.01"),
                "limit_up_price": Decimal("31.09"),
                "amount": Decimal("810396087"),
                "turnover_rate": Decimal("3.83"),
            }
        ],
        limit_up_rows=[],
        diagnostics=SourceStatus(source_status={"market_regime": "ready_non_empty"}),
    )

    result = engine.build_from_context(ctx)

    assert result.diagnostics["fact_pool_count"] == 1
    assert len(result.candidate_features) == 1
    assert result.candidate_features[0]["stock_id"] == "603618.SH"


def test_one_to_two_subject_choice_prefers_strong_hotspot_over_other_active_mainline() -> None:
    from stock_processing_service.domain.services.one_to_two_candidate_service import OneToTwoCandidateService

    svc = OneToTwoCandidateService()
    rows = [
        {"trade_date": "2026-05-06", "stock_id": "603618.SH", "subject_key": "9014636", "rank_order": 2, "is_leader": True},
        {"trade_date": "2026-05-06", "stock_id": "603618.SH", "subject_key": "9064103", "rank_order": 1, "is_leader": True},
    ]
    chosen = svc._choose_subject_row(
        rows,
        "2026-05-06",
        active_subject_keys={"9014636", "9064103"},
        strong_hotspot_keys={"9064103"},
        subject_priority_rank={"9064103": 0, "9014636": 1},
    )

    assert chosen is not None
    assert chosen["subject_key"] == "9064103"


def test_one_to_two_subject_choice_prefers_confirmed_hotspot_over_other_strong_hotspot() -> None:
    from stock_processing_service.domain.services.one_to_two_candidate_service import OneToTwoCandidateService

    svc = OneToTwoCandidateService()
    rows = [
        {"trade_date": "2026-05-06", "stock_id": "603618.SH", "subject_key": "9014636", "rank_order": 1, "is_leader": True},
        {"trade_date": "2026-05-06", "stock_id": "603618.SH", "subject_key": "9064103", "rank_order": 9, "is_leader": False},
    ]
    chosen = svc._choose_subject_row(
        rows,
        "2026-05-06",
        active_subject_keys={"9014636", "9064103"},
        strong_hotspot_keys={"9014636", "9064103"},
        confirmed_hotspot_keys={"9064103"},
        subject_priority_rank={"9064103": 0, "9014636": 1},
    )

    assert chosen is not None
    assert chosen["subject_key"] == "9064103"


def test_one_to_two_subject_choice_prefers_ranked_confirmed_hotspot_order() -> None:
    from stock_processing_service.domain.services.one_to_two_candidate_service import OneToTwoCandidateService

    svc = OneToTwoCandidateService()
    rows = [
        {"trade_date": "2026-05-06", "stock_id": "603618.SH", "subject_key": "9014636", "rank_order": 1, "is_leader": True},
        {"trade_date": "2026-05-06", "stock_id": "603618.SH", "subject_key": "9064103", "rank_order": 9, "is_leader": False},
    ]
    chosen = svc._choose_subject_row(
        rows,
        "2026-05-06",
        active_subject_keys={"9014636", "9064103"},
        strong_hotspot_keys={"9014636", "9064103"},
        confirmed_hotspot_keys={"9014636", "9064103"},
        subject_priority_rank={"9064103": 0, "9014636": 1},
    )

    assert chosen is not None
    assert chosen["subject_key"] == "9064103"


def test_one_to_two_subject_choice_prefers_stock_subject_authenticity_over_subject_level() -> None:
    from stock_processing_service.domain.services.one_to_two_candidate_service import OneToTwoCandidateService

    svc = OneToTwoCandidateService()
    rows = [
        {"trade_date": "2026-05-06", "stock_id": "603618.SH", "subject_key": "9014636", "rank_order": 1, "is_leader": False},
        {"trade_date": "2026-05-06", "stock_id": "603618.SH", "subject_key": "9064103", "rank_order": 9, "is_leader": False},
    ]
    chosen = svc._choose_subject_row(
        rows,
        "2026-05-06",
        active_subject_keys={"9014636", "9064103"},
        strong_hotspot_keys={"9014636", "9064103"},
        confirmed_hotspot_keys={"9014636", "9064103"},
        subject_priority_rank={"9014636": 0, "9064103": 1},
        subject_authenticity_by_subject={"9014636": {"score": 30.0}, "9064103": {"score": 30.0}},
        stock_subject_authenticity_by_pair={"603618|9014636": {"score": 40.0}, "603618|9064103": {"score": 95.0}},
    )

    assert chosen is not None
    assert chosen["subject_key"] == "9064103"


def test_one_to_two_subject_selection_trace_records_priority_reason() -> None:
    engine = OneToTwoSetupPlanEngine()
    ctx = PostMarketSetupFactContext(
        trade_date="2026-05-06",
        watch_date="2026-05-07",
        active_mainlines=[{"mainline_id": "ml_AI光纤_202606", "canonical_subject_key": "9064103"}],
        strong_hotspot_subjects=[
            {"subject_key": "9064103", "theme_name": "AI光纤", "source": "confirmed_mainline"},
            {"subject_key": "9014636", "theme_name": "机器人", "source": "confirmed_mainline"},
        ],
        active_subject_keys={"9064103", "9014636"},
        lifecycle_by_subject={"9064103": {"lifecycle_state": "divergence"}, "9014636": {"lifecycle_state": "divergence"}},
        market_regime={"trade_mode": "normal", "allow_trade": True},
        trading_principle={"position_limit": 0.3},
        subject_stock_rows=[
            {
                "trade_date": "2026-05-06",
                "stock_id": "603618",
                "stock_name": "杭电股份",
                "subject_key": "9014636",
                "subject_name": "机器人",
                "open_price": Decimal("29.00"),
                "high_price": Decimal("31.09"),
                "low_price": Decimal("29.00"),
                "close_price": Decimal("31.09"),
                "pct_chg": Decimal("10.01"),
                "limit_up": True,
                "is_leader": True,
                "open_board_count": 0,
                "first_limit_time": "09:56:00",
            },
            {
                "trade_date": "2026-05-06",
                "stock_id": "603618",
                "stock_name": "杭电股份",
                "subject_key": "9064103",
                "subject_name": "AI光纤",
                "open_price": Decimal("29.00"),
                "high_price": Decimal("31.09"),
                "low_price": Decimal("29.00"),
                "close_price": Decimal("31.09"),
                "pct_chg": Decimal("10.01"),
                "limit_up": True,
                "is_leader": False,
                "open_board_count": 0,
                "first_limit_time": "09:56:00",
            },
        ],
        stock_daily_bars=[
            {
                "trade_date": "2026-05-06",
                "stock_id": "603618.SH",
                "stock_name": "杭电股份",
                "open_price": Decimal("29.00"),
                "high_price": Decimal("31.09"),
                "low_price": Decimal("29.00"),
                "close_price": Decimal("31.09"),
                "pre_close": Decimal("28.26"),
                "pct_chg": Decimal("10.01"),
                "limit_up_price": Decimal("31.09"),
                "amount": Decimal("810396087"),
                "turnover_rate": Decimal("3.83"),
            }
        ],
        limit_up_rows=[],
        confirmed_hotspot_rank={"9064103": 0, "9014636": 1},
        strong_hotspot_rank={"9064103": 0, "9014636": 1},
        subject_priority_rank={"9064103": 0, "9014636": 1},
        diagnostics=SourceStatus(source_status={"market_regime": "ready_non_empty"}),
    )

    result = engine.build_from_context(ctx)

    assert result.diagnostics["fact_pool_count"] == 1
    assert result.summary["rule_version"] == "one_to_two_v1.0_post_market_plan"
    trace = result.candidate_features[0]["source_trace_json"]["subject_selection"]
    assert result.candidate_features[0]["rule_version"] == "one_to_two_v1.0_post_market_plan"
    assert result.candidate_features[0]["source_trace_json"]["rule_version"] == "one_to_two_v1.0_post_market_plan"
    assert trace["selected_subject_key"] == "9064103"
    assert trace["candidate_subject_keys"] == ["9014636", "9064103"]
    assert trace["selection_reason"] == "confirmed_hotspot_rank"


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


def test_one_to_two_candidate_features_include_rejects_for_audit() -> None:
    engine = OneToTwoSetupPlanEngine()
    engine.candidate_service.build_fact_pool = lambda ctx: [  # type: ignore[assignment]
        OneToTwoFeatures(
            trade_date="2026-06-04",
            watch_date="2026-06-05",
            stock_id="600367.SH",
            stock_name="红星发展",
            subject_key="mainline_ai",
            subject_name="AI",
            is_confirmed_mainline=True,
            is_strong_hotspot=True,
            mainline_or_hotspot_state="confirmed_mainline",
            lifecycle_state="start",
            market_trade_mode="mainline_ultra_short_only",
            allow_trade=True,
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
        ),
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
            turnover_rate=Decimal("0.10"),
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
        ),
    ]

    result = engine.build_from_context(_setup_context())

    assert len(result.candidate_features) == 2
    assert len(result.items) == 1
    assert result.summary["reject_count"] == 1
    assert any(feature["decision"] == "reject" for feature in result.candidate_features)


@pytest.mark.asyncio
async def test_one_to_two_plan_and_candidate_feature_round_trip_by_setup_type() -> None:
    engine = OneToTwoSetupPlanEngine()
    engine.candidate_service.build_fact_pool = lambda ctx: [  # type: ignore[assignment]
        OneToTwoFeatures(
            trade_date="2026-06-04",
            watch_date="2026-06-05",
            stock_id="600367.SH",
            stock_name="红星发展",
            subject_key="mainline_ai",
            subject_name="AI",
            is_confirmed_mainline=True,
            is_strong_hotspot=True,
            mainline_or_hotspot_state="confirmed_mainline",
            lifecycle_state="start",
            market_trade_mode="mainline_ultra_short_only",
            allow_trade=True,
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
        ),
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
            turnover_rate=Decimal("0.10"),
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
        ),
    ]

    plan = engine.build_from_context(_setup_context())
    setup_plan_rows, candidate_feature_rows = BuildPostMarketRecapJob._build_one_to_two_persist_rows(plan)

    class _Store:
        def __init__(self):
            self.plan_rows: list[dict[str, Any]] = []
            self.feature_rows: list[dict[str, Any]] = []

        async def upsert_post_market_setup_plan_rows(self, rows):
            self.plan_rows.extend(rows)
            return len(rows)

        async def upsert_one_to_two_candidate_feature_rows(self, rows):
            self.feature_rows.extend(rows)
            return len(rows)

        async def get_post_market_setup_plan_rows(self, trade_date, setup_type="one_to_two"):
            return [
                row for row in self.plan_rows
                if str(row.get("trade_date")) == str(trade_date)
                and str(row.get("setup_type") or "") == setup_type
            ]

        async def get_one_to_two_candidate_feature_rows(self, trade_date, setup_type="one_to_two"):
            return [
                row for row in self.feature_rows
                if str(row.get("trade_date")) == str(trade_date)
                and str(row.get("setup_type") or "") == setup_type
            ]

    store = _Store()
    await store.upsert_post_market_setup_plan_rows(setup_plan_rows)
    await store.upsert_one_to_two_candidate_feature_rows(candidate_feature_rows)
    store.feature_rows.append(
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "other_setup",
            "stock_id": "999999.SH",
            "subject_key": "other",
            "decision": "reject",
            "veto_reasons": ["other"],
        }
    )

    plan_rows = await store.get_post_market_setup_plan_rows("2026-06-04", "one_to_two")
    feature_rows = await store.get_one_to_two_candidate_feature_rows("2026-06-04", "one_to_two")
    other_rows = await store.get_one_to_two_candidate_feature_rows("2026-06-04", "other_setup")

    assert len([row for row in plan_rows if row["stock_id"] == "__SUMMARY__"]) == 1
    assert len([row for row in plan_rows if row["stock_id"] != "__SUMMARY__"]) == len(plan.items)
    assert len(feature_rows) == len(plan.candidate_features)
    assert all(row["stock_id"] != "__SUMMARY__" for row in feature_rows)
    assert len(other_rows) == 1
    assert other_rows[0]["setup_type"] == "other_setup"
    reject_rows = [row for row in feature_rows if row["decision"] == "reject"]
    assert reject_rows
    assert all(row.get("veto_reasons") for row in reject_rows)
    assert all(isinstance(row.get("veto_reasons"), list) or row.get("veto_reasons") is None for row in feature_rows)
    assert all(row.get("setup_type") == "one_to_two" for row in feature_rows)


def _versioned_feature(
    *,
    turnover_rate: Decimal,
    same_subject_limit_count: int,
    same_subject_strong_count: int,
    subject_key: str = "9064103",
    is_confirmed_mainline: bool = True,
    first_board_type: str = "chain_first_board",
    first_board_trace: dict[str, object] | None = None,
    first_board_quality_tags: list[str] | None = None,
) -> OneToTwoFeatures:
    return OneToTwoFeatures(
        trade_date="2026-05-07",
        watch_date="2026-05-08",
        stock_id="603618.SH",
        stock_name="杭电股份",
        subject_key=subject_key,
        subject_name="AI光纤",
        is_confirmed_mainline=is_confirmed_mainline,
        is_strong_hotspot=True,
        mainline_or_hotspot_state="confirmed_mainline" if is_confirmed_mainline else "strong_hotspot",
        lifecycle_state="start",
        market_trade_mode="normal",
        allow_trade=True,
        is_first_limit_up=True,
        is_one_word_board=False,
        is_late_seal=False,
        first_limit_time="09:56:00",
        open_board_count=1,
        turnover_rate=turnover_rate,
        amount=Decimal("810396087"),
        close_seal_amount=Decimal("50000000"),
        seal_ratio=Decimal("0.80"),
        float_mcap=Decimal("12000000000"),
        position_120=Decimal("0.30"),
        is_downtrend=False,
        near_pressure=False,
        same_subject_limit_count=same_subject_limit_count,
        same_subject_strong_count=same_subject_strong_count,
        data_quality={"missing_required": []},
        source_trace={"source": "unit"},
        first_board_type=first_board_type,
        first_board_trace=first_board_trace or {"first_board_type_reason": first_board_type},
        first_board_quality_tags=first_board_quality_tags or ["strict_first_board"],
    )


def test_one_to_two_rule_v1_0_keeps_current_hard_vetoes() -> None:
    rule = OneToTwoRuleEngine().apply(
        _versioned_feature(
            turnover_rate=Decimal("0.05"),
            same_subject_limit_count=1,
            same_subject_strong_count=7,
        )
    )

    assert rule.decision == "reject"
    assert "低换手" in "；".join(rule.veto_reasons)
    assert "无板块合力" in "；".join(rule.veto_reasons)


def test_one_to_two_rule_v1_1_allows_strong_breadth_but_caps_focus() -> None:
    rule = OneToTwoRuleEngine(OneToTwoRuleConfig.from_version(RULE_VERSION_V1_1)).apply(
        _versioned_feature(
            turnover_rate=Decimal("0.18"),
            same_subject_limit_count=1,
            same_subject_strong_count=7,
        )
    )

    assert rule.decision == "observe_only"
    assert rule.veto_reasons == []
    assert "涨停合力不足但强势扩散存在" in rule.risk_flags


def test_one_to_two_rule_v1_2_tiered_turnover_caps_focus() -> None:
    rule = OneToTwoRuleEngine(OneToTwoRuleConfig.from_version(RULE_VERSION_V1_2)).apply(
        _versioned_feature(
            turnover_rate=Decimal("0.05"),
            same_subject_limit_count=3,
            same_subject_strong_count=7,
        )
    )

    assert rule.decision == "observe_only"
    assert rule.veto_reasons == []
    assert "低换手，先观察不 focus" in rule.risk_flags


def test_one_to_two_rule_v1_3_combines_soft_breadth_and_low_turnover() -> None:
    rule = OneToTwoRuleEngine(OneToTwoRuleConfig.from_version(RULE_VERSION_V1_3)).apply(
        _versioned_feature(
            turnover_rate=Decimal("0.05"),
            same_subject_limit_count=1,
            same_subject_strong_count=7,
        )
    )

    assert rule.decision == "observe_only"
    assert rule.veto_reasons == []
    assert "涨停合力不足但强势扩散存在" in rule.risk_flags
    assert "低换手，先观察不 focus" in rule.risk_flags


def test_one_to_two_rule_v1_0_accepts_only_chain_first_board() -> None:
    strict_rule = OneToTwoRuleEngine().apply(
        _versioned_feature(
            turnover_rate=Decimal("0.18"),
            same_subject_limit_count=3,
            same_subject_strong_count=7,
            first_board_type="chain_first_board",
        )
    )
    relaunch_rule = OneToTwoRuleEngine().apply(
        _versioned_feature(
            turnover_rate=Decimal("0.18"),
            same_subject_limit_count=3,
            same_subject_strong_count=7,
            first_board_type="not_first_board",
        )
    )

    assert strict_rule.decision in {"focus", "observe_only"}
    assert relaunch_rule.decision == "reject"
    assert "不符合首板类型: not_first_board" in "；".join(relaunch_rule.veto_reasons)


def test_one_to_two_rule_config_default_uses_chain_first_board() -> None:
    config = OneToTwoRuleConfig()

    assert config.allowed_first_board_types == ("chain_first_board",)


@pytest.mark.parametrize(
    "first_board_quality_tags",
    [["relaunch_first_board"], ["trend_first_board"], ["oversold_first_board"]],
)
def test_one_to_two_rule_v1_4_accepts_extended_first_board_quality_tags(first_board_quality_tags: list[str]) -> None:
    rule = OneToTwoRuleEngine(OneToTwoRuleConfig.from_version(RULE_VERSION_V1_4)).apply(
        _versioned_feature(
            turnover_rate=Decimal("0.18"),
            same_subject_limit_count=3,
            same_subject_strong_count=7,
            first_board_type="chain_first_board",
            first_board_trace={
                "first_board_type_reason": "previous_trade_day_not_limit_up",
                "first_board_quality_tags": first_board_quality_tags,
            },
            first_board_quality_tags=first_board_quality_tags,
        )
    )

    assert rule.decision in {"focus", "observe_only", "pending_review_only"}
    assert rule.veto_reasons == []
    assert rule.risk_flags == []


def test_one_to_two_first_board_trace_persisted_to_snapshot_payload() -> None:
    engine = OneToTwoSetupPlanEngine()
    engine.candidate_service.build_fact_pool = lambda ctx: [  # type: ignore[assignment]
        _versioned_feature(
            turnover_rate=Decimal("0.18"),
            same_subject_limit_count=3,
            same_subject_strong_count=7,
            first_board_type="chain_first_board",
            first_board_trace={
                "current_limit_up": True,
                "previous_trade_date": "2026-05-06",
                "previous_trade_date_limit_up": False,
                "limit_streak_count": 1,
                "position_label": "low",
                "first_board_type_reason": "previous_trade_day_not_limit_up",
            },
            first_board_quality_tags=["relaunch_first_board"],
        )
    ]

    result = engine.build_from_context(_setup_context())

    assert result.candidate_features[0]["first_board_type"] == "chain_first_board"
    assert result.candidate_features[0]["first_board_quality_tags"] == ["relaunch_first_board"]
    assert result.candidate_features[0]["first_board_trace"]["first_board_type_reason"] == "previous_trade_day_not_limit_up"
    assert result.candidate_features[0]["source_trace_json"]["first_board_type"] == "chain_first_board"
    assert result.candidate_features[0]["source_trace_json"]["first_board_quality_tags"] == ["relaunch_first_board"]
    assert result.candidate_features[0]["source_trace_json"]["first_board_trace"]["previous_trade_date"] == "2026-05-06"

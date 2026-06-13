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
from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures, RuleResult, ScoreResult
from stock_processing_service.contracts.dto.post_market_setup_context_dto import (
    PostMarketSetupFactContext,
    SetupFactContextBuildError,
    SourceStatus,
)
from stock_processing_service.contracts.dto.trade_calendar_dto import TradeCalendarDTO
from stock_processing_service.domain.services.one_to_two_rule_config import (
    DEFAULT_RULE_VERSION,
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
    assert result.summary["rule_version"] == DEFAULT_RULE_VERSION
    trace = result.candidate_features[0]["source_trace_json"]["subject_selection"]
    assert result.candidate_features[0]["rule_version"] == DEFAULT_RULE_VERSION
    assert result.candidate_features[0]["source_trace_json"]["rule_version"] == DEFAULT_RULE_VERSION
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
        kline_pattern_quality={
            "kline_data_ready": True,
            "has_golden_spider": True,
            "score": 75.0,
            "level": "golden",
            "support_broken": False,
            "is_downtrend": False,
            "kline_near_resistance": False,
        },
        first_board_type=first_board_type,
        first_board_trace=first_board_trace or {"first_board_type_reason": first_board_type},
        first_board_quality_tags=first_board_quality_tags or ["strict_first_board"],
    )


def test_one_to_two_rule_default_version_keeps_extreme_low_turnover_vetoes() -> None:
    rule = OneToTwoRuleEngine().apply(
        _versioned_feature(
            turnover_rate=Decimal("0.01"),
            same_subject_limit_count=3,
            same_subject_strong_count=7,
        )
    )

    assert rule.decision == "reject"
    assert "低换手" in "；".join(rule.veto_reasons)
    assert "无板块合力" not in "；".join(rule.veto_reasons)


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


def test_one_to_two_rule_default_version_accepts_only_chain_first_board() -> None:
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


def test_one_to_two_rule_config_blocks_v1_0_direct_instantiation() -> None:
    with pytest.raises(ValueError, match="unsupported OneToTwo rule version"):
        OneToTwoRuleConfig(rule_version="legacy_blocked_rule_version")


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


# ── Stage 2: score_policy + ranking tests ──

def test_score_policy_final_score_below_80_caps_focus() -> None:
    engine = OneToTwoSetupPlanEngine()
    f = _versioned_feature(turnover_rate=Decimal("0.18"), same_subject_limit_count=3, same_subject_strong_count=7)
    rule = RuleResult(decision="focus", veto_reasons=[], risk_flags=[])
    score = ScoreResult(final_score=Decimal("72.00"), watch_level="B", score_detail={
        "technical_structure": "70", "theme_authenticity": "65",
        "board_breadth": "75", "first_board_quality": "80", "risk_control": "70",
    })
    result = engine._apply_score_policy(f, rule, score)
    assert result.decision == "observe_only"
    assert any("综合评分" in rf for rf in result.risk_flags)


def test_score_policy_technical_structure_below_55_caps_focus() -> None:
    engine = OneToTwoSetupPlanEngine()
    f = _versioned_feature(turnover_rate=Decimal("0.18"), same_subject_limit_count=3, same_subject_strong_count=7)
    rule = RuleResult(decision="focus", veto_reasons=[], risk_flags=[])
    score = ScoreResult(final_score=Decimal("85.00"), watch_level="A", score_detail={
        "technical_structure": "48", "theme_authenticity": "90",
        "board_breadth": "90", "first_board_quality": "90", "risk_control": "90",
    })
    result = engine._apply_score_policy(f, rule, score)
    assert result.decision == "observe_only"
    assert any("技术形态评分" in rf for rf in result.risk_flags)


def test_score_policy_passes_when_both_scores_ok() -> None:
    engine = OneToTwoSetupPlanEngine()
    f = _versioned_feature(turnover_rate=Decimal("0.18"), same_subject_limit_count=3, same_subject_strong_count=7)
    rule = RuleResult(decision="focus", veto_reasons=[], risk_flags=[])
    score = ScoreResult(final_score=Decimal("86.00"), watch_level="A", score_detail={
        "technical_structure": "68", "theme_authenticity": "90",
        "board_breadth": "90", "first_board_quality": "90", "risk_control": "90",
    })
    result = engine._apply_score_policy(f, rule, score)
    assert result.decision == "focus"


def test_score_policy_does_not_downgrade_observe_only() -> None:
    engine = OneToTwoSetupPlanEngine()
    f = _versioned_feature(turnover_rate=Decimal("0.18"), same_subject_limit_count=3, same_subject_strong_count=7)
    rule = RuleResult(decision="observe_only", veto_reasons=[], risk_flags=["no_trade"])
    score = ScoreResult(final_score=Decimal("92.00"), watch_level="A", score_detail={
        "technical_structure": "80", "theme_authenticity": "90",
        "board_breadth": "90", "first_board_quality": "90", "risk_control": "90",
    })
    result = engine._apply_score_policy(f, rule, score)
    assert result.decision == "observe_only"


def test_ranking_orders_by_score_and_technical() -> None:
    engine = OneToTwoSetupPlanEngine()
    engine.candidate_service.build_fact_pool = lambda ctx: [
        _versioned_feature(turnover_rate=Decimal("0.12"), same_subject_limit_count=5, same_subject_strong_count=8, subject_key="s1"),
        _versioned_feature(turnover_rate=Decimal("0.09"), same_subject_limit_count=3, same_subject_strong_count=4, subject_key="s2"),
        _versioned_feature(turnover_rate=Decimal("0.15"), same_subject_limit_count=6, same_subject_strong_count=10, subject_key="s3"),
    ]
    result = engine.build_from_context(_setup_context())
    items = result.items or []
    assert len(items) >= 1
    for item in items:
        assert "rank_no" in item
        assert "rank_reason" in item
        assert isinstance(item["rank_no"], int)
    # All items should be observe_only (score < 80)
    assert all(item["decision"] == "observe_only" for item in items)


# ── P1-B: __independent__ exclusion ──

def test_independent_subject_not_in_one_to_two_candidates() -> None:
    """CandidateService must skip subject_key='__independent__'."""
    from stock_processing_service.domain.services.one_to_two_candidate_service import OneToTwoCandidateService

    ctx = PostMarketSetupFactContext(
        trade_date="2026-06-08",
        watch_date="2026-06-09",
        active_mainlines=[],
        strong_hotspot_subjects=[{"subject_key": "__independent__", "theme_name": "独立龙头"}, {"subject_key": "9018144", "theme_name": "PCB"}],
        active_subject_keys={"9018144"},
        lifecycle_by_subject={},
        market_regime={"trade_mode": "no_trade", "allow_trade": False},
        trading_principle={"position_limit": 0.0},
        subject_stock_rows=[
            {"trade_date": "2026-06-08", "stock_id": "301486.SZ", "stock_name": "致尚科技",
             "subject_key": "__independent__", "pct_chg": -5.95, "limit_up": False},
            {"trade_date": "2026-06-08", "stock_id": "600110.SH", "stock_name": "诺德股份",
             "subject_key": "9018144", "pct_chg": 10.0, "limit_up": True},
        ],
        stock_daily_bars=[
            {"trade_date": "2026-06-08", "stock_id": "301486.SZ", "stock_name": "致尚科技",
             "close_price": 100, "limit_up_price": 120, "pct_chg": -5.95, "limit_up": False},
            {"trade_date": "2026-06-08", "stock_id": "600110.SH", "stock_name": "诺德股份",
             "close_price": 100, "limit_up_price": 90, "pct_chg": 10.0, "limit_up": True},
        ],
        limit_up_rows=[
            {"trade_date": "2026-06-08", "stock_id": "600110.SH", "stock_name": "诺德股份",
             "is_first_limit_up": True, "pct_chg": 10.0},
        ],
        diagnostics=SourceStatus(source_status={"market_regime": "ready"}),
    )

    service = OneToTwoCandidateService()
    pool = service.build_fact_pool(ctx)

    subject_keys_in_pool = {f.subject_key for f in pool}
    assert "__independent__" not in subject_keys_in_pool, (
        f"__independent__ must not enter OneToTwo candidate pool, got: {subject_keys_in_pool}"
    )
    # 诺德股份 should still be in pool (it's in a real subject)
    assert "9018144" in subject_keys_in_pool


def test_independent_subject_not_written_to_plan_items() -> None:
    """Plan items must not include __independent__ subjects."""
    from stock_processing_service.domain.services.one_to_two_candidate_service import OneToTwoCandidateService
    from stock_processing_service.domain.services.one_to_two_rule_engine import OneToTwoRuleEngine
    from stock_processing_service.domain.services.one_to_two_scorer import OneToTwoScorer
    from stock_processing_service.domain.services.one_to_two_risk_plan_builder import OneToTwoRiskPlanBuilder
    from stock_processing_service.domain.services.one_to_two_rule_config import OneToTwoRuleConfig

    engine = OneToTwoSetupPlanEngine()
    engine.candidate_service = OneToTwoCandidateService()
    engine.rule_engine = OneToTwoRuleEngine(OneToTwoRuleConfig())
    engine.scorer = OneToTwoScorer()
    engine.risk_plan_builder = OneToTwoRiskPlanBuilder()

    ctx = PostMarketSetupFactContext(
        trade_date="2026-06-08",
        watch_date="2026-06-09",
        active_mainlines=[{"canonical_subject_key": "9018144", "mainline_name": "PCB"}],
        strong_hotspot_subjects=[{"subject_key": "__independent__", "theme_name": "独立龙头"}],
        active_subject_keys={"9018144"},
        lifecycle_by_subject={"9018144": {"lifecycle_state": "fermentation"}},
        market_regime={"trade_mode": "mainline_core_only", "allow_trade": True},
        trading_principle={"position_limit": 0.2, "allow_trade": True},
        subject_stock_rows=[
            {"trade_date": "2026-06-08", "stock_id": "301486.SZ", "stock_name": "致尚科技",
             "subject_key": "__independent__", "pct_chg": -5.95, "limit_up": False},
            {"trade_date": "2026-06-08", "stock_id": "600110.SH", "stock_name": "诺德股份",
             "subject_key": "9018144", "pct_chg": 10.0, "limit_up": True},
        ],
        stock_daily_bars=[
            {"trade_date": "2026-06-08", "stock_id": "301486.SZ", "stock_name": "致尚科技",
             "close_price": 100, "limit_up_price": 120, "pct_chg": -5.95, "limit_up": False, "turnover_rate": 0.05, "amount": 50000000},
            {"trade_date": "2026-06-08", "stock_id": "600110.SH", "stock_name": "诺德股份",
             "close_price": 100, "limit_up_price": 90, "pct_chg": 10.0, "limit_up": True, "turnover_rate": 0.10, "amount": 500000000},
        ],
        limit_up_rows=[
            {"trade_date": "2026-06-08", "stock_id": "600110.SH", "stock_name": "诺德股份",
             "is_first_limit_up": True, "pct_chg": 10.0, "first_limit_time": "10:00:00"},
        ],
        diagnostics=SourceStatus(source_status={"market_regime": "ready"}),
    )

    result = engine.build_from_context(ctx)

    subject_keys_in_items = {str(item.get("subject_key", "")) for item in result.items}
    assert "__independent__" not in subject_keys_in_items, (
        f"__independent__ must not appear in plan items, got: {subject_keys_in_items}"
    )


# ── breadth_missing vs breadth truly zero ──

def _features(**overrides) -> OneToTwoFeatures:
    """Minimal valid focus candidate, breadth=3."""
    defaults = dict(
        trade_date="2026-06-04",
        watch_date="2026-06-05",
        stock_id="600001.SH",
        stock_name="测试股",
        subject_key="robot",
        subject_name="机器人",
        is_confirmed_mainline=True,
        is_strong_hotspot=False,
        mainline_or_hotspot_state="confirmed_mainline",
        lifecycle_state="fermentation",
        market_trade_mode="mainline_ultra_short_only",
        allow_trade=True,
        is_first_limit_up=True,
        is_one_word_board=False,
        is_late_seal=False,
        first_limit_time="10:00:00",
        open_board_count=1,
        turnover_rate=Decimal("0.15"),
        amount=Decimal("800000000"),
        close_seal_amount=Decimal("50000000"),
        seal_ratio=Decimal("0.7"),
        float_mcap=Decimal("5000000000"),
        position_120=Decimal("0.3"),
        is_downtrend=False,
        near_pressure=False,
        same_subject_limit_count=3,
        same_subject_strong_count=2,
        first_board_type="chain_first_board",
        data_quality={"missing_required": [], "has_breadth": True, "breadth_missing": False},
        source_trace={"source": "unit"},
    )
    defaults.update(overrides)
    return OneToTwoFeatures(**defaults)


def test_breadth_missing_downgrades_focus_to_pending_review_only() -> None:
    """When subject_board_stats is unavailable, breadth_unknown → focus → pending_review_only."""
    f = _features(
        data_quality={"missing_required": [], "has_breadth": False, "breadth_missing": True},
        same_subject_limit_count=None,
        same_subject_strong_count=None,
    )
    result = OneToTwoRuleEngine().apply(f)
    # Must NOT be reject — breadth_missing is not a hard veto
    assert result.decision != "reject", f"expected non-reject, got {result.decision}: {result.veto_reasons}"
    # Must NOT be focus — unknown breadth cannot focus
    assert result.decision != "focus", f"expected non-focus, got {result.decision}"
    # Should be pending_review_only
    assert result.decision == "pending_review_only", f"expected pending_review_only, got {result.decision}"
    # Risk flags must mention breadth missing
    assert any("板块合力数据缺失" in flag for flag in result.risk_flags), f"missing breadth flag in: {result.risk_flags}"


def test_breadth_missing_not_in_missing_required() -> None:
    """board_breadth missing should NOT appear in missing_required (it is an optional source)."""
    f = _features(
        data_quality={
            "missing_required": [],  # board_breadth absent from missing_required
            "has_breadth": False,
            "breadth_missing": True,
        },
        same_subject_limit_count=None,
        same_subject_strong_count=None,
    )
    result = OneToTwoRuleEngine().apply(f)
    # Must not contain the fake "必需字段缺失: ['board_breadth']" error
    assert not any("board_breadth" in r for r in result.veto_reasons), (
        f"board_breadth should not appear in veto reasons: {result.veto_reasons}"
    )
    assert result.decision != "reject", f"missing optional breadth must not hard-reject: {result.veto_reasons}"


def test_breadth_truly_zero_still_hard_rejects() -> None:
    """When board_row exists and count is truly 0, '无板块合力' veto still applies."""
    f = _features(
        data_quality={"missing_required": [], "has_breadth": True, "breadth_missing": False},
        same_subject_limit_count=0,
        same_subject_strong_count=0,
    )
    result = OneToTwoRuleEngine().apply(f)
    assert result.decision == "reject", f"expected reject for true zero breadth, got {result.decision}"
    assert any("无板块合力" in r for r in result.veto_reasons), f"missing 无板块合力 in {result.veto_reasons}"


def test_subject_board_stats_missing_diagnostics() -> None:
    """When limit_up_rows non-empty but subject_market_breadth empty, diagnostics flag set."""
    from stock_processing_service.application.jobs.build_post_market_recap_job import BuildPostMarketRecapJob

    ctx = PostMarketSetupFactContext(
        trade_date="2026-06-04",
        watch_date="2026-06-05",
        active_mainlines=[{"canonical_subject_key": "robot", "subject_key": "robot", "mainline_name": "机器人"}],
        strong_hotspot_subjects=[],
        confirmed_hotspot_keys=set(),
        active_subject_keys={"robot"},
        lifecycle_by_subject={"robot": {"state": "fermentation", "lifecycle_state": "fermentation"}},
        market_regime={"trade_mode": "mainline_ultra_short_only", "allow_trade": True},
        trading_principle={"allow_trade": True, "trade_mode": "mainline_ultra_short_only"},
        subject_stock_rows=[
            {"trade_date": "2026-06-04", "stock_id": "600001.SH", "stock_name": "测试股",
             "subject_key": "robot", "pct_chg": 10.0, "limit_up": True},
        ],
        stock_daily_bars=[
            {"trade_date": "2026-06-04", "stock_id": "600001.SH", "stock_name": "测试股",
             "close_price": 100, "limit_up_price": 90, "pct_chg": 10.0, "limit_up": True,
             "amount": 800000000, "turnover_rate": 15.0},
        ],
        limit_up_rows=[
            {"trade_date": "2026-06-04", "stock_id": "600001.SH", "stock_name": "测试股",
             "close_price": 100, "limit_up_price": 90, "pct_chg": 10.0, "limit_up": True,
             "amount": 800000000, "turnover_rate": 15.0},
        ],
        subject_market_breadth={},  # EMPTY — triggers diagnostic
        diagnostics=SourceStatus(source_status={"market_regime": "ready"}),
    )

    engine = OneToTwoSetupPlanEngine()
    result = engine.build_from_context(ctx)

    assert result.diagnostics["subject_board_stats_missing"] is True
    assert result.diagnostics["breadth_stats"]["subject_board_stats"] == "ready_empty"
    assert any(
        "SUBJECT_BOARD_STATS_MISSING" in w
        for w in result.diagnostics["non_blocking_warnings"]
    ), f"missing SUBJECT_BOARD_STATS_MISSING in warnings: {result.diagnostics['non_blocking_warnings']}"

    # With breadth missing, candidates should be pending_review_only, not reject
    non_reject = [i for i in result.items if i["decision"] != "reject"]
    assert len(non_reject) > 0, f"expected non-reject items when breadth missing, got all rejected"
    for item in non_reject:
        assert item["decision"] != "focus", (
            f"focus forbidden when breadth is missing: {item['decision']}"
        )


def test_lifecycle_missing_not_in_missing_required() -> None:
    """lifecycle data missing should NOT trigger early 'required fields missing' reject."""
    f = _features(
        data_quality={
            "missing_required": [],  # lifecycle absent from missing_required
            "has_breadth": True,
            "breadth_missing": False,
            "has_lifecycle": False,
        },
        lifecycle_state="unknown",
    )
    result = OneToTwoRuleEngine().apply(f)
    # Must not contain the fake "必需字段缺失: ['lifecycle']" error
    assert not any("lifecycle" in r for r in result.veto_reasons), (
        f"lifecycle should not appear in veto reasons: {result.veto_reasons}"
    )
    # Missing lifecycle should not hard-reject — "unknown" state passes lifecycle checks
    assert result.decision != "reject", (
        f"missing lifecycle must not hard-reject: veto={result.veto_reasons}"
    )

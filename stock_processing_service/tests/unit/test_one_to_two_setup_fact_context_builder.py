from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

import pytest

from stock_processing_service.application.services.post_market_setup_fact_context_builder import (
    PostMarketSetupFactContextBuilder,
)
from stock_processing_service.contracts.dto.trade_calendar_dto import TradeCalendarDTO


class _MissingMarketContextReadPort:
    async def get_trade_calendar(self, trade_date: date) -> TradeCalendarDTO:
        return TradeCalendarDTO(trade_date=trade_date, calendar_is_open=True, next_trade_date=trade_date)

    async def get_active_confirmed_mainlines(self, trade_date=None, limit: int = 100):
        return []

    async def get_subject_board_stats(self, trade_date):
        return []

    async def get_stock_daily_bars_range(self, start_date, end_date, stock_ids=None):
        return [{"trade_date": end_date, "stock_id": "000001.SZ", "close_price": 1, "limit_up_price": 1, "limit_up": True}]

    async def get_subject_stock_daily_bars_range(self, start_date, end_date, stock_ids=None, subject_keys=None):
        return [{"trade_date": end_date, "stock_id": "000001.SZ", "subject_key": "robot"}]

    async def get_mainline_state_daily(self, trade_date, subject_keys):
        return []


class _GuardedReadPort(_MissingMarketContextReadPort):
    async def get_strong_stock_watch_view_rows(self, *args, **kwargs):
        raise AssertionError("Layer C read-model should not be called")

    async def get_strong_stock_watch_history(self, *args, **kwargs):
        raise AssertionError("Layer C read-model should not be called")

    async def get_strong_stock_watch_pool(self, *args, **kwargs):
        raise AssertionError("Layer C read-model should not be called")

    async def get_w2s_candidate_inputs(self, *args, **kwargs):
        raise AssertionError("D1 read-model should not be called")


class _FeatureReadPort(_GuardedReadPort):
    async def get_subject_event_stats(self, trade_date, subject_keys=None, lookback_days: int = 7):
        return [
            {
                "subject_key": "9064103",
                "theme_name": "AI光纤",
                "today_event_count": 2,
                "recent_event_count": 5,
                "distinct_event_days": 3,
                "key_event_count": 2,
                "sample_summaries": ["AI光纤事件驱动", "AI光纤产业链扩散"],
            }
        ]

    async def get_stock_position_judgement(self, trade_date, stock_ids=None):
        return [
            {
                "trade_date": trade_date,
                "stock_id": "603618.SH",
                "stock_name": "杭电股份",
                "position_label": "突破前高",
                "ma_alignment_status": "均线多头",
                "trend_strength_score": 72.0,
            }
        ]

    async def get_stock_pattern_judgement(self, trade_date, stock_ids=None):
        return [
            {
                "trade_date": trade_date,
                "stock_id": "603618.SH",
                "stock_name": "杭电股份",
                "pattern_labels": ["高量不破"],
                "volume_pattern_status": "expanding",
                "breakout_status": "resistance_broken",
                "pullback_status": "",
                "risk_pattern_status": "",
            }
        ]

    async def get_stock_daily_bars_range(self, start_date, end_date, stock_ids=None):
        bars = []
        base = end_date - timedelta(days=24)
        for idx in range(25):
            if idx < 15:
                close = Decimal("10.00")
                volume = Decimal("1000000") + Decimal(idx * 5000)
            elif idx < 20:
                close = Decimal("10.20")
                volume = Decimal("1200000") + Decimal(idx * 10000)
            else:
                close = Decimal("10.85") + Decimal((idx - 20) * 0.08)
                volume = Decimal("1800000") + Decimal(idx * 20000)
            bars.append(
                {
                    "trade_date": base + timedelta(days=idx),
                    "stock_id": "603618.SH",
                    "stock_name": "杭电股份",
                    "open_price": close,
                    "high_price": close * Decimal("1.01"),
                    "low_price": close * Decimal("0.99"),
                    "close_price": close,
                    "volume": volume,
                    "amount": volume * close,
                }
            )
        return bars

    async def get_subject_stock_daily_bars_range(self, start_date, end_date, stock_ids=None, subject_keys=None):
        return [
            {
                "trade_date": end_date,
                "stock_id": "603618.SH",
                "stock_name": "杭电股份",
                "subject_key": "9064103",
                "subject_name": "AI光纤",
                "open_price": Decimal("10.85"),
                "high_price": Decimal("11.17"),
                "low_price": Decimal("10.79"),
                "close_price": Decimal("11.17"),
                "pct_chg": Decimal("10.01"),
                "limit_up": True,
                "limit_up_price": Decimal("11.17"),
                "amount": Decimal("1800000000"),
                "is_leader": True,
                "rank_order": 1,
            }
        ]


@pytest.mark.asyncio
async def test_post_market_setup_fact_context_builder_fails_loud_when_market_context_missing() -> None:
    builder = PostMarketSetupFactContextBuilder(_MissingMarketContextReadPort())

    with pytest.raises(Exception, match="missing market_regime"):
        await builder.build(date(2026, 6, 4), source_doc={})


@pytest.mark.asyncio
async def test_post_market_setup_fact_context_builder_does_not_touch_layer_c_or_d1() -> None:
    class _HappyReadPort(_GuardedReadPort):
        pass

    builder = PostMarketSetupFactContextBuilder(_HappyReadPort())
    ctx = await builder.build(
        date(2026, 6, 4),
        source_doc={
            "market_regime_review": {"trade_mode": "no_trade", "allow_trade": False},
            "trading_principle": {"position_limit": 0.0},
            "strong_hotspot_subjects": [],
            "pressure_by_stock": {},
            "ma_pattern_by_stock": {},
        },
    )

    assert ctx.trade_date == "2026-06-04"
    assert ctx.watch_date == "2026-06-04"
    assert ctx.market_regime["trade_mode"] == "no_trade"


@pytest.mark.asyncio
async def test_post_market_setup_fact_context_builder_does_not_touch_strong_stock_watch_sources() -> None:
    class _StrongWatchGuardReadPort(_GuardedReadPort):
        pass

    builder = PostMarketSetupFactContextBuilder(_StrongWatchGuardReadPort())
    ctx = await builder.build(
        date(2026, 5, 26),
        source_doc={
            "market_regime_review": {"trade_mode": "normal", "allow_trade": True},
            "trading_principle": {"position_limit": Decimal("0.3")},
            "strong_hotspot_subjects": [
                {"subject_key": "9060250", "theme_name": "日本九大核心企业", "source": "topic_hotspot"},
            ],
            "pressure_by_stock": {},
            "ma_pattern_by_stock": {},
        },
    )

    assert ctx.trade_date == "2026-05-26"
    assert ctx.watch_date == "2026-05-26"
    assert ctx.subject_priority_rank["9060250"] >= 0


@pytest.mark.asyncio
async def test_post_market_setup_fact_context_builder_includes_authenticity_and_pattern_features() -> None:
    builder = PostMarketSetupFactContextBuilder(_FeatureReadPort())
    ctx = await builder.build(
        date(2026, 5, 6),
        source_doc={
            "market_regime_review": {"trade_mode": "normal", "allow_trade": True},
            "trading_principle": {"position_limit": Decimal("0.3")},
            "strong_hotspot_subjects": [
                {"subject_key": "9064103", "theme_name": "AI光纤", "source": "confirmed_mainline"},
            ],
            "stock_facts": [
                {
                    "trade_date": "2026-05-06",
                    "stock_id": "603618.SH",
                    "stock_name": "杭电股份",
                    "subject_key": "9064103",
                    "turnover_rate": Decimal("10.75"),
                }
            ],
            "pressure_by_stock": {},
            "ma_pattern_by_stock": {},
        },
    )

    assert "9064103" in ctx.subject_authenticity_by_subject
    assert ctx.subject_authenticity_by_subject["9064103"]["level"] in {"core", "direct", "related"}
    assert ctx.subject_authenticity_by_subject["9064103"]["score"] > 0
    assert "603618|9064103" in ctx.stock_subject_authenticity_by_pair
    assert ctx.stock_subject_authenticity_by_pair["603618|9064103"]["authenticity_scope"] == "stock_subject"
    assert ctx.stock_subject_authenticity_by_pair["603618|9064103"]["score"] > 0
    assert ctx.turnover_rate_by_stock["603618"] == Decimal("10.75")
    assert "603618" in ctx.kline_pattern_quality_by_stock or "603618.SH" in ctx.kline_pattern_quality_by_stock
    key = "603618" if "603618" in ctx.kline_pattern_quality_by_stock else "603618.SH"
    assert "has_golden_spider" in ctx.kline_pattern_quality_by_stock[key]
    assert ctx.kline_pattern_quality_by_stock[key]["level"] in {"golden", "near_golden", "unknown"}

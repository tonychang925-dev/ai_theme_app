from __future__ import annotations

from datetime import date, timedelta

import pytest

from stock_processing_service.application.services.event_theme_stock_authenticity_service import (
    EventThemeStockAuthenticityService,
)
from stock_processing_service.application.services.golden_spider_pattern_service import (
    GoldenSpiderPatternService,
)


class _AuthenticityReadPort:
    async def get_subject_event_stats(self, trade_date, subject_keys=None, lookback_days: int = 7):
        return [
            {
                "subject_key": "9064103",
                "theme_name": "AI光纤",
                "today_event_count": 2,
                "recent_event_count": 5,
                "distinct_event_days": 3,
                "key_event_count": 2,
                "sample_summaries": [
                    "AI光纤产业链政策推动",
                    "AI光纤订单持续落地",
                ],
            }
        ]


class _GoldenSpiderReadPort:
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
                "pattern_labels": ["高量不破", "放量突破"],
                "volume_pattern_status": "expanding",
                "breakout_status": "resistance_broken",
                "pullback_status": "",
                "risk_pattern_status": "",
            }
        ]


@pytest.mark.asyncio
async def test_event_theme_authenticity_prefers_core_event_driven_subject() -> None:
    service = EventThemeStockAuthenticityService(_AuthenticityReadPort())
    result = await service.build(
        trade_date=date(2026, 5, 6),
        subject_keys=["9064103"],
        subject_stock_rows=[
            {
                "trade_date": "2026-05-06",
                "subject_key": "9064103",
                "stock_id": "603618.SH",
                "stock_name": "杭电股份",
                "rank_order": 1,
                "is_leader": True,
                "pct_chg": 10.01,
                "limit_up": True,
            }
        ],
        subject_market_breadth={
            "9064103": {
                "subject_key": "9064103",
                "subject_limit_up_count": 3,
                "subject_strong_count": 7,
                "leader_pct_chg": 10.01,
                "member_count": 8,
                "leader_limit_up": True,
            }
        },
        active_subject_keys={"9064103"},
    )

    topic = result["9064103"]
    assert topic["level"] in {"core", "direct"}
    assert topic["score"] > 60
    assert topic["purity_score"] > 50
    assert topic["evidence_events"]
    assert topic["evidence_stock_facts"]
    assert topic["matched_theme_anchors"][0]["theme_name"] == "AI光纤"


@pytest.mark.asyncio
async def test_event_theme_authenticity_builds_stock_subject_scope() -> None:
    service = EventThemeStockAuthenticityService(_AuthenticityReadPort())
    result = await service.build_stock_subject_authenticity(
        trade_date=date(2026, 5, 6),
        subject_keys=["9064103"],
        subject_stock_rows=[
            {
                "trade_date": "2026-05-06",
                "subject_key": "9064103",
                "stock_id": "603618.SH",
                "stock_name": "杭电股份",
                "rank_order": 1,
                "is_leader": True,
                "pct_chg": 10.01,
                "limit_up": True,
            },
            {
                "trade_date": "2026-05-06",
                "subject_key": "9064103",
                "stock_id": "002XXX.SZ",
                "stock_name": "测试股份",
                "rank_order": 5,
                "is_leader": False,
                "pct_chg": 6.88,
                "limit_up": False,
            },
        ],
        subject_market_breadth={
            "9064103": {
                "subject_key": "9064103",
                "subject_limit_up_count": 3,
                "subject_strong_count": 7,
                "leader_pct_chg": 10.01,
                "member_count": 8,
                "leader_limit_up": True,
            }
        },
        active_subject_keys={"9064103"},
    )

    scoped = result["603618|9064103"]
    assert scoped["authenticity_scope"] == "stock_subject"
    assert scoped["stock_id"] == "603618"
    assert scoped["stock_subject_key"] == "603618|9064103"
    assert scoped["level"] in {"core", "direct", "related"}
    assert scoped["score"] > 0


@pytest.mark.asyncio
async def test_golden_spider_detector_uses_ma_cluster_and_volume_context() -> None:
    service = GoldenSpiderPatternService(_GoldenSpiderReadPort())
    bars = []
    start = date(2026, 4, 1)
    for idx in range(25):
        if idx < 15:
            close = 10.00
            volume = 1000000 + idx * 5000
        elif idx < 20:
            close = 10.20
            volume = 1200000 + idx * 10000
        else:
            close = 10.85 + (idx - 20) * 0.08
            volume = 1800000 + idx * 20000
        bars.append(
            {
                "trade_date": start + timedelta(days=idx),
                "stock_id": "603618.SH",
                "stock_name": "杭电股份",
                "open_price": close,
                "high_price": close * 1.01,
                "low_price": close * 0.99,
                "close_price": close,
                "volume": volume,
                "amount": volume * close,
            }
        )

    result = await service.build(
        trade_date=date(2026, 5, 6),
        stock_ids=["603618.SH"],
        stock_bars_by_stock={"603618.SH": bars},
    )

    item = result["603618.SH"]
    assert item["has_golden_spider"] is True
    assert item["score"] >= 68
    assert item["level"] == "golden"
    assert item["pattern_reasons"]
    assert item["pattern_reasons"][0] in {"pattern_label_hit", "price_above_ma_cluster", "ma5_ma10_ma20_bullish_alignment", "ma_cluster_converged"}


@pytest.mark.asyncio
async def test_golden_spider_missing_bars_is_unknown() -> None:
    service = GoldenSpiderPatternService(_GoldenSpiderReadPort())
    result = await service.build(
        trade_date=date(2026, 5, 6),
        stock_ids=["603618.SH"],
        stock_bars_by_stock={"603618.SH": []},
    )

    item = result["603618.SH"]
    assert item["has_golden_spider"] is False
    assert item["level"] == "unknown"
    assert item["score"] == 0.0
    assert item["pattern_reasons"] == ["missing_bars"]

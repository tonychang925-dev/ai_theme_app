"""Phase 4.5.5-RB — Workbench intelligence binding tests."""

from stock_processing_service.application.services.analyst_workbench.draft_context_builder import (
    DraftContextBuilder,
)
from scripts.generate_analyst_workbench import _build_cognition_cards_from_context


def test_tc_p455_rb_01_given_derived_context_when_build_then_themes_and_stocks_bound():
    derived = {
        "themes": [
            {
                "subject_key": "theme_pcb",
                "theme_name": "PCB印制电路板",
                "stage": "DIFFUSION",
                "role": "MAINLINE",
                "mainline_strength_score": 82,
                "evidence_refs": ["资金承接增强"],
            }
        ],
        "money_flows": [
            {
                "subject_key": "theme_pcb",
                "theme_name": "PCB印制电路板",
                "stock_code": "000001.SZ",
                "stock_name": "测试股份",
                "main_net_inflow": 120000000,
            }
        ],
        "strong_stocks": [
            {
                "stock_code": "000001.SZ",
                "stock_name": "测试股份",
                "subject_key": "theme_pcb",
                "theme_name": "PCB印制电路板",
                "role": "leader",
            }
        ],
        "market_state": {"theme_count": 1, "strong_stock_count": 1},
        "source_quality": 1.0,
        "missing_sources": [],
    }

    ctx = DraftContextBuilder().build(
        trade_date="2026-07-09",
        chart_json=[],
        emotion_json={"emotion_node": "REBOUND", "emotion_score": 39},
        derived_context=derived,
    )

    assert len(ctx.themes) == 1
    assert ctx.themes[0]["theme_name"] == "PCB印制电路板"
    assert ctx.themes[0]["stage"] == "DIFFUSION"
    assert ctx.themes[0]["capital"]["stock_count"] == 1
    assert len(ctx.strong_stocks) == 1
    assert ctx.strong_stocks[0]["stock_name"] == "测试股份"


def test_tc_p455_rb_03_draft_context_produces_review_document_snapshot_fields():
    charts = [
        {
            "chart_type": "active_capital",
            "data": {
                "active_amount_yi": 5058.28,
                "total_amount_yi": 10000,
                "limit_up_count": 75,
            },
        },
        {
            "chart_type": "emotion_momentum",
            "data": {"emotion_momentum_score": 1.5},
        },
        {
            "chart_type": "market_breadth",
            "data": {"limit_up_count": 75, "chain_board_count": 7, "up_ratio": 0.689},
        },
        {
            "chart_type": "relay_ecology",
            "data": {"max_board_height": 6, "promotion_1_to_2": 0.04},
        },
        {
            "chart_type": "institution_style",
            "data": {"directions": [{"name": "存储芯片", "state": "回流", "score": 80}]},
        },
        {
            "chart_type": "hot_money_style",
            "data": {"directions": [{"name": "人形机器人", "state": "活跃", "score": 72}]},
        },
        {
            "chart_type": "limitup_classification",
            "data": {
                "limit_up_count": 75,
                "categories": {
                    "storage": {
                        "theme_name": "存储芯片",
                        "count": 8,
                        "stocks": [{"code": "605178.SH", "name": "时空科技"}],
                    }
                },
            },
        },
    ]

    ctx = DraftContextBuilder().build(
        trade_date="2026-07-09",
        chart_json=charts,
        emotion_json={"emotion_node": "CHAOS", "emotion_score": 39},
        derived_context={"themes": [{"subject_key": "storage", "theme_name": "存储芯片"}]},
        trend_data={
            "breadth": [{"date": f"2026-07-{day:02d}", "limit_up": day} for day in range(1, 13)],
            "momentum": [{"date": f"2026-07-{day:02d}", "score": day / 10} for day in range(1, 13)],
            "capital": [{"date": f"2026-07-{day:02d}", "amount": day / 10} for day in range(1, 13)],
            "relay": [{"date": f"2026-07-{day:02d}", "max_height": day % 7} for day in range(1, 13)],
        },
    )

    payload = ctx.to_dict()
    assert payload["capital_state"]["active_amount"] == 5058.28
    assert payload["capital_state"]["institution"][0]["theme_name"] == "存储芯片"
    assert payload["capital_state"]["hot_money"][0]["theme_name"] == "人形机器人"
    assert len(payload["trend_data"]["breadth"]) == 12
    assert len(payload["trend_data"]["momentum"]) == 12
    assert len(payload["trend_data"]["capital"]) == 12
    assert len(payload["trend_data"]["relay"]) == 12
    assert payload["limit_up"]["total"] == 75
    assert payload["limit_up"]["categories"][0]["theme_name"] == "存储芯片"


def test_tc_p455_rb_04_draft_context_does_not_build_single_day_trend_from_charts():
    ctx = DraftContextBuilder().build(
        trade_date="2026-07-09",
        chart_json=[
            {
                "chart_type": "emotion_momentum",
                "data": {"emotion_momentum_score": 1.5},
            }
        ],
        emotion_json={"emotion_node": "CHAOS", "emotion_score": 39},
        derived_context={"themes": [{"subject_key": "storage", "theme_name": "存储芯片"}]},
    )

    assert ctx.trend_data == {}


def test_tc_p455_rb_02_given_context_themes_when_generate_draft_then_cognition_cards_not_empty():
    context = {
        "themes": [
            {
                "subject_key": "theme_pcb",
                "theme_name": "PCB印制电路板",
                "stage": "DIFFUSION",
                "role": "MAINLINE",
                "mainline_strength_score": 82,
                "evidence_refs": ["资金承接增强"],
                "capital": {
                    "stock_count": 1,
                    "top_stocks": [{"stock_code": "000001.SZ", "stock_name": "测试股份"}],
                },
            }
        ]
    }

    cards = _build_cognition_cards_from_context(context)

    assert len(cards) == 1
    assert cards[0]["subject_key"] == "theme_pcb"
    assert cards[0]["subject_name"] == "PCB印制电路板"
    assert cards[0]["state"] == "DIFFUSION"
    assert cards[0]["source"] == "draft_context.derived"
    assert cards[0]["top_stocks"][0]["stock_name"] == "测试股份"

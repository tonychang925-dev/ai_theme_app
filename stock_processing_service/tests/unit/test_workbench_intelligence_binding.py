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

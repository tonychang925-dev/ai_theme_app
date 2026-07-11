"""PR2.2 — Projection merge tests for Theme Structure and Stock Structure.

Case 1: AI/Analyst conflict resolution (AI=机器人, Analyst=PCB → final=PCB)
Case 2: Theme source missing (subject_key appears in cognition_cards but not theme_reviews)
Case 3: Stock dedup (same stock_code in strong_stock + pool_review → one entity)
"""

from __future__ import annotations

import pytest

from stock_processing_service.application.services.daily_review.projections.theme_structure import (
    project_theme_structure,
)
from stock_processing_service.application.services.daily_review.projections.stock_structure import (
    project_stock_structure,
)


# ═══ Case 1: AI/Analyst conflict resolution ═══

def test_analyst_override_wins_in_theme_structure():
    """Given AI says 机器人 and analyst says PCB,
    the stage_judgement final_value in analyst_view must be PCB."""
    engine_report = {
        "mainline_daily_states": [
            {
                "canonical_subject_key": "9018144",
                "mainline_name": "PCB印制电路板",
                "lifecycle_state": "fermentation",
                "mainline_alive": True,
                "mainline_trade_alive": True,
            }
        ],
        "theme_driver_events": [],
        "mainline_narrative": {},
    }

    snapshot_cards = [
        {
            "subject_id": "9018144",
            "subject_name": "PCB印制电路板",
            "attention_level": "CRITICAL",
            "attention_score": 85,
            "analyst_reviewed": True,
            "stage_judgement": {
                "field": "stage_judgement",
                "ai_value": "人形机器人延续主线",
                "analyst_value": "PCB成为资金承接方向",
                "final_value": "PCB成为资金承接方向",
                "override": True,
                "reason": "机器人高位分歧，资金切换PCB",
            },
        },
        {
            "subject_id": "9055500",
            "subject_name": "人形机器人",
            "attention_level": "HIGH",
            "attention_score": 70,
            "analyst_reviewed": False,
        },
    ]

    builder_theme_reviews = [
        {
            "subject_key": "9018144",
            "theme_name": "PCB印制电路板",
            "tier": "mainline",
            "cycle_stage": "fermentation",
        },
        {
            "subject_key": "9055500",
            "theme_name": "人形机器人",
            "tier": "secondary",
            "cycle_stage": "divergence",
        },
    ]

    result = project_theme_structure(
        engine_report=engine_report,
        snapshot_cognition_cards=snapshot_cards,
        builder_theme_reviews=builder_theme_reviews,
        builder_theme_capital_reviews=[],
    )

    themes = result["themes"]
    assert len(themes) >= 2, f"Expected >=2 themes, got {len(themes)}"

    # Find PCB theme
    pcb = _find_theme(themes, "9018144")
    assert pcb is not None, "PCB theme must exist in output"
    assert pcb["theme_name"] == "PCB印制电路板"
    assert pcb["role"] == "MAINLINE"

    # Analyst override must be present
    analyst_view = pcb["analyst_view"]
    assert "overrides" in analyst_view, "analyst_view must have overrides"
    overrides = analyst_view["overrides"]
    assert len(overrides) >= 1

    stage_override = _find_override(overrides, "stage_judgement")
    assert stage_override is not None
    assert stage_override["ai_value"] == "人形机器人延续主线"
    assert stage_override["analyst_value"] == "PCB成为资金承接方向"
    assert stage_override["final_value"] == "PCB成为资金承接方向"
    assert stage_override["reason"] == "机器人高位分歧，资金切换PCB"

    # Robot theme should exist but without override
    robot = _find_theme(themes, "9055500")
    assert robot is not None, "人形机器人 theme must exist in output"
    robot_view = robot["analyst_view"]
    assert not robot_view.get("overrides"), "robot theme should have no overrides"


# ═══ Case 2: Theme source missing ═══

def test_theme_appears_even_if_missing_from_theme_reviews():
    """A subject_key that exists in cognition_cards and driver_events
    but NOT in theme_reviews must still appear in the output."""
    engine_report = {
        "mainline_daily_states": [],
        "theme_driver_events": [
            {
                "subject_key": "9019999",
                "theme_name": "低空经济",
                "driver_events": [
                    {"event_id": "ev_001", "summary": "政策利好", "confidence": 0.8}
                ],
            }
        ],
        "mainline_narrative": {},
    }

    snapshot_cards = [
        {
            "subject_id": "9019999",
            "subject_name": "低空经济",
            "attention_level": "HIGH",
            "attention_score": 65,
            "analyst_reviewed": False,
        }
    ]

    # theme_reviews does NOT have 9019999
    builder_theme_reviews = [
        {"subject_key": "other_001", "theme_name": "Other Theme", "tier": "watch"}
    ]

    result = project_theme_structure(
        engine_report=engine_report,
        snapshot_cognition_cards=snapshot_cards,
        builder_theme_reviews=builder_theme_reviews,
        builder_theme_capital_reviews=[],
    )

    themes = result["themes"]

    # Low-altitude economy must appear despite missing from theme_reviews
    lae = _find_theme(themes, "9019999")
    assert lae is not None, (
        "低空经济 must appear in theme_structure even though "
        "it is missing from theme_reviews (present in cognition_cards + driver_events)"
    )
    assert lae["theme_name"] == "低空经济"
    assert len(lae["drivers"]) == 1
    assert lae["drivers"][0]["summary"] == "政策利好"


# ═══ Case 3: Stock dedup ═══

def test_same_stock_deduped_to_single_entity():
    """A stock that appears in both strong_stock_reviews and pool_reviews
    must be merged into a single entity."""
    engine_report = {
        "post_market_decision_v2": {
            "strong_stock_pool_reviews": [
                {
                    "stock_code": "002384.SZ",
                    "stock_id": "002384.SZ",
                    "stock_name": "东山精密",
                    "theme_name": "PCB印制电路板",
                    "role": "LEADER",
                }
            ]
        },
    }

    builder_strong_stocks = [
        {
            "stock_code": "002384.SZ",
            "stock_id": "002384.SZ",
            "stock_name": "东山精密",
            "subject_key": "9018144",
            "theme_name": "PCB印制电路板",
            "role": "LEADER",
            "role_label": "龙头",
            "composite_score": 70.26,
            "capital_score": 75.0,
            "structure_score": 81.0,
            "leading_score": 68.0,
            "purity_score": 62.0,
            "resilience_score": 92.0,
            "money_flow": {
                "main_net_inflow": 5000.0,
                "money_flow_tier": "strong",
                "role_enhanced": "leader",
            },
            "kline": {"position_label": "near_support", "pattern_summary": ""},
            "llm": {"judgement": "confirmed_leader", "reason": "换手板确认"},
            "rationale": "龙头确认",
        }
    ]

    result = project_stock_structure(
        engine_report=engine_report,
        builder_strong_stock_reviews=builder_strong_stocks,
    )

    stocks = result["stocks"]
    assert len(stocks) == 1, (
        f"Expected 1 unique stock entity, got {len(stocks)}. "
        f"Same stock_code should be deduped across sources."
    )

    stock = stocks[0]
    assert stock["stock_code"] == "002384.SZ"
    assert stock["stock_name"] == "东山精密"
    assert stock["today_role"] == "LEADER"
    assert stock["scores"]["composite"] == 70.26
    assert stock["capital"]["main_net_inflow"] == 5000.0

    # Groups must reference the stock
    assert "002384.SZ" in result["groups"]["leaders"]


# ═══ Edge: empty inputs ═══

def test_theme_structure_handles_empty_inputs():
    """Empty inputs should produce empty themes, not crash."""
    result = project_theme_structure(
        engine_report={"mainline_daily_states": [], "theme_driver_events": [], "mainline_narrative": {}},
        snapshot_cognition_cards=[],
        builder_theme_reviews=[],
        builder_theme_capital_reviews=[],
    )
    assert result["themes"] == []
    assert result["summary"]["mainline_narrative"] == ""


def test_stock_structure_handles_empty_inputs():
    """Empty inputs should produce empty stocks, not crash."""
    result = project_stock_structure(
        engine_report={"post_market_decision_v2": {}},
        builder_strong_stock_reviews=[],
    )
    assert result["stocks"] == []
    assert result["groups"]["leaders"] == []


# ── helpers ──


def _find_theme(themes: list[dict], subject_key: str) -> dict | None:
    for t in themes:
        if t.get("subject_key") == subject_key:
            return t
    return None


def _find_override(overrides: list[dict], field: str) -> dict | None:
    for o in overrides:
        if o.get("field") == field:
            return o
    return None

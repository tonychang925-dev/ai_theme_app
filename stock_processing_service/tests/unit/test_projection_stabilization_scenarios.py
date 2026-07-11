"""PR5 — Formal Review stabilization scenarios.

These tests cover five representative market/review shapes. They are not a
substitute for real five-trading-day observation, but they keep the frozen
Formal Review v1 schema stable while PR5 observation is running.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from stock_processing_service.application.services.daily_review.formal_review_projection_compiler import (
    FormalReviewProjectionCompiler,
)


SCENARIOS = [
    ("clear_mainline", "MAINLINE", "fermentation", "002384.SZ"),
    ("multi_theme_rotation", "SECONDARY", "rotation", "300814.SZ"),
    ("fade_day", "WATCH", "fade", "000887.SZ"),
    ("degraded_chart_data", "MAINLINE", "unknown", "688720.SH"),
    ("no_approved_snapshot", "WATCH", "divergence", "603688.SH"),
]


@pytest.mark.parametrize(("scenario", "expected_role", "stage", "stock_code"), SCENARIOS)
def test_formal_review_v1_stays_stable_across_pr5_scenarios(
    scenario: str,
    expected_role: str,
    stage: str,
    stock_code: str,
) -> None:
    snapshot = None if scenario == "no_approved_snapshot" else _snapshot_for(scenario)
    projection = FormalReviewProjectionCompiler().compile(
        trade_date="2026-07-09",
        engine_report=_engine_for(scenario, stage, stock_code),
        snapshot=snapshot,
        builder_theme_reviews=[
            {
                "subject_key": f"{scenario}_theme",
                "theme_name": _theme_name(scenario),
                "tier": "mainline" if expected_role == "MAINLINE" else "watch",
                "cycle_stage": stage,
            }
        ],
        builder_theme_capital_reviews=[
            {
                "subject_key": f"{scenario}_theme",
                "theme_name": _theme_name(scenario),
                "total_inflow": 120000000,
                "rank_order": 1,
            }
        ],
        builder_strong_stock_reviews=[
            {
                "stock_code": stock_code,
                "stock_name": _stock_name(stock_code),
                "subject_key": f"{scenario}_theme",
                "theme_name": _theme_name(scenario),
                "role": "LEADER" if expected_role == "MAINLINE" else "WATCH",
                "composite_score": 70.0,
            }
        ],
        builder_stock_capital_reviews=[
            {"stock_code": stock_code, "stock_name": _stock_name(stock_code), "main_net_inflow": 50000000}
        ],
        builder_money_flow_reviews=[
            {"stock_code": stock_code, "stock_name": _stock_name(stock_code), "money_flow_tier": "strong"}
        ],
        builder_watchlist_reviews=[
            {
                "stock_code": stock_code,
                "stock_name": _stock_name(stock_code),
                "subject_key": f"{scenario}_theme",
                "theme_name": _theme_name(scenario),
                "action": "观察确认",
            }
        ],
        builder_post_market_setup_plan={"items": []},
        builder_trading_principle={"main_strategy": "按确认信号执行", "forbidden_actions": ["不追高"]},
    ).to_dict()

    assert set(projection.keys()) == {"metadata", "formal_review", "evidence_appendix", "diagnostics"}
    formal = projection["formal_review"]
    assert set(formal.keys()) == {
        "version",
        "executive_summary",
        "market_state",
        "theme_structure",
        "stock_structure",
        "capital_evidence",
        "next_day_plan",
    }

    themes = formal["theme_structure"]["themes"]
    theme_keys = [row["subject_key"] for row in themes]
    assert len(theme_keys) == len(set(theme_keys))
    assert f"{scenario}_theme" in theme_keys

    stocks = formal["stock_structure"]["stocks"]
    stock_codes = [row["stock_code"] for row in stocks]
    assert len(stock_codes) == len(set(stock_codes))
    assert stock_code in stock_codes

    capital_stocks = formal["capital_evidence"]["stocks"]
    capital_stock = next(row for row in capital_stocks if row["stock_code"] == stock_code)
    assert capital_stock["capital"]["fact"]["main_net_inflow"] == 50000000
    assert capital_stock["capital"]["assessment"]["money_flow_tier"] == "strong"

    assert formal["next_day_plan"]["watch_stocks"][0]["stock_code"] == stock_code
    if scenario == "degraded_chart_data":
        assert formal["market_state"]["facts"]["up_count"] == 1200
        assert "active_amount_yi" not in formal["market_state"]["facts"]
    if scenario == "no_approved_snapshot":
        assert formal["market_state"]["emotion"]["emotion_node"] == ""


def _engine_for(scenario: str, stage: str, stock_code: str) -> dict:
    charts = [] if scenario == "degraded_chart_data" else [
        {"chart_type": "active_capital", "key_metrics": {"active_amount_yi": 5058}},
        {"chart_type": "relay_ecology", "key_metrics": {"max_board_height": 6, "promotion_1_to_2": 0.04}},
    ]
    return {
        "market_overview_review": {
            "up_count": 1200,
            "down_count": 3800,
            "limit_up_total": 36,
            "limit_down_total": 21,
            "total_amount": 18000000000000,
        },
        "market_regime_review": {"trade_mode": "observe", "allow_trade": False},
        "mainline_daily_states": [
            {
                "canonical_subject_key": f"{scenario}_theme",
                "mainline_name": _theme_name(scenario),
                "lifecycle_state": stage,
                "mainline_alive": scenario != "fade_day",
                "mainline_trade_alive": scenario == "clear_mainline",
            }
        ],
        "theme_driver_events": [
            {"subject_key": f"{scenario}_theme", "driver_events": [{"event_id": scenario, "summary": "场景驱动"}]}
        ],
        "limit_up_ladder": {"summary": "梯队检查", "board_rows": [{"board_count": 6}]},
        "new_high_summary": {"industry_summary": [{"industry_name": _theme_name(scenario)}]},
        "post_market_decision_v2": {"strong_stock_pool_reviews": [{"stock_code": stock_code, "stock_name": _stock_name(stock_code)}]},
        "evidence_layer_review": {"summary": "证据层可用", "diagnostics": {"stock_capital_count": 1}},
        "_scenario_chart_reviews": charts,
    }


def _snapshot_for(scenario: str) -> SimpleNamespace:
    chart_reviews = _engine_for(scenario, "fermentation", "002384.SZ").get("_scenario_chart_reviews") or []
    return SimpleNamespace(
        emotion_review={
            "emotion_node": "REBOUND" if scenario != "fade_day" else "FADE",
            "emotion_score": 39,
            "risk_level": "MEDIUM",
            "tomorrow_outlook": "等待确认",
            "tomorrow_watchpoints": ["观察主线承接"],
            "tomorrow_forbidden": ["不追高"],
        },
        narrative={"main_story": f"{_theme_name(scenario)} 场景复盘。"},
        playbook={},
        cognition_cards=[],
        chart_reviews=chart_reviews,
    )


def _theme_name(scenario: str) -> str:
    return {
        "clear_mainline": "PCB印制电路板",
        "multi_theme_rotation": "存储芯片",
        "fade_day": "机器人",
        "degraded_chart_data": "低空经济",
        "no_approved_snapshot": "AI光纤",
    }[scenario]


def _stock_name(stock_code: str) -> str:
    return {
        "002384.SZ": "东山精密",
        "300814.SZ": "中富电路",
        "000887.SZ": "中鼎股份",
        "688720.SH": "DR艾森股",
        "603688.SH": "石英股份",
    }[stock_code]

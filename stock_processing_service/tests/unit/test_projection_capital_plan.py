"""PR2.3 — Projection tests for Capital Evidence and Next Day Plan."""

from __future__ import annotations

from stock_processing_service.application.services.daily_review.projections.capital_evidence import (
    project_capital_evidence,
)
from stock_processing_service.application.services.daily_review.projections.next_day_plan import (
    project_next_day_plan,
)


def test_capital_evidence_merges_stock_sources_by_stock_code() -> None:
    """The same stock across capital/money-flow/seat/abnormal rows becomes one entity."""
    result = project_capital_evidence(
        engine_report={
            "evidence_layer_review": {"summary": "证据层整理完成", "diagnostics": {"money_flow_count": 1}},
            "seat_money_summary": {"summary": "机构净买", "institution_net_buy": 56000000},
        },
        builder_theme_capital_reviews=[
            {
                "subject_key": "9018144",
                "theme_name": "PCB印制电路板",
                "total_inflow": 120000000,
                "rank_order": 1,
            }
        ],
        builder_stock_capital_reviews=[
            {
                "stock_code": "002384.SZ",
                "stock_name": "东山精密",
                "subject_key": "9018144",
                "theme_name": "PCB印制电路板",
                "main_net_inflow": 50000000,
                "rank_order": 1,
            }
        ],
        builder_money_flow_reviews=[
            {
                "stock_id": "002384.SZ",
                "stock_name": "东山精密",
                "main_net_inflow": 52000000,
                "money_flow_tier": "strong",
                "role_enhanced": "leader",
            }
        ],
        builder_dragon_tiger_reviews=[
            {
                "stock_code": "002384.SZ",
                "stock_name": "东山精密",
                "net_buy": 30000000,
                "seat_type": "HOT_MONEY",
                "side_summary": "游资净买",
            }
        ],
        builder_abnormal_reviews=[
            {
                "stock_code": "002384.SZ",
                "stock_name": "东山精密",
                "abnormal_score": 88,
                "conclusion": "放量异动",
            }
        ],
    )

    assert result["market"]["summary"] == "证据层整理完成"
    assert result["themes"][0]["subject_key"] == "9018144"

    stocks = result["stocks"]
    assert len(stocks) == 1
    stock = stocks[0]
    assert stock["stock_code"] == "002384.SZ"
    assert stock["capital_flow"]["main_net_inflow"] == 50000000
    assert stock["capital_flow"]["money_flow_tier"] == "strong"
    assert stock["dragon_tiger"]["net_buy"] == 30000000
    assert stock["abnormal_signals"][0]["conclusion"] == "放量异动"
    assert set(stock["sources"]) == {
        "stock_capital_reviews",
        "money_flow_reviews",
        "dragon_tiger_reviews",
        "abnormal_reviews",
    }


def test_capital_evidence_keeps_seat_rows_without_stock_code_as_orphans() -> None:
    result = project_capital_evidence(
        engine_report={},
        builder_dragon_tiger_reviews=[
            {
                "stock_name": "席位聚合",
                "theme_name": "PCB印制电路板",
                "net_buy": 10000000,
                "seat_type": "INSTITUTION",
                "reason": "聚合席位无个股代码",
            }
        ],
    )

    assert result["stocks"] == []
    assert len(result["orphan_seats"]) == 1
    assert result["orphan_seats"][0]["stock_name"] == "席位聚合"


def test_next_day_plan_merges_watchlist_and_one_to_two_by_stock_code() -> None:
    result = project_next_day_plan(
        engine_report={},
        snapshot_emotion={
            "tomorrow_outlook": "反弹窗口，快进快出",
            "tomorrow_watchpoints": ["PCB承接是否延续"],
            "tomorrow_forbidden": ["不追高"],
        },
        snapshot_playbook={},
        builder_watchlist_reviews=[
            {
                "stock_code": "002384.SZ",
                "stock_name": "东山精密",
                "subject_key": "9018144",
                "theme_name": "PCB印制电路板",
                "category": "重点观察",
                "action": "观察竞价承接",
                "flags": ["竞价放量"],
                "priority": 1,
            }
        ],
        builder_post_market_setup_plan={
            "items": [
                {
                    "stock_id": "002384.SZ",
                    "stock_name": "东山精密",
                    "subject_key": "9018144",
                    "subject_name": "PCB印制电路板",
                    "tomorrow_plan": {
                        "confirmation_triggers": ["二板快速封单"],
                        "expected_behavior": "只做确认观察",
                    },
                    "invalidation_plan": ["高开回落"],
                }
            ]
        },
    )

    assert result["scenario"] == "反弹窗口，快进快出"
    assert result["confirmation_signals"] == ["PCB承接是否延续"]
    assert result["forbidden_actions"] == ["不追高"]

    stocks = result["watch_stocks"]
    assert len(stocks) == 1
    stock = stocks[0]
    assert stock["stock_code"] == "002384.SZ"
    assert set(stock["tags"]) == {"watchlist", "one_to_two"}
    assert "竞价放量" in stock["confirmation_signals"]
    assert "二板快速封单" in stock["confirmation_signals"]
    assert "高开回落" in stock["invalidation_signals"]

    assert result["watch_themes"][0]["subject_key"] == "9018144"
    assert result["watch_themes"][0]["stock_count"] == 1


def test_next_day_plan_uses_analyst_playbook_override_before_engine_plan() -> None:
    result = project_next_day_plan(
        engine_report={},
        snapshot_emotion={"tomorrow_outlook": "AI情绪计划"},
        snapshot_playbook={
            "scenario": {
                "ai_value": "AI情绪计划",
                "analyst_value": "分析师计划：只看PCB确认",
                "final_value": "分析师计划：只看PCB确认",
                "override": True,
            },
            "forbidden_actions": {
                "ai_value": ["追强势机器人"],
                "analyst_value": ["不追机器人高位"],
                "final_value": ["不追机器人高位"],
                "override": True,
            },
        },
        builder_trading_principle={"main_strategy": "空仓等待", "forbidden_actions": ["非主线追涨"]},
    )

    assert result["scenario"] == "分析师计划：只看PCB确认"
    assert result["forbidden_actions"] == ["不追机器人高位"]

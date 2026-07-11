"""PR3 — DailyReview Projection Diff golden baseline for 2026-07-09.

This test is intentionally semantic, not a raw JSON diff:

  - FACT fields must stay equal.
  - ENTITY key sets must not lose themes/stocks.
  - ASSESSMENT fields must honor analyst final_value.
  - PLAN fields must honor analyst final watch universe.
"""

from __future__ import annotations

from types import SimpleNamespace

from stock_processing_service.application.services.daily_review.formal_review_projection_compiler import (
    FormalReviewProjectionCompiler,
)


def test_projection_diff_20260709_preserves_facts_entities_and_analyst_plan() -> None:
    old = _daily_review_v2_20260709_sample()
    snapshot = _approved_snapshot_20260709_sample()

    projection = FormalReviewProjectionCompiler().compile(
        trade_date="2026-07-09",
        engine_report=old,
        snapshot=snapshot,
        snapshot_meta={
            "mode": "formal",
            "snapshot_hash": "hash_20260709_pcb",
            "approval_mode": "formal",
            "source_mode": "analyst_workbench",
            "composition_mode": "formal",
        },
        source_info={"data_mode": "daily_review_v2_first"},
        theme_name_map={
            "robot": "机器人",
            "pcb": "PCB印制电路板",
        },
        snapshot_version="daily_review_v2.2026-07-09.golden",
        builder_theme_reviews=old["theme_reviews"],
        builder_theme_capital_reviews=old["theme_capital_reviews"],
        builder_strong_stock_reviews=old["strong_stock_reviews"],
        builder_watchlist_reviews=old["watchlist_reviews"],
        builder_stock_capital_reviews=old["stock_capital_reviews"],
        builder_money_flow_reviews=old["money_flow_reviews"],
        builder_dragon_tiger_reviews=old["dragon_tiger_reviews"],
        builder_abnormal_reviews=old["abnormal_reviews"],
        builder_post_market_setup_plan=old["post_market_setup_plan"],
        builder_trading_principle=old["trading_principle"],
    ).to_dict()

    formal = projection["formal_review"]

    # FACT Diff: market facts are preserved exactly from their owner source.
    facts = formal["market_state"]["facts"]
    overview = old["market_overview_review"]
    assert facts["up_count"] == overview["up_count"]
    assert facts["down_count"] == overview["down_count"]
    assert facts["limit_up_total"] == overview["limit_up_total"]
    assert facts["limit_down_total"] == overview["limit_down_total"]
    assert facts["total_amount"] == overview["total_amount"]

    # ENTITY Diff: theme and today-stock identity sets are not lost.
    old_theme_keys = {row["subject_key"] for row in old["theme_reviews"]}
    new_theme_keys = {row["subject_key"] for row in formal["theme_structure"]["themes"]}
    assert old_theme_keys.issubset(new_theme_keys)

    old_stock_codes = {row["stock_code"] for row in old["strong_stock_reviews"]}
    new_stock_codes = {row["stock_code"] for row in formal["stock_structure"]["stocks"]}
    assert old_stock_codes == new_stock_codes

    # ASSESSMENT Diff: analyst final_value wins over AI robot view.
    pcb = _find_theme(formal["theme_structure"]["themes"], "pcb")
    assert pcb is not None
    stage_override = _find_override(pcb["analyst_view"]["overrides"], "stage_judgement")
    assert stage_override["ai_value"] == "人形机器人延续主线"
    assert stage_override["final_value"] == "PCB成为资金承接方向"

    # Capital FACT/ASSESSMENT separation: numeric flow is fact; interpretation is assessment.
    capital_stock = _find_stock(formal["capital_evidence"]["stocks"], "002384.SZ")
    assert capital_stock is not None
    assert capital_stock["capital"]["fact"]["main_net_inflow"] == 52000000
    assert capital_stock["capital"]["assessment"]["money_flow_tier"] == "strong"
    assert "money_flow_tier" not in capital_stock["capital"]["fact"]

    # PLAN Diff: analyst watch override removes the AI/legacy robot watch theme.
    next_plan = formal["next_day_plan"]
    assert [row["subject_key"] for row in next_plan["watch_themes"]] == ["pcb"]
    assert [row["stock_code"] for row in next_plan["watch_stocks"]] == ["002384.SZ"]
    assert next_plan["playbook"]["watch_themes"]["ai_value"][0]["subject_key"] == "robot"
    assert next_plan["playbook"]["watch_themes"]["final_value"][0]["subject_key"] == "pcb"


def _daily_review_v2_20260709_sample() -> dict:
    return {
        "market_overview_review": {
            "up_count": 2357,
            "down_count": 2642,
            "limit_up_total": 75,
            "limit_down_total": 29,
            "total_amount": 28925822000000,
        },
        "market_regime_review": {
            "broad_market_regime": "chaos",
            "short_term_sentiment": "rebound",
            "allow_trade": False,
            "trade_mode": "quick_rebound",
        },
        "market_summary": {"market_health_score": 56.88},
        "limit_up_ladder": {"summary": "最高6板，梯队有断层", "board_rows": [{"board_count": 6}]},
        "new_high_summary": {"industry_summary": [{"industry_name": "PCB"}]},
        "theme_reviews": [
            {"subject_key": "robot", "theme_name": "机器人", "tier": "secondary", "cycle_stage": "divergence"},
            {"subject_key": "pcb", "theme_name": "PCB印制电路板", "tier": "mainline", "cycle_stage": "fermentation"},
        ],
        "theme_capital_reviews": [
            {"subject_key": "pcb", "theme_name": "PCB印制电路板", "total_inflow": 120000000, "rank_order": 1},
        ],
        "mainline_daily_states": [
            {
                "canonical_subject_key": "pcb",
                "mainline_name": "PCB印制电路板",
                "lifecycle_state": "fermentation",
                "mainline_alive": True,
                "mainline_trade_alive": True,
            }
        ],
        "theme_driver_events": [
            {"subject_key": "pcb", "driver_events": [{"event_id": "ev_pcb", "summary": "资金切换PCB"}]},
        ],
        "strong_stock_reviews": [
            {
                "stock_code": "002384.SZ",
                "stock_name": "东山精密",
                "subject_key": "pcb",
                "theme_name": "PCB印制电路板",
                "role": "LEADER",
                "composite_score": 70.26,
                "money_flow": {"main_net_inflow": 52000000, "money_flow_tier": "strong"},
            },
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "role": "WATCH",
                "composite_score": 55.0,
            },
        ],
        "stock_capital_reviews": [
            {"stock_code": "002384.SZ", "stock_name": "东山精密", "main_net_inflow": 52000000, "rank_order": 1},
        ],
        "money_flow_reviews": [
            {
                "stock_code": "002384.SZ",
                "stock_name": "东山精密",
                "main_net_inflow": 52000000,
                "money_flow_tier": "strong",
                "role_enhanced": "leader",
            },
        ],
        "dragon_tiger_reviews": [
            {"stock_code": "002384.SZ", "stock_name": "东山精密", "net_buy": 30000000, "seat_type": "HOT_MONEY"},
        ],
        "abnormal_reviews": [
            {"stock_code": "002384.SZ", "stock_name": "东山精密", "abnormal_score": 88, "conclusion": "放量异动"},
        ],
        "watchlist_reviews": [
            {"stock_code": "002361.SZ", "stock_name": "神剑股份", "subject_key": "robot", "theme_name": "机器人"},
            {"stock_code": "002384.SZ", "stock_name": "东山精密", "subject_key": "pcb", "theme_name": "PCB印制电路板"},
        ],
        "post_market_setup_plan": {
            "items": [
                {
                    "stock_id": "002384.SZ",
                    "stock_name": "东山精密",
                    "subject_key": "pcb",
                    "subject_name": "PCB印制电路板",
                    "tomorrow_plan": {"confirmation_triggers": ["二板快速封单"]},
                }
            ]
        },
        "trading_principle": {"main_strategy": "空仓等待", "forbidden_actions": ["非主线追涨"]},
        "post_market_decision_v2": {"strong_stock_pool_reviews": []},
        "evidence_layer_review": {"summary": "证据层整理完成", "diagnostics": {"money_flow_count": 1}},
    }


def _approved_snapshot_20260709_sample() -> SimpleNamespace:
    return SimpleNamespace(
        emotion_review={
            "emotion_node": "REBOUND",
            "emotion_score": 39,
            "risk_level": "MEDIUM",
            "tomorrow_outlook": "反弹第1天，快进快出",
            "tomorrow_watchpoints": ["PCB承接是否延续"],
            "tomorrow_forbidden": ["不追高"],
        },
        narrative={"main_story": "机器人高位分歧，资金切换PCB。"},
        playbook={
            "watch_themes": {
                "ai_value": [{"subject_key": "robot", "theme_name": "机器人"}],
                "analyst_value": [{"subject_key": "pcb", "theme_name": "PCB印制电路板"}],
                "final_value": [{"subject_key": "pcb", "theme_name": "PCB印制电路板"}],
                "override": True,
            }
        },
        cognition_cards=[
            {
                "subject_id": "pcb",
                "subject_name": "PCB印制电路板",
                "attention_level": "CRITICAL",
                "stage_judgement": {
                    "field": "stage_judgement",
                    "ai_value": "人形机器人延续主线",
                    "analyst_value": "PCB成为资金承接方向",
                    "final_value": "PCB成为资金承接方向",
                    "override": True,
                    "reason": "机器人高位分歧，资金切换PCB",
                },
            }
        ],
        chart_reviews=[
            {"chart_type": "active_capital", "key_metrics": {"active_amount_yi": 5058, "total_amount_yi": 289258}},
            {"chart_type": "relay_ecology", "key_metrics": {"max_board_height": 6, "promotion_1_to_2": 0.043}},
        ],
    )


def _find_theme(rows: list[dict], subject_key: str) -> dict | None:
    return next((row for row in rows if row.get("subject_key") == subject_key), None)


def _find_stock(rows: list[dict], stock_code: str) -> dict | None:
    return next((row for row in rows if row.get("stock_code") == stock_code), None)


def _find_override(rows: list[dict], field: str) -> dict:
    return next(row for row in rows if row.get("field") == field)

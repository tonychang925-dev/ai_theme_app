from __future__ import annotations

from stock_processing_service.application.services.new_chain_post_market_report_builder import (
    NewChainPostMarketReportBuilder,
)


def test_new_chain_report_builder_emits_board_group_matrix() -> None:
    recap_doc = {
        "trade_date": "2026-06-17",
        "candidate_count_total": 0,
        "strong_watch_pool_written": 0,
        "strong_watch_history_count": 0,
        "report_context": {
            "market": {
                "trade_date": "2026-06-17",
                "market_total_amount": 3091800000000,
                "market_amount_change_pct": 0.88,
                "up_count": 1594,
                "down_count": 3549,
                "limit_up_count": 85,
                "limit_down_count": 1,
                "market_bias": "neutral_choppy",
                "action_bias": "mainline_core_only",
                "breadth_status": "偏弱",
                "short_term_sentiment_status": "attack",
                "relay_sentiment_status": "mainline_tradable",
                "intraday_fade_status": "mainline_tradable",
                "market_health_score": 72,
            },
            "stock_facts": [
                {
                    "subject_key": "pcb",
                    "theme_name": "PCB",
                    "stock_id": "301366",
                    "stock_name": "一博科技",
                    "board_count": 3,
                    "max_consecutive_limit_up_days": 3,
                    "limit_up_days": 3,
                    "role_label": "leader",
                    "in_layer_c": True,
                    "is_d1_candidate": True,
                    "trade_action": "主线参与",
                    "main_net_inflow": 31500000,
                    "pct_chg": 20.0,
                },
                {
                    "subject_key": "pcb",
                    "theme_name": "PCB",
                    "stock_id": "300903",
                    "stock_name": "科翔股份",
                    "board_count": 2,
                    "max_consecutive_limit_up_days": 2,
                    "limit_up_days": 2,
                    "role_label": "runner",
                    "trade_action": "主线分歧",
                    "main_net_inflow": 8900000,
                    "pct_chg": 14.0,
                },
                {
                    "subject_key": "glass",
                    "theme_name": "玻璃基板",
                    "stock_id": "002845",
                    "stock_name": "同兴达",
                    "board_count": 2,
                    "max_consecutive_limit_up_days": 2,
                    "limit_up_days": 2,
                    "role_label": "leader",
                    "trade_action": "轮动跟随",
                    "main_net_inflow": 7600000,
                    "pct_chg": 10.0,
                },
                {
                    "subject_key": "bank",
                    "theme_name": "银行",
                    "stock_id": "000001",
                    "stock_name": "平安银行",
                    "board_count": 1,
                    "max_consecutive_limit_up_days": 1,
                    "limit_up_days": 1,
                    "role_label": "observer",
                    "trade_action": "观察",
                    "main_net_inflow": 100000,
                    "pct_chg": 2.0,
                },
            ],
            "theme_name_map": {},
            "cycles": [],
            "theme_capital_flow": [],
            "money_flow": [],
        },
        "market_summary": {},
    }

    payload = NewChainPostMarketReportBuilder().build(recap_doc)

    matrix = payload["market_overview_review"]["theme_limitup_matrix"]
    assert len(matrix["columns"]) == 2
    assert payload["market_overview_review"]["diagnostics"]["visible_theme_count"] == 2
    assert matrix["columns"][0]["theme_name"] == "PCB"
    assert matrix["columns"][0]["board_groups"][0]["board_label"] == "4板"
    assert matrix["columns"][0]["board_groups"][1]["board_label"] == "3板"
    assert matrix["columns"][0]["board_groups"][1]["stocks"][0]["stock_name"] == "一博科技"
    assert matrix["columns"][0]["board_groups"][2]["stocks"][0]["stock_name"] == "科翔股份"


def test_new_chain_report_builder_board_groups_can_use_fact_fallback() -> None:
    recap_doc = {
        "trade_date": "2026-06-17",
        "candidate_count_total": 0,
        "strong_watch_pool_written": 0,
        "strong_watch_history_count": 0,
        "report_context": {
            "market": {
                "trade_date": "2026-06-17",
                "market_total_amount": 3091800000000,
                "market_amount_change_pct": 0.88,
                "up_count": 1594,
                "down_count": 3549,
                "limit_up_count": 85,
                "limit_down_count": 1,
                "market_bias": "neutral_choppy",
                "action_bias": "mainline_core_only",
                "breadth_status": "偏弱",
                "short_term_sentiment_status": "attack",
                "relay_sentiment_status": "mainline_tradable",
                "intraday_fade_status": "mainline_tradable",
                "market_health_score": 72,
            },
            "stock_facts": [
                    {
                        "subject_key": "pcb",
                        "theme_name": "PCB",
                        "stock_id": "301366",
                        "stock_name": "一博科技",
                        "max_consecutive_limit_up_days": 3,
                        "pct_chg": 20.0,
                        "role_label": "leader",
                        "in_layer_c": True,
                        "trade_action": "主线参与",
                    },
                    {
                        "subject_key": "pcb",
                        "theme_name": "PCB",
                        "stock_id": "300903",
                        "stock_name": "科翔股份",
                        "max_consecutive_limit_up_days": 2,
                        "pct_chg": 14.0,
                        "role_label": "runner",
                        "trade_action": "主线分歧",
                    },
            ],
            "theme_name_map": {},
            "cycles": [],
            "theme_capital_flow": [],
            "money_flow": [],
        },
        "market_summary": {},
    }

    payload = NewChainPostMarketReportBuilder().build(recap_doc)
    matrix = payload["market_overview_review"]["theme_limitup_matrix"]
    col = matrix["columns"][0]
    board_groups = {row["board_count"]: row for row in col["board_groups"]}
    assert board_groups[3]["stock_count"] == 1
    assert board_groups[2]["stock_count"] == 1


def test_new_chain_report_builder_prefers_canonical_theme_name_map() -> None:
    recap_doc = {
        "trade_date": "2026-06-17",
        "candidate_count_total": 0,
        "strong_watch_pool_written": 0,
        "strong_watch_history_count": 0,
        "report_context": {
            "market": {
                "trade_date": "2026-06-17",
                "market_total_amount": 3091800000000,
                "market_amount_change_pct": 0.88,
                "up_count": 1594,
                "down_count": 3549,
                "limit_up_count": 85,
                "limit_down_count": 1,
                "market_bias": "neutral_choppy",
                "action_bias": "mainline_core_only",
                "breadth_status": "偏弱",
                "short_term_sentiment_status": "attack",
                "relay_sentiment_status": "mainline_tradable",
                "intraday_fade_status": "mainline_tradable",
                "market_health_score": 72,
            },
            "stock_facts": [
                {
                    "subject_key": "pcb",
                    "theme_name": "__independent__",
                    "stock_id": "301366",
                    "stock_name": "一博科技",
                    "board_count": 3,
                    "max_consecutive_limit_up_days": 3,
                    "limit_up_days": 3,
                    "role_label": "leader",
                    "in_layer_c": True,
                    "is_d1_candidate": True,
                    "trade_action": "主线参与",
                    "main_net_inflow": 31500000,
                    "pct_chg": 20.0,
                }
            ],
            "theme_name_map": {"pcb": "PCB印制电路板"},
            "cycles": [],
            "theme_capital_flow": [],
            "money_flow": [],
        },
        "market_summary": {},
    }

    payload = NewChainPostMarketReportBuilder().build(recap_doc)

    matrix = payload["market_overview_review"]["theme_limitup_matrix"]
    assert matrix["columns"][0]["theme_name"] == "PCB印制电路板"

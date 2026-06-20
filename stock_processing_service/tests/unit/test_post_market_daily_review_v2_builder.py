from __future__ import annotations

from datetime import date

from stock_processing_service.application.services.post_market_daily_review_v2_builder import (
    MODULE_SECTION_HEADINGS,
    PostMarketDailyReviewV2Builder,
)


def test_daily_review_v2_builder_emits_complete_empty_contract() -> None:
    recap_doc = {
        "report": {
            "sections": [
                {"heading": "主线与支线", "items": ["A", "B"]},
                {"heading": "龙虎榜", "items": ["C"]},
            ]
        },
        "report_context": {
            "theme_capital_flow": [{"subject_key": "robot"}],
            "dragon_tiger": [{"stock_id": "000001.SZ"}],
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        recap_snapshot_version="recap.v1",
        snapshot_version="daily_review_v2.test",
    )

    assert payload["schema_version"] == "daily_review_v2"
    assert payload["trade_date"] == "2026-05-26"
    assert payload["data_mode"] == "daily_review_v2_first"
    assert payload["source"]["recap_snapshot_version"] == "recap.v1"
    assert payload["source"]["derived_data_status"] == "ready"

    for key in MODULE_SECTION_HEADINGS:
        assert key in payload
        if key not in {"theme_capital_reviews", "theme_reviews", "dragon_tiger_reviews"}:
            assert payload[key] == []

    coverage = payload["diagnostics"]["module_coverage"]
    assert set(coverage) == {"market_summary", *MODULE_SECTION_HEADINGS.keys()}
    assert coverage["theme_reviews"]["status"] == "partial"
    assert coverage["theme_reviews"]["source"] == "legacy_sections"
    assert coverage["theme_reviews"]["legacy_row_count"] == 2
    assert coverage["theme_capital_reviews"]["source"] == "none"
    assert payload["dragon_tiger_reviews"]
    assert coverage["dragon_tiger_reviews"]["status"] == "partial"
    assert coverage["dragon_tiger_reviews"]["legacy_row_count"] == 1
    assert coverage["dragon_tiger_reviews"]["source"] == "legacy_sections"
    assert payload["diagnostics"]["legacy_sections_available"] is True
    assert payload["diagnostics"]["source_tables"]["theme_capital_flow"] == 1
    assert payload["diagnostics"]["source_tables"]["dragon_tiger"] == 1


def test_daily_review_v2_builder_maps_theme_capital_from_report_context() -> None:
    recap_doc = {
        "report_context": {
            "theme_capital_flow": [
                {
                    "subject_key": "robot",
                    "theme_name": "机器人",
                    "main_net_inflow_sum": 880000000,
                    "leader_main_net_inflow": 160000000,
                    "top3_main_net_inflow": 320000000,
                    "positive_stock_count": 12,
                    "theme_structure": "放量突破",
                    "final_cycle_state": "rebound",
                    "trade_action": "观察分歧承接",
                    "rank": 1,
                    "mainline_strength_score": 72,
                }
            ]
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.theme.capital",
    )

    rows = payload["theme_capital_reviews"]
    assert len(rows) == 1
    assert rows[0]["subject_key"] == "robot"
    assert rows[0]["total_inflow"] == 880000000
    assert rows[0]["leader_inflow"] == 160000000
    coverage = payload["diagnostics"]["module_coverage"]["theme_capital_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_uses_strong_stock_rows_for_ladder_without_matrix() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "stock_id": "603186.SH",
                "stock_name": "华正新材",
                "subject_key": "pcb",
                "theme_name": "PCB",
                "board_count": 3,
                "role_label": "核心",
                "trade_action": "观察分歧承接",
                "reason": "光模块PCB",
            },
            {
                "stock_id": "600110.SH",
                "stock_name": "诺德股份",
                "subject_key": "pcb",
                "theme_name": "PCB",
                "board_count": 3,
                "role_label": "核心",
                "trade_action": "观察分歧承接",
                "reason": "铜箔",
            },
            {
                "stock_id": "688549.SH",
                "stock_name": "中巨芯",
                "subject_key": "semiconductor",
                "theme_name": "半导体设备",
                "board_count": 2,
                "role_label": "补涨",
                "trade_action": "等回踩",
                "reason": "六氟化钨",
            },
        ],
        "post_market_decision_v2": {
            "strong_stock_pool_reviews": [
                {
                    "stock_id": "603186.SH",
                    "stock_name": "华正新材",
                    "subject_key": "pcb",
                    "theme_name": "PCB",
                    "board_count": 3,
                }
            ]
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 17),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.strong.stock.fallback",
    )

    ladder = {row["board_count"]: row for row in payload["limit_up_ladder"]["board_rows"]}
    assert ladder[3]["stock_count"] >= 1
    assert ladder[2]["stock_count"] >= 1
    assert any(row["stock_count"] > 0 for row in ladder.values())
    assert payload["limit_up_ladder"]["theme_rows"]

    theme_events = payload["limit_up_theme_events"]
    assert theme_events["themes"]
    assert theme_events["themes"][0]["theme_name"] == "PCB"
    assert theme_events["themes"][0]["representative_stocks"]
    assert theme_events["diagnostics"]["candidate_count"] >= 3


def test_daily_review_v2_builder_normalizes_independent_placeholder_theme() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "stock_id": "000001.SZ",
                "stock_name": "平安银行",
                "subject_key": "__independent__",
                "theme_name": "__independent__",
                "board_count": 4,
                "role_label": "核心",
                "trade_action": "观察",
                "reason": "独立信号",
            },
            {
                "stock_id": "301366.SZ",
                "stock_name": "一博科技",
                "subject_key": "pcb",
                "theme_name": "PCB印制电路板",
                "board_count": 3,
                "role_label": "核心",
                "trade_action": "主线参与",
                "reason": "PCB",
            },
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 17),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.independent.normalize",
    )

    ladder_summary = payload["limit_up_ladder"]["summary"]
    theme_summary = payload["limit_up_theme_events"]["summary"]
    theme_rows = payload["limit_up_theme_events"]["themes"]
    assert "__independent__" not in ladder_summary
    assert "__independent__" not in theme_summary
    assert any(
        row["theme_name"] == "未归类"
        and any(stock["stock_name"] == "平安银行" for stock in row["representative_stocks"])
        for row in theme_rows
    )
    assert any(
        row["theme_name"] == "PCB印制电路板"
        and any(stock["stock_name"] == "一博科技" for stock in row["representative_stocks"])
        for row in theme_rows
    )


def test_daily_review_v2_builder_prefers_canonical_mainline_name_map() -> None:
    recap_doc = {
        "report_context": {
            "theme_name_map": {"pcb": "PCB印制电路板"},
            "theme_capital_flow": [
                {
                    "subject_key": "pcb",
                    "theme_name": "__independent__",
                    "main_net_inflow_sum": 880000000,
                    "leader_main_net_inflow": 160000000,
                    "top3_main_net_inflow": 320000000,
                    "positive_stock_count": 12,
                    "theme_structure": "放量突破",
                    "final_cycle_state": "rebound",
                    "trade_action": "观察分歧承接",
                    "rank": 1,
                    "mainline_strength_score": 72,
                }
            ],
            "market_overview_review": {
                "theme_limitup_matrix": {
                    "columns": [
                        {
                            "subject_key": "pcb",
                            "theme_name": "__independent__",
                            "limit_up_count": 8,
                            "active_mainline": True,
                            "lifecycle_state": "divergence",
                            "trade_action": "主线分歧",
                            "focus_stocks": [
                                {"stock_id": "1", "stock_name": "A", "board_count": 3, "role_label": "leader", "trade_action": "主线参与"},
                            ],
                        }
                    ],
                }
            },
        },
        "mainline_daily_states": [
            {
                "mainline_id": "pcb",
                "canonical_subject_key": "pcb",
                "mainline_name": "PCB印制电路板",
                "lifecycle_state": "divergence",
                "mainline_strength_score": 86.2,
                "fade_risk_score": 27.5,
                "strong_pool_count": 8,
                "d1_count": 3,
                "focus_count": 0,
                "action_advice": "观察分歧修复",
                "conclusion": "主线仍有资金，但处于分歧阶段",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 17),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.canonical.theme.map",
    )

    assert payload["theme_name_map"]["pcb"] == "PCB印制电路板"
    assert payload["theme_capital_reviews"][0]["theme_name"] == "PCB印制电路板"
    assert payload["theme_reviews"][0]["theme_name"] == "PCB印制电路板"
    assert payload["seat_money_summary"]["theme_rows"][0]["theme_name"] == "PCB印制电路板"


def test_daily_review_v2_builder_emits_limit_up_theme_matrix_from_single_contract() -> None:
    recap_doc = {
        "report_context": {
            "theme_name_map": {"pcb": "PCB印制电路板"},
        },
        "limit_up_ladder": {
            "board_rows": [
                {
                    "board_count": 4,
                    "stock_count": 1,
                    "stocks": [
                        {"stock_id": "1", "stock_name": "A", "subject_key": "pcb", "theme_name": "__independent__", "board_count": 4, "role_label": "leader", "trade_action": "主线参与"},
                        ],
                    },
                    {
                        "board_count": 1,
                    "stock_count": 1,
                    "stocks": [
                        {"stock_id": "2", "stock_name": "B", "subject_key": "pcb", "theme_name": "__independent__", "board_count": 1, "role_label": "watch", "trade_action": "观察"},
                        ],
                    },
                    {
                        "board_count": 2,
                        "stock_count": 1,
                        "stocks": [
                            {"stock_id": "3", "stock_name": "C", "subject_key": "__independent__", "theme_name": "未归类", "board_count": 2, "role_label": "watch", "trade_action": "观察"},
                        ],
                    },
                ]
            },
        "mainline_daily_states": [
            {
                "mainline_id": "pcb",
                "canonical_subject_key": "pcb",
                "mainline_name": "PCB印制电路板",
                "lifecycle_state": "divergence",
                "mainline_strength_score": 86.2,
                "fade_risk_score": 27.5,
                "strong_pool_count": 8,
                "d1_count": 3,
                "focus_count": 0,
                "focus_stocks": [
                    {"stock_id": "1", "stock_name": "A", "subject_key": "pcb", "theme_name": "PCB印制电路板"},
                    {"stock_id": "2", "stock_name": "B", "subject_key": "pcb", "theme_name": "PCB印制电路板"},
                ],
                "action_advice": "观察分歧修复",
                "conclusion": "主线仍有资金，但处于分歧阶段",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 18),
        recap_doc=recap_doc,
        theme_driver_events=[
            {
                "subject_key": "pcb",
                "theme_name": "PCB印制电路板",
                "driver_events": [
                    {
                        "event_id": "evt-1",
                        "summary": "Rubin BOM拆解",
                        "event_time": "2026-06-18",
                        "confidence": 0.93,
                        "match_reason": "主题命中",
                    }
                ],
            }
        ],
        snapshot_version="daily_review_v2.limit_up_theme_matrix",
    )

    matrix = payload["limit_up_theme_matrix"]
    assert matrix["diagnostics"]["source"] == "daily_review_v2.limit_up_theme_matrix"
    assert matrix["board_totals"]["4"] == 1
    assert matrix["board_totals"]["1"] == 1
    themes = [col["theme_name"] for col in matrix["columns"]]
    assert themes == ["PCB印制电路板"]
    assert "未归类" not in themes
    assert "9017093" not in themes
    col = matrix["columns"][0]
    assert col["board_groups"][0]["board_count"] == 4
    assert col["board_groups"][0]["stock_count"] == 1
    assert col["board_groups"][3]["board_count"] == 1
    assert col["board_groups"][3]["stock_count"] == 1
    assert col["catalyst_events"][0]["summary"] == "Rubin BOM拆解"
    assert matrix["diagnostics"]["unclassified_board_count"] == 1


def test_daily_review_v2_builder_keeps_unclassified_rows_in_diagnostics_but_counts_them() -> None:
    recap_doc = {
        "report_context": {
            "theme_name_map": {"pcb": "PCB印制电路板"},
        },
        "limit_up_ladder": {
            "board_rows": [
                {
                    "board_count": 4,
                    "board_label": "4板",
                    "stock_count": 1,
                    "stocks": [
                        {
                            "stock_id": "600353.SH",
                            "stock_name": "旭光电子",
                            "subject_key": "__independent__",
                            "theme_name": "未归类",
                            "board_count": 4,
                            "trade_action": "观察",
                        }
                    ],
                },
                {
                    "board_count": 1,
                    "board_label": "首板",
                    "stock_count": 1,
                    "stocks": [
                        {
                            "stock_id": "1",
                            "stock_name": "A",
                            "subject_key": "pcb",
                            "theme_name": "__independent__",
                            "board_count": 1,
                            "trade_action": "观察",
                        }
                    ],
                }
            ]
        },
        "mainline_daily_states": [
            {
                "mainline_id": "pcb",
                "canonical_subject_key": "pcb",
                "mainline_name": "PCB印制电路板",
                "lifecycle_state": "divergence",
                "mainline_strength_score": 86.2,
                "fade_risk_score": 27.5,
                "strong_pool_count": 8,
                "d1_count": 3,
                "focus_count": 0,
                "focus_stocks": [
                    {"stock_id": "1", "stock_name": "A", "subject_key": "pcb", "theme_name": "PCB印制电路板"},
                ],
                "action_advice": "观察分歧修复",
                "conclusion": "主线仍有资金，但处于分歧阶段",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 18),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.unclassified.diagnostics",
    )

    matrix = payload["limit_up_theme_matrix"]
    assert matrix["board_totals"]["4"] == 1
    assert matrix["diagnostics"]["unclassified_board_count"] == 1
    assert matrix["diagnostics"]["unclassified_board_rows"][0]["stock_name"] == "旭光电子"
    assert [col["theme_name"] for col in matrix["columns"]] == ["PCB印制电路板"]


def test_daily_review_v2_builder_records_duplicate_stock_rows_in_diagnostics() -> None:
    recap_doc = {
        "report_context": {
            "theme_name_map": {"pcb": "PCB印制电路板"},
        },
        "limit_up_ladder": {
            "board_rows": [
                {
                    "board_count": 4,
                    "stock_count": 1,
                    "stocks": [
                        {
                            "stock_id": "1",
                            "stock_name": "A",
                            "subject_key": "theme-a",
                            "theme_name": "主题A",
                            "board_count": 4,
                        }
                    ],
                }
            ]
        },
        "strong_stock_reviews": [
            {
                "stock_id": "1",
                "stock_name": "A",
                "subject_key": "theme-b",
                "theme_name": "主题B",
                "board_count": 4,
            }
        ],
        "mainline_daily_states": [
            {
                "mainline_id": "pcb",
                "canonical_subject_key": "pcb",
                "mainline_name": "PCB印制电路板",
                "lifecycle_state": "divergence",
                "mainline_strength_score": 86.2,
                "fade_risk_score": 27.5,
                "strong_pool_count": 8,
                "d1_count": 3,
                "focus_count": 0,
                "focus_stocks": [
                    {"stock_id": "1", "stock_name": "A", "subject_key": "pcb", "theme_name": "PCB印制电路板"},
                ],
                "action_advice": "观察分歧修复",
                "conclusion": "主线仍有资金，但处于分歧阶段",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 18),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.duplicate.diagnostics",
    )

    matrix = payload["limit_up_theme_matrix"]
    assert matrix["board_totals"]["4"] == 2
    assert matrix["diagnostics"]["duplicate_stock_count"] == 1
    assert matrix["diagnostics"]["duplicate_stock_rows"][0]["stock_name"] == "A"
    assert [col["theme_name"] for col in matrix["columns"]] == ["PCB印制电路板"]


def test_daily_review_v2_builder_uses_report_context_stock_facts_to_resolve_unclassified_stock() -> None:
    recap_doc = {
        "report_context": {
            "theme_name_map": {"pcb": "PCB印制电路板"},
            "stock_facts": [
                {
                    "stock_id": "600353.SH",
                    "stock_name": "旭光电子",
                    "subject_key": "pcb",
                    "theme_name": "PCB印制电路板",
                    "board_count": 4,
                }
            ],
        },
        "limit_up_ladder": {
            "board_rows": [
                {
                    "board_count": 4,
                    "stock_count": 1,
                    "stocks": [
                        {
                            "stock_id": "600353.SH",
                            "stock_name": "旭光电子",
                            "subject_key": "__independent__",
                            "theme_name": "未归类",
                            "board_count": 4,
                        }
                    ],
                }
            ]
        },
        "mainline_daily_states": [
            {
                "mainline_id": "pcb",
                "canonical_subject_key": "pcb",
                "mainline_name": "PCB印制电路板",
                "lifecycle_state": "divergence",
                "mainline_strength_score": 86.2,
                "fade_risk_score": 27.5,
                "strong_pool_count": 8,
                "d1_count": 3,
                "focus_count": 0,
                "focus_stocks": [
                    {"stock_id": "1", "stock_name": "A", "subject_key": "pcb", "theme_name": "PCB印制电路板"},
                ],
                "action_advice": "观察分歧修复",
                "conclusion": "主线仍有资金，但处于分歧阶段",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 18),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.stock_facts.resolve",
    )

    matrix = payload["limit_up_theme_matrix"]
    assert matrix["board_totals"]["4"] == 1
    assert matrix["diagnostics"]["unclassified_board_count"] == 0
    assert [col["theme_name"] for col in matrix["columns"]] == ["PCB印制电路板"]
    assert matrix["columns"][0]["board_groups"][0]["stock_count"] == 1
    assert matrix["columns"][0]["board_groups"][0]["stocks"][0]["stock_name"] == "旭光电子"


def test_daily_review_v2_builder_uses_capital_reviews_for_seat_money_fallback() -> None:
    recap_doc = {
        "capital_reviews": [
            {
                "stock_code": "600703.SH",
                "stock_name": "三安光电",
                "related_theme": "LED芯片",
                "seat_type": "INSTITUTION",
                "net_buy_amount": 1558608781.19,
                "ai_comment": "非ST、*ST和S证券连续三个交易日内收盘价格涨幅偏离值累计达到20%的证券",
            },
            {
                "stock_code": "300475.SZ",
                "stock_name": "香农芯创",
                "related_theme": "分销商",
                "seat_type": "INSTITUTION",
                "net_buy_amount": 885431494.64,
                "ai_comment": "日涨幅达到15%的前5只证券",
            },
            {
                "stock_code": "000725.SZ",
                "stock_name": "京东方A",
                "related_theme": "显示面板",
                "seat_type": "HOT_MONEY",
                "net_buy_amount": 532500000.0,
                "ai_comment": "日涨幅达到7%的前5只证券",
            },
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 17),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.seat.fallback",
    )

    seat = payload["seat_money_summary"]
    assert seat["summary"].startswith("机构关注")
    assert seat["institution_top_buys"]
    assert seat["hot_money_top_buys"]
    assert seat["theme_rows"]
    assert seat["diagnostics"]["source"] == "structured"


def test_daily_review_v2_builder_dedupes_stock_capital_reviews_by_stock_id() -> None:
    recap_doc = {
        "report_context": {
            "money_flow": [
                {
                    "stock_id": "300581",
                    "stock_name": "晨曦航空",
                    "subject_key": "air",
                    "theme_name": "军工",
                    "main_net_inflow": 12000000,
                    "pct_chg": 6.1,
                    "turnover_rate": 12.4,
                },
                {
                    "stock_id": "300581.SZ",
                    "stock_name": "晨曦航空",
                    "subject_key": "air2",
                    "theme_name": "导弹",
                    "main_net_inflow": 9000000,
                    "pct_chg": 6.1,
                    "turnover_rate": 12.4,
                },
                {
                    "stock_id": "688010",
                    "stock_name": "福光股份",
                    "subject_key": "optic",
                    "theme_name": "光学",
                    "main_net_inflow": 8000000,
                    "pct_chg": 3.2,
                    "turnover_rate": 9.1,
                },
            ]
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 12),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.stock.capital.dedupe",
    )

    rows = payload["stock_capital_reviews"]
    assert len(rows) == 2
    assert {row["stock_id"] for row in rows} == {"300581", "688010"}


def test_daily_review_v2_builder_prefers_report_context_money_flow_enhanced_for_stock_capital() -> None:
    recap_doc = {
        "stock_capital_reviews": [
            {
                "stock_id": "300581",
                "stock_name": "晨曦航空",
                "subject_key": "legacy_air",
                "theme_name": "陆军",
                "main_net_inflow": 0,
                "rank_overall": 1,
                "pct_chg": 0.0,
                "turnover_rate": 0.0,
            }
        ],
        "report_context": {
            "money_flow_enhanced": [
                {
                    "stock_id": "300581",
                    "stock_name": "晨曦航空",
                    "subject_key": "air",
                    "theme_name": "军工",
                    "main_net_inflow": 12000000,
                    "rank_overall": 1,
                    "pct_chg": 6.1,
                    "turnover_rate": 12.4,
                }
            ]
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 12),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.stock.capital.prefers_context",
    )

    rows = payload["stock_capital_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_id"] == "300581"
    assert rows[0]["subject_key"] == "air"
    assert rows[0]["main_net_inflow"] == 12000000


def test_daily_review_v2_builder_synthesizes_theme_reviews_from_capital_and_cycles() -> None:
    recap_doc = {
        "report_context": {
            "theme_capital_flow": [
                {
                    "subject_key": "robot",
                    "theme_name": "机器人",
                    "main_net_inflow_sum": 880000000,
                    "leader_main_net_inflow": 160000000,
                    "positive_stock_count": 12,
                    "theme_structure": "放量突破",
                    "trade_action": "观察分歧承接",
                    "rank": 1,
                }
            ],
            "cycles": [
                {
                    "subject_key": "robot",
                    "theme_name": "机器人",
                    "final_cycle_state": "rebound",
                    "mainline_strength_score": 72,
                    "final_mainline_alive": True,
                    "conclusion": "主线仍在",
                }
            ],
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.theme.synth",
    )

    rows = payload["theme_reviews"]
    assert len(rows) == 1
    assert rows[0]["subject_key"] == "robot"
    assert rows[0]["tier"] == "mainline"
    assert rows[0]["cycle_stage"] == "rebound"
    assert rows[0]["diagnostics"]["source"] == "report_context.cycles"
    coverage = payload["diagnostics"]["module_coverage"]["theme_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_blocks_theme_review_without_event_market_columns() -> None:
    recap_doc = {
        "theme_reviews": [
            {
                "subject_key": "robot",
                "theme_name": "机器人",
                "tier": "mainline",
                "total_inflow": 880000000,
                "cycle_stage": "rebound",
                "action_advice": "观察分歧承接",
            }
        ],
        "report": {"sections": [{"heading": "主线与支线", "items": ["legacy"]}]},
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.theme.columns.partial",
    )

    coverage = payload["diagnostics"]["module_coverage"]["theme_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "legacy_sections"
    assert "event_score" in coverage["column_missing_fields"]
    assert "market_score" in coverage["column_missing_fields"]


def test_daily_review_v2_builder_reports_missing_snapshot() -> None:
    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=None,
        snapshot_version="daily_review_v2.missing",
    )

    assert payload["schema_version"] == "daily_review_v2"
    assert payload["source"]["derived_data_status"] == "failed_precondition"
    assert payload["source"]["recap_generate_status"] == "failed"
    assert "post_market_recap_snapshot_missing" in payload["diagnostics"]["errors"]
    coverage = payload["diagnostics"]["module_coverage"]
    assert coverage["theme_reviews"]["source"] == "none"
    assert coverage["dragon_tiger_reviews"]["source"] == "none"


def test_daily_review_v2_builder_maps_ready_strong_stock_reviews() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "role": "leader",
                "watch_status": "formal",
                "watch_score": 88.5,
                "support_type": "ma20",
                "support_score": 0.72,
                "money_flow_tier": "strong",
                "role_enhanced": "leader",
                "main_net_inflow": 120000000,
                "position_label": "高位震荡",
                "pattern_labels": ["放量", "承接"],
                "rationale": "资金与结构共振",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.strong",
    )

    rows = payload["strong_stock_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "002361.SZ"
    assert rows[0]["role"] == "leader"
    assert rows[0]["role_label"] == "leader"
    assert rows[0]["money_flow"]["main_net_inflow"] == 120000000
    assert rows[0]["kline"]["pattern_labels"] == ["放量", "承接"]
    assert rows[0]["purity_score"] == 88.5
    assert rows[0]["leading_score"] == 85.0
    assert rows[0]["capital_score"] == 85.0
    assert rows[0]["structure_score"] == 0.72
    assert rows[0]["resilience_score"] == 0.72
    assert rows[0]["diagnostics"]["source"] == "recap_doc.strong_stock_reviews"
    assert "purity_score.watch_score_or_role" in rows[0]["diagnostics"]["fallback_used"]
    assert "leading_score.role" in rows[0]["diagnostics"]["fallback_used"]
    assert "capital_score.money_flow" in rows[0]["diagnostics"]["fallback_used"]

    coverage = payload["diagnostics"]["module_coverage"]["strong_stock_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["row_count"] == 1
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_maps_nested_support_and_kline_from_decision_reviews() -> None:
    recap_doc = {
        "strong_stock_decision_reviews": [
            {
                "stock_code": "605162.SH",
                "stock_name": "新中港",
                "subject_key": "9013416",
                "theme_name": "电力运营",
                "role": "watch",
                "role_label": "观察",
                "watch_status": "formal",
                "watch_score": 58.0,
                "support": {
                    "support_type": "previous_close",
                    "support_score": 9.0,
                    "support_reason": "已有支撑信号",
                },
                "kline": {
                    "position_label": "previous_close",
                    "pattern_labels": [],
                },
                "money_flow": {
                    "main_net_inflow": 442846311.0,
                    "money_flow_tier": "MEDIUM",
                    "role_enhanced": "watch",
                },
                "rationale": "观察承接",
            }
        ],
        "report_context": {
            "money_flow": [
                {
                    "stock_id": "605162",
                    "main_net_inflow": 442846311.0,
                    "money_flow_tier": "MEDIUM",
                    "role_enhanced": "watch",
                }
            ],
            "stock_facts": [
                {
                    "stock_id": "605162",
                    "position_label": "previous_close",
                    "pattern_labels": [],
                }
            ],
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 4),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.strong.nested.kline",
    )

    rows = payload["strong_stock_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "605162.SH"
    assert rows[0]["support"]["support_type"] == "previous_close"
    assert rows[0]["kline"]["position_label"] == "previous_close"
    assert rows[0]["kline"]["pattern_summary"] == "previous_close"
    assert rows[0]["diagnostics"]["source"] == "recap_doc.strong_stock_decision_reviews"
    coverage = payload["diagnostics"]["module_coverage"]["strong_stock_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_marks_strong_stock_missing_fields_partial() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "watch_status": "formal",
            }
        ],
        "report": {"sections": [{"heading": "强势股分层", "items": ["legacy"]}]},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.strong.partial",
    )

    coverage = payload["diagnostics"]["module_coverage"]["strong_stock_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "legacy_sections"
    assert coverage["row_count"] == 1
    assert "subject_key" in coverage["missing_fields"]
    assert "theme_name" in coverage["missing_fields"]
    assert "money_flow" in coverage["missing_fields"]
    assert "support" in coverage["missing_fields"]
    assert "kline" in coverage["missing_fields"]


def test_daily_review_v2_builder_marks_strong_stock_display_missing_partial() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "role": "leader",
                "watch_status": "formal",
                "watch_score": 88.5,
            }
        ],
        "report": {"sections": [{"heading": "强势股分层", "items": ["legacy"]}]},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.strong.display.partial",
    )

    coverage = payload["diagnostics"]["module_coverage"]["strong_stock_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "legacy_sections"
    assert "money_flow" in coverage["missing_fields"]
    assert "support" in coverage["missing_fields"]
    assert "kline" in coverage["missing_fields"]
    assert "capital_score" in coverage["missing_fields"]
    assert "rationale_or_llm_judgement" not in coverage["missing_fields"]


def test_daily_review_v2_builder_allows_strong_stock_kline_support_type_fallback() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "role": "leader",
                "watch_status": "formal",
                "watch_score": 88.5,
                "support_type": "ma20",
                "support_score": 0.72,
                "money_flow_tier": "strong",
                "role_enhanced": "leader",
                "main_net_inflow": 120000000,
                "rationale": "资金与承接共振",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.strong.kline.fallback",
    )

    row = payload["strong_stock_reviews"][0]
    assert row["kline"]["position_label"] == "ma20"
    assert row["kline"]["pattern_summary"] == "ma20"
    assert row["structure_score"] == 0.72
    assert row["resilience_score"] == 0.72
    assert "kline.support_type" in row["diagnostics"]["fallback_used"]
    assert "structure_score.support_or_composite" in row["diagnostics"]["fallback_used"]
    coverage = payload["diagnostics"]["module_coverage"]["strong_stock_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_does_not_block_strong_stock_ready_on_reject_display_fields() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "role": "leader",
                "watch_status": "formal",
                "watch_score": 88.5,
                "support_type": "ma20",
                "support_score": 0.72,
                "money_flow_tier": "strong",
                "role_enhanced": "leader",
                "main_net_inflow": 120000000,
                "rationale": "资金与承接共振",
            },
            {
                "stock_code": "000001.SZ",
                "stock_name": "淘汰样本",
                "subject_key": "robot",
                "theme_name": "机器人",
                "role": "reject",
                "watch_status": "reject",
            },
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.strong.reject.display",
    )

    coverage = payload["diagnostics"]["module_coverage"]["strong_stock_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_maps_promoted_pool_preview_to_strong_stock_reviews() -> None:
    recap_doc = {
        "promoted_pool_preview": [
            {
                "stock_id": "300302.SZ",
                "stock_name": "同有科技",
                "subject_key": "9015778",
                "subject_name": "存储芯片",
                "watch_status": "formal",
                "watch_score": "100.00",
                "support_type": "previous_low",
            }
        ],
        "report_context": {
            "money_flow": [
                {
                    "stock_id": "300302",
                    "stock_name": "同有科技",
                    "subject_key": "9015778",
                    "resolved_theme_name": "存储芯片",
                    "main_net_inflow": 88000000,
                    "money_flow_tier": "HIGH",
                    "role_enhanced": "龙头/资金共振",
                }
            ],
            "stock_facts": [
                {
                    "stock_id": "300302",
                    "position_label": "平台整理",
                    "pattern_labels": ["均线多头"],
                }
            ],
        },
        "report": {"sections": [{"heading": "强势股分层", "items": ["legacy"]}]},
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 25),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.strong.promoted",
    )

    rows = payload["strong_stock_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "300302.SZ"
    assert rows[0]["theme_name"] == "存储芯片"
    assert rows[0]["money_flow"]["main_net_inflow"] == 88000000
    assert rows[0]["diagnostics"]["source"] == "recap_doc.promoted_pool_preview"
    coverage = payload["diagnostics"]["module_coverage"]["strong_stock_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_maps_ready_watchlist_reviews() -> None:
    recap_doc = {
        "watchlist_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "category": "弱转强观察",
                "role_label": "观察",
                "stage": "rebound",
                "action": "观察竞价承接",
                "volume_ratio": 2.3,
                "pattern": "平台突破",
                "flags": ["放量"],
                "dragon_tiger_days": 1,
                "catalyst": "机器人催化",
                "abnormal_labels": ["倍量"],
                "priority": 1,
                "reason": "放量承接",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.watchlist",
    )

    rows = payload["watchlist_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "002361.SZ"
    assert rows[0]["category"] == "弱转强观察"
    assert rows[0]["role_label"] == "观察"
    assert rows[0]["priority"] == 1
    assert rows[0]["diagnostics"]["source"] == "recap_doc.watchlist_reviews"

    coverage = payload["diagnostics"]["module_coverage"]["watchlist_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["row_count"] == 1
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_marks_watchlist_display_missing_partial() -> None:
    recap_doc = {
        "watchlist_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "category": "重点观察",
            }
        ],
        "report": {"sections": [{"heading": "次日观察清单", "items": ["legacy"]}]},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.watchlist.partial",
    )

    coverage = payload["diagnostics"]["module_coverage"]["watchlist_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "legacy_sections"
    assert coverage["row_count"] == 1
    assert "reason" in coverage["missing_fields"]


def test_daily_review_v2_builder_synthesizes_watchlist_from_strong_stock_reviews() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "role": "leader",
                "role_enhanced": "leader",
                "watch_status": "formal",
                "watch_score": 88.5,
                "support_type": "ma20",
                "support_score": 0.72,
                "money_flow_tier": "strong",
                "main_net_inflow": 120000000,
                "rationale": "资金与承接共振",
            },
            {
                "stock_code": "000001.SZ",
                "stock_name": "淘汰样本",
                "subject_key": "robot",
                "theme_name": "机器人",
                "role": "reject",
            },
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.watchlist.synth",
    )

    rows = payload["watchlist_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "002361.SZ"
    assert rows[0]["diagnostics"]["source"] == "synthesized_from_strong_stock_reviews"
    assert "watchlist.from_strong_stock_reviews" in rows[0]["diagnostics"]["fallback_used"]
    assert "dragon_tiger_days.default_zero" in rows[0]["diagnostics"]["fallback_used"]
    coverage = payload["diagnostics"]["module_coverage"]["watchlist_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "none"
    assert "volume_ratio" in coverage["missing_fields"]
    assert "flags" in coverage["missing_fields"]


def test_daily_review_v2_builder_maps_promoted_pool_preview_to_watchlist_reviews() -> None:
    recap_doc = {
        "promoted_pool_preview": [
            {
                "stock_id": "300302.SZ",
                "stock_name": "同有科技",
                "subject_key": "9015778",
                "subject_name": "存储芯片",
                "watch_status": "formal",
                "watch_score": "100.00",
                "support_type": "previous_low",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 25),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.watchlist.promoted",
    )

    rows = payload["watchlist_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "300302.SZ"
    assert rows[0]["reason"] == "previous_low"
    assert rows[0]["diagnostics"]["source"] == "recap_doc.promoted_pool_preview"
    coverage = payload["diagnostics"]["module_coverage"]["watchlist_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "none"
    assert "volume_ratio" in coverage["missing_fields"]
    assert "flags" in coverage["missing_fields"]


def test_daily_review_v2_builder_dedupes_watchlist_promoted_pool_preview() -> None:
    recap_doc = {
        "promoted_pool_preview": [
            {
                "stock_id": "002579.SZ",
                "stock_name": "中京电子",
                "subject_key": "9015778",
                "subject_name": "存储芯片",
                "watch_status": "weakening",
                "prior7_limitup_days": 3,
                "recent_limit_up_count": 3,
            },
            {
                "stock_id": "002579.SZ",
                "stock_name": "中京电子",
                "subject_key": "9015778",
                "subject_name": "存储芯片",
                "watch_status": "weakening",
                "prior7_limitup_days": 3,
                "recent_limit_up_count": 3,
            },
            {
                "stock_id": "002957.SZ",
                "stock_name": "科瑞技术",
                "subject_key": "9013933",
                "subject_name": "共封装光学CPO",
                "watch_status": "weakening",
                "prior7_limitup_days": 3,
                "recent_limit_up_count": 3,
            },
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 29),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.watchlist.dedupe",
    )

    rows = payload["watchlist_reviews"]
    assert [row["stock_code"] for row in rows] == ["002579.SZ", "002957.SZ"]
    assert [row["priority"] for row in rows] == [1, 2]


def test_daily_review_v2_builder_maps_ready_stock_capital_reviews() -> None:
    recap_doc = {
        "stock_capital_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "main_net_inflow": 120000000,
                "rank_in_theme": 1,
                "rank_overall": 3,
                "pct_chg": 6.8,
                "turnover_rate": 18.2,
                "volume_ratio": 2.4,
                "is_leader": True,
                "flags": ["资金流入", "leader"],
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.stock.capital",
    )

    rows = payload["stock_capital_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "002361.SZ"
    assert rows[0]["main_net_inflow"] == 120000000
    assert rows[0]["rank_in_theme"] == 1
    assert rows[0]["is_leader"] is True
    assert rows[0]["diagnostics"]["source"] == "recap_doc.stock_capital_reviews"

    coverage = payload["diagnostics"]["module_coverage"]["stock_capital_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["row_count"] == 1
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_marks_stock_capital_display_missing_partial() -> None:
    recap_doc = {
        "stock_capital_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "rank_in_theme": 1,
            }
        ],
        "report": {"sections": [{"heading": "主线股票资金流入前20", "items": ["legacy"]}]},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.stock.capital.partial",
    )

    coverage = payload["diagnostics"]["module_coverage"]["stock_capital_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "legacy_sections"
    assert coverage["row_count"] == 1
    assert "main_net_inflow" in coverage["missing_fields"]
    assert "pct_chg_or_turnover_rate" in coverage["missing_fields"]
    assert "flags" not in coverage["missing_fields"]


def test_daily_review_v2_builder_allows_stock_capital_empty_flags_ready() -> None:
    recap_doc = {
        "stock_capital_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "main_net_inflow": 120000000,
                "rank_in_theme": 1,
                "pct_chg": 6.8,
                "flags": [],
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.stock.capital.flags.empty",
    )

    coverage = payload["diagnostics"]["module_coverage"]["stock_capital_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_maps_ready_abnormal_reviews() -> None:
    recap_doc = {
        "abnormal_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "abnormal_score": 91.2,
                "turnover_rate": 18.2,
                "volume_ratio": 2.4,
                "volume_vs_ma50": 3.1,
                "main_net_inflow": 120000000,
                "inflow_rank": 1,
                "money_flow_tier": "strong",
                "labels": ["倍量", "资金流入"],
                "conclusion": "资金与异动共振",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.abnormal",
    )

    rows = payload["abnormal_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "002361.SZ"
    assert rows[0]["abnormal_score"] == 91.2
    assert rows[0]["capital"]["main_net_inflow"] == 120000000
    assert rows[0]["labels"] == ["倍量", "资金流入"]
    assert rows[0]["diagnostics"]["source"] == "recap_doc.abnormal_reviews"

    coverage = payload["diagnostics"]["module_coverage"]["abnormal_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["row_count"] == 1
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_marks_abnormal_display_missing_partial() -> None:
    recap_doc = {
        "abnormal_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "abnormal_score": 91.2,
            }
        ],
        "report": {"sections": [{"heading": "当日异动股与资金行为", "items": ["legacy"]}]},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.abnormal.partial",
    )

    coverage = payload["diagnostics"]["module_coverage"]["abnormal_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "legacy_sections"
    assert coverage["row_count"] == 1
    assert "volume_or_turnover" in coverage["missing_fields"]
    assert "labels_or_conclusion" in coverage["missing_fields"]


def test_daily_review_v2_builder_maps_ready_money_flow_reviews() -> None:
    recap_doc = {
        "money_flow_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "main_net_inflow": 120000000,
                "money_flow_tier": "strong",
                "role_enhanced": "leader",
                "institution_signal": "净买",
                "hot_money_signal": "活跃",
                "dragon_tiger_signal": "上榜",
                "conclusion": "资金行为确认主线地位",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.money_flow",
    )

    rows = payload["money_flow_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "002361.SZ"
    assert rows[0]["main_net_inflow"] == 120000000
    assert rows[0]["role_enhanced"] == "leader"
    assert rows[0]["diagnostics"]["source"] == "recap_doc.money_flow_reviews"

    coverage = payload["diagnostics"]["module_coverage"]["money_flow_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["row_count"] == 1
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_prefers_resolved_theme_name_for_money_flow() -> None:
    recap_doc = {
        "report_context": {
            "money_flow": [
                {
                    "stock_id": "002361.SZ",
                    "stock_name": "神剑股份",
                    "subject_key": "9028660",
                    "theme_name": "9028660",
                    "resolved_theme_name": "机器人",
                    "main_net_inflow": 120000000,
                    "money_flow_tier": "strong",
                    "role_enhanced": "leader",
                    "conclusion": "资金行为确认主线地位",
                }
            ]
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.money_flow.resolved_theme",
    )

    rows = payload["money_flow_reviews"]
    assert rows[0]["subject_key"] == "9028660"
    assert rows[0]["theme_name"] == "机器人"


def test_daily_review_v2_builder_marks_money_flow_display_missing_partial() -> None:
    recap_doc = {
        "money_flow_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "theme_name": "机器人",
            }
        ],
        "report": {"sections": [{"heading": "资金行为增强", "items": ["legacy"]}]},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.money_flow.partial",
    )

    coverage = payload["diagnostics"]["module_coverage"]["money_flow_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "legacy_sections"
    assert coverage["row_count"] == 1
    assert "main_net_inflow_or_money_flow_tier" in coverage["missing_fields"]
    assert "role_or_signal" in coverage["missing_fields"]
    assert "conclusion" in coverage["missing_fields"]


def test_daily_review_v2_builder_uses_money_flow_conclusion_fallback() -> None:
    recap_doc = {
        "money_flow_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "main_net_inflow": 120000000,
                "money_flow_tier": "strong",
                "role_enhanced": "leader",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.money_flow.conclusion.fallback",
    )

    row = payload["money_flow_reviews"][0]
    assert row["conclusion"] == "leader / strong"
    assert row["kline"]["position_label"] == "leader"
    assert row["kline"]["pattern_summary"] == "strong"
    assert "conclusion" in row["diagnostics"]["fallback_used"]
    assert "kline.role_enhanced" in row["diagnostics"]["fallback_used"]
    assert "kline.money_flow_tier" in row["diagnostics"]["fallback_used"]
    coverage = payload["diagnostics"]["module_coverage"]["money_flow_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_formats_numeric_theme_kline_for_display() -> None:
    recap_doc = {
        "theme_reviews": [
            {
                "subject_key": "robot",
                "theme_name": "机器人",
                "tier": "mainline",
                "mainline_strength_score": 72,
                "capital_focus_score": 85.926,
                "cycle_stage": "rebound",
                "action_advice": "观察分歧承接",
                "total_inflow": 880000000,
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.theme.kline",
    )

    assert payload["theme_reviews"][0]["theme_kline"] == "强度 85.93"


def test_daily_review_v2_builder_maps_ready_dragon_tiger_reviews() -> None:
    recap_doc = {
        "dragon_tiger_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "subject_key": "robot",
                "theme_name": "机器人",
                "net_buy": 56000000,
                "buy_amount": 120000000,
                "sell_amount": 64000000,
                "seat_type": "HOT_MONEY",
                "hot_money_name": "一线游资",
                "institution_seat_count": 0,
                "reason": "日换手率达20%",
                "continuous_days": 1,
                "side_summary": "净买5600万",
                "seat_summary": ["一线游资净买"],
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.dragon_tiger",
    )

    rows = payload["dragon_tiger_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "002361.SZ"
    assert rows[0]["seat_type"] == "HOT_MONEY"
    assert rows[0]["net_buy"] == 56000000
    assert rows[0]["diagnostics"]["source"] == "recap_doc.dragon_tiger_reviews"

    coverage = payload["diagnostics"]["module_coverage"]["dragon_tiger_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["row_count"] == 1
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_maps_dragon_tiger_object_aliases_ready() -> None:
    recap_doc = {
        "report_context": {
            "dragon_tiger_object": [
                {
                    "stock_id": "301269.SZ",
                    "stock_name": "华大九天",
                    "subject_key": "chip",
                    "theme_name": "芯片",
                    "net_amount": -1481880725.53,
                    "billboard_buy_amount": 1678970326.23,
                    "billboard_sell_amount": 3160851051.76,
                    "institution_seat_count": 10,
                    "reason": "连续三个交易日内，涨幅偏离值累计达到30%的证券",
                    "seat_summary": "[\"机构专用 买入席位 净额 527716129.17\"]",
                }
            ]
        },
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.dragon_tiger.aliases",
    )

    rows = payload["dragon_tiger_reviews"]
    assert len(rows) == 1
    assert rows[0]["stock_code"] == "301269.SZ"
    assert rows[0]["net_buy"] == -1481880725.53
    assert rows[0]["buy_amount"] == 1678970326.23
    assert rows[0]["sell_amount"] == 3160851051.76
    assert rows[0]["seat_type"] == "INSTITUTION"
    assert rows[0]["seat_summary"] == ["机构专用 买入席位 净额 527716129.17"]
    assert rows[0]["diagnostics"]["source"] == "report_context.dragon_tiger_object"

    coverage = payload["diagnostics"]["module_coverage"]["dragon_tiger_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_does_not_use_money_flow_as_dragon_tiger_source() -> None:
    recap_doc = {
        "report_context": {
            "money_flow": [
                {
                    "stock_code": "002361.SZ",
                    "stock_name": "神剑股份",
                    "main_net_inflow": 120000000,
                    "money_flow_tier": "strong",
                }
            ]
        },
        "report": {"sections": [{"heading": "龙虎榜", "items": ["legacy"]}]},
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.dragon_tiger.no_money_flow",
    )

    assert payload["dragon_tiger_reviews"] == []
    coverage = payload["diagnostics"]["module_coverage"]["dragon_tiger_reviews"]
    assert coverage["status"] == "empty"
    assert coverage["source"] == "legacy_sections"
    assert coverage["legacy_row_count"] == 1


def test_daily_review_v2_builder_limits_dragon_tiger_rows_to_legacy_module_count() -> None:
    recap_doc = {
        "report_context": {
            "dragon_tiger": [
                {
                    "stock_id": f"00000{idx}.SZ",
                    "stock_name": f"龙虎股{idx}",
                    "net_amount": 1000000 * idx,
                    "billboard_buy_amount": 2000000 * idx,
                    "billboard_sell_amount": 1000000 * idx,
                    "institution_seat_count": 1,
                    "reason": "龙虎榜机构席位净买",
                }
                for idx in range(1, 4)
            ]
        },
        "report": {"sections": [{"heading": "龙虎榜", "items": ["legacy-a", "legacy-b"]}]},
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.dragon_tiger.legacy_count",
    )

    assert len(payload["dragon_tiger_reviews"]) == 2
    coverage = payload["diagnostics"]["module_coverage"]["dragon_tiger_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["row_count"] == 2
    assert coverage["legacy_row_count"] == 2


def test_daily_review_v2_builder_rejects_plain_capital_reviews_for_dragon_tiger() -> None:
    recap_doc = {
        "capital_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "main_net_inflow": 120000000,
                "related_theme": "机器人",
            }
        ],
        "report": {"sections": [{"heading": "龙虎榜", "items": ["legacy"]}]},
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.dragon_tiger.reject_capital",
    )

    assert payload["dragon_tiger_reviews"] == []
    coverage = payload["diagnostics"]["module_coverage"]["dragon_tiger_reviews"]
    assert coverage["status"] == "empty"
    assert coverage["source"] == "legacy_sections"
    assert coverage["legacy_row_count"] == 1


def test_daily_review_v2_builder_allows_explicit_capital_dragon_tiger_source() -> None:
    recap_doc = {
        "capital_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
                "net_buy_amount": 56000000,
                "seat_type": "HOT_MONEY",
                "ai_comment": "龙虎榜游资席位净买",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.dragon_tiger.capital_explicit",
    )

    rows = payload["dragon_tiger_reviews"]
    assert len(rows) == 1
    assert rows[0]["diagnostics"]["source"] == "recap_doc.capital_reviews"
    coverage = payload["diagnostics"]["module_coverage"]["dragon_tiger_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["missing_fields"] == []


def test_daily_review_v2_builder_marks_dragon_tiger_display_missing_partial() -> None:
    recap_doc = {
        "dragon_tiger_reviews": [
            {
                "stock_code": "002361.SZ",
                "stock_name": "神剑股份",
            }
        ],
        "report": {"sections": [{"heading": "龙虎榜", "items": ["legacy"]}]},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.dragon_tiger.partial",
    )

    coverage = payload["diagnostics"]["module_coverage"]["dragon_tiger_reviews"]
    assert coverage["status"] == "partial"
    assert coverage["source"] == "legacy_sections"
    assert coverage["row_count"] == 1
    assert "net_buy_or_buy_sell_amount" in coverage["missing_fields"]
    assert "seat_type_or_hot_money_or_institution" in coverage["missing_fields"]
    assert "reason_or_side_summary" in coverage["missing_fields"]


def test_daily_review_v2_builder_keeps_no_dragon_tiger_day_empty_not_failed() -> None:
    recap_doc = {
        "diagnostics": {"readiness": {"status": "ready", "skipped_reason": "no_dragon_tiger_day"}},
        "report": {"sections": [{"heading": "龙虎榜", "items": []}]},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.dragon_tiger.empty",
    )

    coverage = payload["diagnostics"]["module_coverage"]["dragon_tiger_reviews"]
    assert coverage["status"] == "empty"
    assert coverage["source"] == "none"
    assert coverage["row_count"] == 0
    assert "post_market_recap_snapshot_missing" not in payload["diagnostics"]["errors"]


def test_daily_review_v2_builder_passes_through_watchlists() -> None:
    recap_doc = {
        "watchlists": {
            "one_to_two": {
                "summary": {
                    "focus_count": 0,
                    "observe_only_count": 1,
                    "pending_review_only_count": 0,
                    "reject_count": 0,
                    "empty_is_valid": True,
                },
                "items": [],
                "diagnostics": {"empty_is_valid": True},
            }
        },
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 5, 26),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.watchlists.pass_through",
    )

    assert payload["watchlists"]["one_to_two"]["summary"]["observe_only_count"] == 1


def test_daily_review_v2_builder_emits_fixed_recap_modules() -> None:
    recap_doc = {
        "limit_up_ladder": {
            "board_rows": [
                {
                    "board_count": 3,
                    "stock_count": 1,
                    "stocks": [
                        {
                            "stock_id": "301366",
                            "stock_name": "一博科技",
                            "subject_key": "pcb",
                            "theme_name": "PCB",
                            "board_count": 3,
                            "role_label": "leader",
                            "trade_action": "主线参与",
                            "reason": "PCB",
                        }
                    ],
                },
                {
                    "board_count": 2,
                    "stock_count": 1,
                    "stocks": [
                        {
                            "stock_id": "300903",
                            "stock_name": "科翔股份",
                            "subject_key": "pcb",
                            "theme_name": "PCB",
                            "board_count": 2,
                            "role_label": "runner",
                            "trade_action": "主线分歧",
                            "reason": "PCB",
                        }
                    ],
                },
                {
                    "board_count": 2,
                    "stock_count": 1,
                    "stocks": [
                        {
                            "stock_id": "002845",
                            "stock_name": "同兴达",
                            "subject_key": "glass",
                            "theme_name": "玻璃基板",
                            "board_count": 2,
                            "role_label": "leader",
                            "trade_action": "轮动跟随",
                            "reason": "玻璃基板",
                        }
                    ],
                },
            ]
        },
        "theme_driver_events": [
            {
                "subject_key": "pcb",
                "theme_name": "PCB",
                "driver_events": [
                    {
                        "event_id": "evt-1",
                        "summary": "摩根士丹利拆解Rubin机架BOM，PCB价值增幅显著",
                        "confidence": 0.92,
                        "event_time": "2026-06-17",
                        "match_reason": "PCB",
                    }
                ],
            }
        ],
        "report_context": {
            "new_high_reviews": [
                {
                    "stock_id": "301366",
                    "stock_name": "一博科技",
                    "industry_name": "电子元件",
                    "is_new_high": True,
                    "pct_chg": 20.0,
                }
            ],
        },
        "dragon_tiger_reviews": [
            {
                "stock_code": "301366",
                "stock_name": "一博科技",
                "theme_name": "PCB",
                "seat_type": "INSTITUTION",
                "institution_seat_count": 3,
                "net_buy": 12000000,
            },
            {
                "stock_code": "300903",
                "stock_name": "科翔股份",
                "theme_name": "PCB",
                "seat_type": "HOT_MONEY",
                "hot_money_name": "章盟主",
                "net_buy": 18000000,
            },
        ],
        "money_flow_reviews": [
            {
                "stock_id": "301366",
                "stock_name": "一博科技",
                "theme_name": "PCB",
                "main_net_inflow": 12000000,
                "money_flow_tier": "强",
                "role_enhanced": "主线加速",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 17),
        recap_doc=recap_doc,
        theme_driver_events=recap_doc["theme_driver_events"],
        snapshot_version="daily_review_v2.fixed.modules",
    )

    assert payload["limit_up_ladder"]["board_rows"][0]["board_label"] == "4板"
    assert payload["limit_up_ladder"]["theme_rows"][0]["theme_name"] == "PCB"
    assert payload["limit_up_theme_events"]["rows"][0]["theme_name"] == "PCB"
    assert payload["limit_up_theme_events"]["rows"][0]["catalyst_events"][0]["summary"].startswith("摩根士丹利")
    assert payload["new_high_summary"]["today_count"] == 1
    assert payload["new_high_summary"]["industry_summary"][0]["industry_name"] == "电子元件"
    assert payload["seat_money_summary"]["cohesion"] in {"同向", "分歧"}
    assert payload["seat_money_summary"]["institution_top_buys"]
    assert len(payload["limit_up_theme_matrix"]["columns"]) == 2


def test_daily_review_v2_builder_builds_structured_seat_money_tables() -> None:
    recap_doc = {
        "report_context": {
            "hot_money_activities": [
                {
                    "hot_money_name": "紫阳东路",
                    "seat_name": "紫阳东路",
                    "stock_id": "000001",
                    "stock_name": "平安银行",
                    "subject_key": "bank",
                    "theme_name": "银行",
                    "side": "买入",
                    "buy_amount": 36700000,
                    "sell_amount": 0,
                    "net_amount": 36700000,
                    "reason": "机构席位观察",
                    "rank_order": 1,
                    "is_theme_leader": True,
                    "style_tags": ["接力"],
                },
                {
                    "hot_money_name": "紫阳东路",
                    "seat_name": "紫阳东路",
                    "stock_id": "600000",
                    "stock_name": "浦发银行",
                    "subject_key": "bank",
                    "theme_name": "银行",
                    "side": "卖出",
                    "buy_amount": 0,
                    "sell_amount": 32800000,
                    "net_amount": -32800000,
                    "reason": "机构席位观察",
                    "rank_order": 2,
                    "is_theme_leader": False,
                    "style_tags": ["接力"],
                },
            ],
        },
        "dragon_tiger_reviews": [
            {
                "stock_code": "688766",
                "stock_name": "普冉股份",
                "theme_name": "存储芯片",
                "seat_type": "INSTITUTION",
                "institution_seat_count": 3,
                "buy_amount": 989430000,
                "sell_amount": 376270000,
                "net_buy": 613160000,
                "seat_summary": [
                    {
                        "seat_name": "机构专用",
                        "side": "0",
                        "side_label": "买入席位",
                        "buy_amount": 560000000,
                        "sell_amount": 120000000,
                        "net_buy": 440000000,
                    },
                    {
                        "seat_name": "机构专用(二)",
                        "side": "1",
                        "side_label": "卖出席位",
                        "buy_amount": 180000000,
                        "sell_amount": 220000000,
                        "net_buy": -40000000,
                    },
                ],
            }
        ],
        "money_flow_reviews": [
            {
                "stock_id": "688766",
                "stock_name": "普冉股份",
                "theme_name": "存储芯片",
                "main_net_inflow": 12000000,
                "money_flow_tier": "强",
                "role_enhanced": "主线加速",
            }
        ],
        "diagnostics": {"readiness": {"status": "ready"}},
    }

    payload = PostMarketDailyReviewV2Builder().build(
        trade_date=date(2026, 6, 18),
        recap_doc=recap_doc,
        snapshot_version="daily_review_v2.seat_tables",
    )

    seat = payload["seat_money_summary"]
    assert seat["summary"].startswith("机构关注")
    assert seat["institution_buy_rows"][0]["stock_name"] == "普冉股份"
    assert seat["institution_buy_rows"][0]["buy_seat_count"] == 1
    assert seat["institution_buy_rows"][0]["seat_summary"][0]["seat_name"] == "机构专用"
    assert seat["hot_money_buy_rows"][0]["hot_money_name"] == "紫阳东路"
    assert seat["hot_money_buy_rows"][0]["buy_entries"][0]["stock_name"] == "平安银行"
    assert seat["hot_money_sell_rows"][0]["sell_entries"][0]["stock_name"] == "浦发银行"

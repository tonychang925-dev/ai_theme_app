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
    assert rows[0]["diagnostics"]["source"] == "recap_doc.strong_stock_reviews"
    assert "purity_score.watch_score_or_role" in rows[0]["diagnostics"]["fallback_used"]
    assert "leading_score.role" in rows[0]["diagnostics"]["fallback_used"]
    assert "capital_score.money_flow" in rows[0]["diagnostics"]["fallback_used"]

    coverage = payload["diagnostics"]["module_coverage"]["strong_stock_reviews"]
    assert coverage["status"] == "ready"
    assert coverage["source"] == "structured"
    assert coverage["row_count"] == 1
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
    assert "kline.support_type" in row["diagnostics"]["fallback_used"]
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
    assert "volume_ratio" in coverage["missing_fields"]
    assert "labels" in coverage["missing_fields"]
    assert "main_net_inflow_or_money_flow_tier" in coverage["missing_fields"]


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

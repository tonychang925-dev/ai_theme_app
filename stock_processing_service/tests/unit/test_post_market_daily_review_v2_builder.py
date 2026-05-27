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
        assert payload[key] == []

    coverage = payload["diagnostics"]["module_coverage"]
    assert set(coverage) == {"market_summary", *MODULE_SECTION_HEADINGS.keys()}
    assert coverage["theme_reviews"]["status"] == "empty"
    assert coverage["theme_reviews"]["source"] == "legacy_sections"
    assert coverage["theme_reviews"]["legacy_row_count"] == 2
    assert coverage["theme_capital_reviews"]["source"] == "none"
    assert coverage["dragon_tiger_reviews"]["legacy_row_count"] == 1
    assert coverage["dragon_tiger_reviews"]["source"] == "legacy_sections"
    assert payload["diagnostics"]["legacy_sections_available"] is True
    assert payload["diagnostics"]["source_tables"]["theme_capital_flow"] == 1
    assert payload["diagnostics"]["source_tables"]["dragon_tiger"] == 1


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
    assert rows[0]["diagnostics"]["source"] == "recap_doc.strong_stock_reviews"
    assert rows[0]["diagnostics"]["fallback_used"] == []

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
    assert "rationale_or_llm_judgement" not in coverage["missing_fields"]


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
    assert "flags" in coverage["missing_fields"]


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
    assert "turnover_rate_or_volume_ratio" in coverage["missing_fields"]
    assert "labels_or_conclusion" in coverage["missing_fields"]
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

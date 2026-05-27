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

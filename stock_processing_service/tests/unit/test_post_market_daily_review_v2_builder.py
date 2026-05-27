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

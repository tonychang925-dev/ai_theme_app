from __future__ import annotations

from scripts.check_one_to_two_setup_plan_audit import build_audit_report


def test_one_to_two_audit_report_passes_for_valid_persisted_contract() -> None:
    plan_rows = [
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "__SUMMARY__",
            "subject_key": "__SUMMARY__",
            "decision": "pending_review_only",
            "summary": "{\"focus_count\": 1, \"observe_only_count\": 1, \"pending_review_only_count\": 0, \"reject_count\": 1}",
            "diagnostics": "{\"empty_is_valid\": true}",
        },
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600367.SH",
            "subject_key": "mainline_ai",
            "decision": "focus",
        },
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600403.SH",
            "subject_key": "mainline_ai",
            "decision": "observe_only",
        },
    ]
    feature_rows = [
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600367.SH",
            "subject_key": "mainline_ai",
            "decision": "focus",
            "veto_reasons": [],
        },
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600403.SH",
            "subject_key": "mainline_ai",
            "decision": "observe_only",
            "veto_reasons": [],
        },
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "000001.SZ",
            "subject_key": "robot",
            "decision": "reject",
            "veto_reasons": ["非市场主线"],
        },
    ]

    report = build_audit_report(plan_rows, feature_rows, trade_date="2026-06-04")

    assert report["ok"] is True
    assert report["contract"]["summary_unique"] is True
    assert report["contract"]["plan_item_count_matches_summary"] is True
    assert report["contract"]["candidate_feature_covers_plan_items"] is True
    assert report["contract"]["candidate_feature_no_summary"] is True
    assert report["contract"]["candidate_feature_setup_type_consistent"] is True
    assert report["contract"]["reject_audit_complete"] is True
    assert report["contract"]["no_buy_signal"] is True


def test_one_to_two_audit_report_fails_when_reject_missing_veto_reasons() -> None:
    plan_rows = [
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "__SUMMARY__",
            "subject_key": "__SUMMARY__",
            "decision": "pending_review_only",
            "summary": "{\"focus_count\": 0, \"observe_only_count\": 0, \"pending_review_only_count\": 0, \"reject_count\": 1}",
            "diagnostics": "{\"empty_is_valid\": true}",
        }
    ]
    feature_rows = [
        {
            "trade_date": "2026-06-04",
            "watch_date": "2026-06-05",
            "setup_type": "one_to_two",
            "stock_id": "600367.SH",
            "subject_key": "mainline_ai",
            "decision": "reject",
            "veto_reasons": [],
        }
    ]

    report = build_audit_report(plan_rows, feature_rows, trade_date="2026-06-04")

    assert report["ok"] is False
    assert report["contract"]["reject_audit_complete"] is False
    assert report["errors"]

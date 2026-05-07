from __future__ import annotations

from stock_processing_service.application.replay.candidate_miss_report import CandidateMissReportBuilder


def test_candidate_miss_uses_full_input_stock_ids_when_preview_is_truncated() -> None:
    report = CandidateMissReportBuilder().build(
        trade_date="2026-04-15",
        stock_id="605060.SH",
        recap_doc={
            "strong_watch_input_7d_stock_ids": ["605060.SH"],
            "candidate_count": 12,
            "observe_candidates_count": 10,
        },
        top_candidates=[],
        observe_candidates=[],
        promoted_pool=[],
        strong_watch_input=[],
        best_row=None,
    ).to_dict()

    assert report["presence"]["in_pool"] is True
    assert report["presence"]["in_refreshed"] is True
    assert report["selection"]["not_selected_reason"] == "in_input_but_not_promoted"


def test_candidate_miss_uses_full_promoted_stock_ids_when_preview_is_truncated() -> None:
    report = CandidateMissReportBuilder().build(
        trade_date="2026-04-15",
        stock_id="605060.SH",
        recap_doc={
            "strong_watch_input_7d_stock_ids": ["605060.SH"],
            "promoted_pool_stock_ids": ["605060.SH"],
            "candidate_count": 12,
            "observe_candidates_count": 10,
        },
        top_candidates=[],
        observe_candidates=[],
        promoted_pool=[],
        strong_watch_input=[],
        best_row=None,
    ).to_dict()

    assert report["presence"]["in_promoted_pool"] is True
    assert report["selection"]["not_selected_reason"] == "in_promoted_but_not_candidate"


def test_candidate_miss_reports_observe_rank_outside_output_from_candidate_diagnostics() -> None:
    report = CandidateMissReportBuilder().build(
        trade_date="2026-04-15",
        stock_id="605060.SH",
        recap_doc={
            "strong_watch_input_7d_stock_ids": ["605060.SH"],
            "promoted_pool_stock_ids": ["605060.SH"],
            "candidate_count_observe": 37,
        },
        top_candidates=[],
        observe_candidates=[],
        promoted_pool=[],
        strong_watch_input=[],
        best_row={
            "stock_id": "605060.SH",
            "candidate_level": "observe_only",
            "support_type": "prev_low_support",
            "candidate_rank": 73,
        },
    ).to_dict()

    assert report["d_layer_trace"]["candidate_row_created"] is True
    assert report["ranking"]["observe_rank"] == 73
    assert report["selection"]["not_selected_reason"] == "observe_rank_gt_observe_top_n"

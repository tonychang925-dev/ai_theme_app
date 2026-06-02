from theme_service.tools.build_product_runtime_daily_quality_report import (
    _quality_watch_metrics,
    _hard_negative_subject_rows,
    _watchlist_subject_rows,
    _write_quality_report,
)
import json

from datetime import date


def test_quality_watch_metrics_counts_direct_hits_and_watchlist_residuals():
    details = [
        {"event_id": 1, "subject_key": "9054404", "match_reason": "direct_theme_name_hit", "runtime_source": "v1_fallback"},
        {"event_id": 1, "subject_key": "9012396", "match_reason": "direct_theme_name_hit", "runtime_source": "v2_accepted"},
        {"event_id": 2, "subject_key": "9043698", "match_reason": "profile_hit", "runtime_source": "v2_accepted"},
        {"event_id": 3, "subject_key": "9010250", "match_reason": "direct_theme_name_hit", "runtime_source": "v1_fallback"},
        {"event_id": 3, "subject_key": "9011981", "match_reason": "direct_theme_name_hit", "runtime_source": "v1_fallback"},
    ]
    candidates = [
        {"event_id": 1, "subject_key": "9054404", "match_reason": "direct_theme_name_hit", "runtime_source": "v1_fallback"},
        {"event_id": 3, "subject_key": "9010250", "match_reason": "direct_theme_name_hit", "runtime_source": "v1_fallback"},
    ]

    metrics = _quality_watch_metrics(details, candidates)

    assert metrics["direct_theme_name_hit_count"] == 4
    assert metrics["v1_fallback_direct_hit_count"] == 3
    assert metrics["direct_theme_name_hit_bad_count"] == 2
    assert metrics["v1_fallback_direct_hit_bad_count"] == 2
    assert metrics["ambiguous_direct_hit_candidates_count"] == 2
    assert metrics["target_wrong_theme_residual_count"] == 1


def test_watchlist_subject_rows_include_risk_tier_and_actions(tmp_path):
    details = [
        {"event_id": 1, "subject_key": "9054404", "match_reason": "direct_theme_name_hit", "runtime_source": "v1_fallback", "title": "A股全球第一"},
        {"event_id": 2, "subject_key": "9054404", "match_reason": "direct_theme_name_hit", "runtime_source": "v2_accepted", "title": "A股全球第一"},
        {"event_id": 3, "subject_key": "9013055", "match_reason": "profile_hit", "runtime_source": "v2_accepted", "title": "物流"},
    ]
    reviews = [
        {"proposed_theme_name": "A股全球第一"},
        {"proposed_theme_name": "物流"},
    ]
    candidates = [
        {"event_id": 1, "subject_key": "9054404", "match_reason": "direct_theme_name_hit", "runtime_source": "v1_fallback", "title": "A股全球第一"},
    ]

    rows = _watchlist_subject_rows(details, reviews, candidates)
    by_subject = {row["subject_key"]: row for row in rows}

    p0 = by_subject["9054404"]
    assert p0["risk_tier"] == "P0"
    assert p0["match_count"] == 2
    assert p0["review_count"] == 1
    assert p0["direct_theme_name_hit_count"] == 2
    assert p0["v1_fallback_direct_hit_count"] == 1
    assert p0["bad_count"] == 1
    assert p0["suggested_action"] == "delta_repair"

    p1 = by_subject["9013055"]
    assert p1["risk_tier"] == "P1"
    assert p1["match_count"] == 1
    assert p1["review_count"] == 1

    report_path = tmp_path / "quality_report.md"
    _write_quality_report(report_path, date(2026, 5, 31), {"watchlist_subject_rows": rows}, [])
    content = report_path.read_text(encoding="utf-8")

    assert "## Broad Theme Watchlist" in content
    assert "A股全球第一" in content


def test_hard_negative_subject_rows_loads_from_compare_summary(tmp_path):
    summary_path = tmp_path / "theme_profile_v1_v2_compare_summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "hard_negative_subject_rows": [
                    {
                        "subject_key": "9054404",
                        "subject_name": "A股全球第一",
                        "hard_negative_case_count": 3,
                        "hard_negative_reject_count": 2,
                        "hard_negative_reject_rate": 0.6667,
                        "failed_hard_negative_cases": ["case_a"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    rows = _hard_negative_subject_rows(summary_path)

    assert rows == [
        {
            "subject_key": "9054404",
            "subject_name": "A股全球第一",
            "hard_negative_case_count": 3,
            "hard_negative_reject_count": 2,
            "hard_negative_reject_rate": 0.6667,
            "failed_hard_negative_cases": ["case_a"],
        }
    ]

    report_path = tmp_path / "quality_report.md"
    _write_quality_report(
        report_path,
        date(2026, 5, 31),
        {
            "watchlist_subject_rows": [],
            "hard_negative_subject_rows": rows,
        },
        [],
    )
    content = report_path.read_text(encoding="utf-8")

    assert "## Hard Negative Watchlist" in content
    assert "A股全球第一" in content

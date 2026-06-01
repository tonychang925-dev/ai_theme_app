from theme_service.tools.build_product_runtime_daily_quality_report import _quality_watch_metrics


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

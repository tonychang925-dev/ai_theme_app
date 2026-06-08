from __future__ import annotations

from stock_processing_service.application.jobs.build_post_market_recap_job import BuildPostMarketRecapJob


def test_confirmed_mainline_hotspots_are_merged_into_strong_hotspots() -> None:
    confirmed = BuildPostMarketRecapJob._build_confirmed_mainline_hotspots(
        {
            "active_mainlines": [
                {
                    "mainline_id": "ml_AI光纤_202606",
                    "mainline_name": "AI光纤",
                    "canonical_subject_key": "9064103",
                    "mainline_strength_score": 45.2,
                    "state": "divergence",
                }
            ]
        }
    )

    merged = BuildPostMarketRecapJob._merge_hotspot_subjects(
        [
            {"subject_key": "9044385", "theme_name": "电缆", "source": "strong_stock_reviews"},
        ],
        confirmed,
    )

    assert merged[0]["subject_key"] == "9064103"
    assert merged[0]["source"] == "confirmed_mainline"
    assert merged[1]["subject_key"] == "9044385"

"""Formal Review projection schema contract.

Keeps the six-chapter formal_review model frozen and prevents removed legacy
fields from leaking back into the projection output.
"""

from __future__ import annotations

from types import SimpleNamespace

from stock_processing_service.application.services.daily_review.formal_review_projection_compiler import (
    FormalReviewProjectionCompiler,
)


def test_formal_review_has_exact_six_business_chapters() -> None:
    projection = FormalReviewProjectionCompiler().compile(
        trade_date="2026-07-09",
        engine_report={},
        snapshot=SimpleNamespace(
            emotion_review={},
            narrative={},
            playbook={},
            cognition_cards=[],
            chart_reviews=[],
        ),
    ).to_dict()

    assert set(projection.keys()) == {
        "metadata",
        "formal_review",
        "evidence_appendix",
        "diagnostics",
    }

    formal_review = projection["formal_review"]
    assert set(formal_review.keys()) == {
        "version",
        "executive_summary",
        "market_state",
        "theme_structure",
        "stock_structure",
        "capital_evidence",
        "next_day_plan",
        "evidence_charts",
    }

    forbidden_legacy_fields = {
        "workbench_data",
        "confirmed_mainlines",
        "pending_mainline_reviews",
    }
    assert forbidden_legacy_fields.isdisjoint(projection.keys())
    assert forbidden_legacy_fields.isdisjoint(formal_review.keys())

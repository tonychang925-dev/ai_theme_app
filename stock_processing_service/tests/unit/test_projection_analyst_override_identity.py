"""PR2.4 — Identity override projection tests.

Analyst edits to subject_name are entity identity changes. They must be
projected into FormalReview theme_structure instead of being treated as
ordinary assessment text or ignored.
"""

from __future__ import annotations

from stock_processing_service.application.services.daily_review.projections.theme_structure import (
    project_theme_structure,
)


def test_subject_name_field_override_updates_formal_theme_identity() -> None:
    """AI theme identity 人形机器人, analyst identity override PCB -> final PCB."""
    result = project_theme_structure(
        engine_report={
            "mainline_daily_states": [],
            "theme_driver_events": [],
            "mainline_narrative": {},
        },
        snapshot_cognition_cards=[
            {
                "subject_id": "theme:robot",
                "subject_key": "robot",
                "subject_name": "人形机器人",
                "attention_level": "CRITICAL",
                "attention_score": 91,
                "analyst_reviewed": True,
                "field_overrides": {
                    "subject_name": {
                        "ai_value": "人形机器人",
                        "analyst_value": "PCB",
                        "reason": "机器人高位分歧，资金切换到PCB容量方向",
                    }
                },
            }
        ],
        builder_theme_reviews=[],
        builder_theme_capital_reviews=[],
    )

    themes = result["themes"]
    assert len(themes) == 1

    theme = themes[0]
    assert theme["subject_key"] == "theme:robot"
    assert theme["theme_name"] == "PCB"

    overrides = theme["analyst_view"]["overrides"]
    subject_name_override = next((item for item in overrides if item["field"] == "subject_name"), None)
    assert subject_name_override is not None
    assert subject_name_override["field_class"] == "IDENTITY"
    assert subject_name_override["ai_value"] == "人形机器人"
    assert subject_name_override["analyst_value"] == "PCB"
    assert subject_name_override["final_value"] == "PCB"
    assert subject_name_override["reason"] == "机器人高位分歧，资金切换到PCB容量方向"


def test_subject_name_identity_override_matches_normalized_subject_key() -> None:
    """theme: prefix mismatch must not prevent identity override projection."""
    result = project_theme_structure(
        engine_report={
            "mainline_daily_states": [],
            "theme_driver_events": [
                {
                    "subject_key": "theme:robot",
                    "driver_events": [{"summary": "高位分歧"}],
                }
            ],
            "mainline_narrative": {},
        },
        snapshot_cognition_cards=[
            {
                "subject_id": "robot",
                "subject_name": "人形机器人",
                "field_overrides": {
                    "subject_name": {
                        "ai_value": "人形机器人",
                        "analyst_value": "PCB",
                    }
                },
            }
        ],
        builder_theme_reviews=[],
        builder_theme_capital_reviews=[],
    )

    theme = next(item for item in result["themes"] if item["subject_key"] == "theme:robot")
    assert theme["theme_name"] == "PCB"

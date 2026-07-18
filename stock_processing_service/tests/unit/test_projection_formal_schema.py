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


def test_formal_review_uses_approved_snapshot_canonical_stock_and_capital_fields() -> None:
    projection = FormalReviewProjectionCompiler().compile(
        trade_date="2026-07-16",
        engine_report={},
        snapshot=SimpleNamespace(
            emotion_review={},
            narrative={},
            playbook={},
            cognition_cards=[],
            chart_reviews=[],
            stock_structure=[
                {
                    "stock_code": "600152.SH",
                    "stock_name": "维科技术",
                    "subject_key": "9035101",
                    "theme_name": "钠离子电池",
                    "role": "dragon",
                    "watch_score": 62.0,
                    "watch_priority": 71,
                    "watch_status": "removed",
                    "cycle_state": "divergence",
                    "main_net_inflow": 12000000,
                    "money_flow_tier": "LOW",
                }
            ],
            capital_active_amount=886.27,
            capital_institution_style=[
                {"direction_key": "AI_COMPUTE", "direction_name": "AI算力方向", "flow_score": 41.25}
            ],
            capital_hot_money_style=[],
            capital_seat_money={"institution_net_buy": 30000000},
        ),
    ).to_dict()

    formal = projection["formal_review"]
    assert formal["stock_structure"]["stocks"][0]["stock_name"] == "维科技术"
    assert formal["stock_structure"]["stocks"][0]["today_role"] == "LEADER"
    assert formal["stock_structure"]["stocks"][0]["scores"]["composite"] == 62.0
    assert formal["capital_evidence"]["market"]["active_amount"] == 886.27
    assert formal["capital_evidence"]["market"]["institution_net_buy"] == 30000000
    assert formal["capital_evidence"]["stocks"][0]["capital"]["fact"]["main_net_inflow"] == 12000000
    assert formal["capital_evidence"]["stocks"][0]["capital"]["assessment"]["money_flow_tier"] == "LOW"
    assert formal["next_day_plan"]["watch_stocks"][0]["stock_code"] == "600152.SH"


def test_formal_review_omits_zero_turnover_as_missing_data() -> None:
    projection = FormalReviewProjectionCompiler().compile(
        trade_date="2026-07-16",
        engine_report={},
        snapshot=SimpleNamespace(
            emotion_review={},
            narrative={},
            playbook={},
            cognition_cards=[],
            chart_reviews=[
                {
                    "chart_type": "active_capital",
                    "key_metrics": {
                        "active_amount_yi": 886.27,
                        "total_amount_yi": 0.0,
                    },
                }
            ],
        ),
    ).to_dict()

    facts = projection["formal_review"]["market_state"]["facts"]
    assert facts["active_amount_yi"] == 886.27
    assert "total_amount_yi" not in facts

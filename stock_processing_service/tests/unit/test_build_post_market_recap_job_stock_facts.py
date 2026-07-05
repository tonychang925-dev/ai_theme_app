from __future__ import annotations

from stock_processing_service.application.jobs.build_post_market_recap_job import (
    BuildPostMarketRecapJob,
)


def test_materialize_stock_facts_by_subject_flattens_authoritative_fact_layer() -> None:
    stock_facts_by_subject = {
        "9010301": [
            {
                "subject_key": "9010301",
                "theme_name": "PCB",
                "stock_id": "301366",
                "stock_name": "一博科技",
                "leader_composite_score": 92,
                "leader_capital_score": 88,
                "pct_chg": 20.0,
            },
            {
                "theme_name": "PCB",
                "stock_id": "300903",
                "stock_name": "科翔股份",
                "leader_composite_score": 81,
                "leader_capital_score": 75,
                "pct_chg": 14.0,
            },
        ],
        "9010402": [
            {
                "subject_key": "9010402",
                "theme_name": "玻璃基板",
                "stock_id": "002845",
                "stock_name": "同兴达",
                "leader_composite_score": 85,
                "leader_capital_score": 80,
                "pct_chg": 10.0,
            }
        ],
    }

    rows = BuildPostMarketRecapJob._materialize_stock_facts_by_subject(stock_facts_by_subject)

    assert [row["stock_id"] for row in rows] == ["301366", "300903", "002845"]
    assert rows[0]["subject_key"] == "9010301"
    assert rows[1]["subject_key"] == "9010301"
    assert rows[2]["subject_key"] == "9010402"
    assert rows[1]["theme_name"] == "PCB"
    assert rows[2]["theme_name"] == "玻璃基板"


def test_materialize_report_context_stock_facts_prefers_structured_board_rows() -> None:
    recap_doc = {
        "strong_stock_reviews": [
            {
                "subject_key": "9010301",
                "theme_name": "PCB",
                "stock_id": "301366",
                "stock_name": "一博科技",
                "board_count": 4,
                "leader_composite_score": 92,
                "leader_capital_score": 88,
                "pct_chg": 20.0,
            },
            {
                "subject_key": "9010301",
                "theme_name": "PCB",
                "stock_id": "300903",
                "stock_name": "科翔股份",
                "board_count": 2,
                "leader_composite_score": 81,
                "leader_capital_score": 75,
                "pct_chg": 14.0,
            },
        ],
        "post_market_decision_v2": {
            "strong_stock_pool_reviews": [
                {
                    "subject_key": "9010402",
                    "theme_name": "玻璃基板",
                    "stock_id": "002845",
                    "stock_name": "同兴达",
                    "board_count": 3,
                }
            ]
        },
    }

    report_context = BuildPostMarketRecapJob._materialize_report_context_stock_facts(
        recap_doc=recap_doc,
        base_report_context={},
        stock_facts_by_subject={},
    )

    rows = report_context["stock_facts"]
    assert [row["stock_id"] for row in rows] == ["301366", "300903", "002845"]
    assert rows[0]["board_count"] == 4
    assert rows[1]["board_count"] == 2
    assert rows[2]["board_count"] == 3
    assert report_context["stock_facts_by_subject"] == {}

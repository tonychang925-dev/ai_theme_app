from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.limit_up_board_recalculator import (
    LimitUpBoardRecalculator,
)


class _FakeConn:
    def __init__(self, rows, authoritative_rows=None):
        self._rows = rows
        self._authoritative_rows = authoritative_rows or []
        self._call_count = 0

    async def fetch(self, *args, **kwargs):
        self._call_count += 1
        if self._call_count == 1:
            return self._rows
        return self._authoritative_rows


@pytest.mark.asyncio
async def test_limit_up_board_recalculator_enriches_focus_stock_board_counts() -> None:
    recap_doc = {
        "report_context": {
            "stock_facts": [
                {"subject_key": "9010301", "theme_name": "PCB", "stock_id": "000001", "stock_name": "三连板"},
                {"subject_key": "9010301", "theme_name": "PCB", "stock_id": "000002", "stock_name": "首板"},
                {"subject_key": "9010301", "theme_name": "PCB", "stock_id": "000003", "stock_name": "非涨停"},
            ]
        },
        "market_overview_review": {
            "theme_limitup_matrix": {
                "columns": [
                    {
                        "theme_name": "PCB",
                        "subject_key": "9010301",
                        "focus_stocks": [
                            {"stock_id": "000001", "stock_name": "三连板"},
                            {"stock_id": "000002", "stock_name": "首板"},
                            {"stock_id": "000003", "stock_name": "非涨停"},
                        ],
                    }
                ]
            }
        }
    }
    rows = [
        {"stock_id": "000001", "trade_date": date(2026, 6, 17), "pct_chg": 10.0},
        {"stock_id": "000001", "trade_date": date(2026, 6, 16), "pct_chg": 9.98},
        {"stock_id": "000001", "trade_date": date(2026, 6, 13), "pct_chg": 10.01},
        {"stock_id": "000002", "trade_date": date(2026, 6, 17), "pct_chg": 9.95},
        {"stock_id": "000002", "trade_date": date(2026, 6, 16), "pct_chg": 7.2},
        {"stock_id": "000003", "trade_date": date(2026, 6, 17), "pct_chg": 4.2},
    ]

    recalculator = LimitUpBoardRecalculator()
    enriched = await recalculator.enrich_recap_doc(recap_doc, date(2026, 6, 17), _FakeConn(rows))

    focus_stocks = enriched["market_overview_review"]["theme_limitup_matrix"]["columns"][0]["focus_stocks"]
    board_map = {row["stock_id"]: row.get("board_count") for row in focus_stocks}
    board_groups = enriched["market_overview_review"]["theme_limitup_matrix"]["columns"][0]["board_groups"]
    board_group_map = {row["board_count"]: row for row in board_groups}

    assert board_map["000001"] == 3
    assert board_map["000002"] == 1
    assert board_map["000003"] is None
    assert board_group_map[3]["stock_count"] == 1
    assert board_group_map[1]["stock_count"] == 1
    assert enriched["limit_up_ladder_context"]["source"] == "recomputed_from_stock_daily_snapshot"


@pytest.mark.asyncio
async def test_limit_up_board_recalculator_enriches_placeholder_theme_from_theme_stock_map() -> None:
    recap_doc = {
        "report_context": {
            "stock_facts": [
                {"subject_key": "__independent__", "theme_name": "未归类", "stock_id": "000004", "stock_name": "D"},
            ]
        },
        "mainline_daily_states": [
            {
                "mainline_id": "9027744",
                "canonical_subject_key": "9027744",
                "mainline_name": "国内机器人",
                "lifecycle_state": "divergence",
            }
        ],
        "market_overview_review": {
            "theme_limitup_matrix": {
                "columns": [
                    {
                        "theme_name": "未归类",
                        "subject_key": "__independent__",
                        "focus_stocks": [
                            {"stock_id": "000004", "stock_name": "D", "subject_key": "__independent__", "theme_name": "未归类"},
                        ],
                    }
                ]
            }
        },
    }
    rows = [
        {"stock_id": "000004", "trade_date": date(2026, 6, 17), "pct_chg": 10.0},
        {"stock_id": "000004", "trade_date": date(2026, 6, 16), "pct_chg": 10.0},
    ]
    authoritative_rows = [
        {"stock_key": "000004", "subject_key": "9027744", "theme_name": "国内机器人"},
    ]

    recalculator = LimitUpBoardRecalculator()
    enriched = await recalculator.enrich_recap_doc(
        recap_doc,
        date(2026, 6, 17),
        _FakeConn(rows, authoritative_rows),
    )

    stock_fact = enriched["report_context"]["stock_facts"][0]
    board_group_map = {
        group["board_count"]: group
        for group in enriched["market_overview_review"]["theme_limitup_matrix"]["columns"][0]["board_groups"]
    }

    assert stock_fact["subject_key"] == "9027744"
    assert stock_fact["theme_name"] == "国内机器人"
    assert board_group_map[2]["stock_count"] == 1

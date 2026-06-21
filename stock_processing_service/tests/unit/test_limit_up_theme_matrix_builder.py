from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from stock_processing_service.application.services.limit_up_theme_matrix_builder import (
    LimitUpThemeMatrixBuilder,
)


class _FakeConn:
    def __init__(self, trade_date: date) -> None:
        self.trade_date = trade_date
        self.queries: list[str] = []

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        q = " ".join(query.lower().split())
        self.queries.append(q)
        assert "stock_facts" not in q
        assert "strong_stock_reviews" not in q
        assert "market_overview_review" not in q
        assert "limit_up_theme_events" not in q
        assert "theme_master" not in q

        if "from stock_daily_snapshot" in q and "trade_date = $1::date" in q and "pct_chg" in q and ">= $2" in q:
            return [
                {
                    "stock_key": "000001",
                    "stock_id": "000001.SZ",
                    "stock_name": "PCB龙头",
                    "close_price": 12.3,
                    "pct_chg": 10.01,
                    "amount": 100000000,
                },
                {
                    "stock_key": "000003",
                    "stock_id": "000003.SZ",
                    "stock_name": "无映射股",
                    "close_price": 7.8,
                    "pct_chg": 9.99,
                    "amount": 50000000,
                },
            ]

        if "from stock_daily_snapshot" in q and "trade_date <= $1::date" in q:
            return [
                {"stock_key": "000001", "trade_date": self.trade_date, "pct_chg": 10.01},
                {"stock_key": "000001", "trade_date": self.trade_date - timedelta(days=1), "pct_chg": 10.0},
                {"stock_key": "000001", "trade_date": self.trade_date - timedelta(days=2), "pct_chg": 9.8},
                {"stock_key": "000001", "trade_date": self.trade_date - timedelta(days=3), "pct_chg": 0.5},
                {"stock_key": "000003", "trade_date": self.trade_date, "pct_chg": 9.99},
            ]

        if "from subject_stock_map" in q:
            return [
                {
                    "stock_id": "000001",
                    "subject_key": "pcb",
                    "sort": 1,
                    "top": 1,
                    "source_type": "db",
                    "confidence": 1.0,
                    "reason": "确定映射",
                }
            ]

        if "from mainline_daily_state" in q:
            return [
                {
                    "canonical_subject_key": "pcb",
                    "mainline_name": "PCB印制电路板",
                    "active_subject_keys_json": ["pcb", "PCB印制电路板"],
                    "lifecycle_state": "divergence",
                    "mainline_alive": True,
                    "mainline_trade_alive": True,
                    "trade_mode": "mainline_core_only",
                    "allow_trade": True,
                }
            ]

        if "from subject_rank_daily" in q:
            return [{"subject_key": "pcb", "heat_name": "PCB印制电路板"}]

        if "from theme_mainline_identity_registry" in q or "from theme_detail_snapshot" in q:
            return []

        raise AssertionError(f"unexpected query: {query}")


@pytest.mark.asyncio
async def test_limit_up_theme_matrix_builder_uses_snapshot_board_count_and_deterministic_mapping() -> None:
    trade_date = date(2026, 6, 18)
    matrix = await LimitUpThemeMatrixBuilder().build(trade_date=trade_date, conn=_FakeConn(trade_date))

    assert matrix["source"] == "limit_up_theme_matrix_builder"
    assert matrix["diagnostics"]["count_method"] == "stock_daily_snapshot_continuous_limit_up"
    assert matrix["diagnostics"]["limit_up_stock_count"] == 2
    assert matrix["diagnostics"]["mapped_stock_count"] == 1
    assert matrix["diagnostics"]["unmapped_stock_count"] == 1
    assert matrix["diagnostics"]["unmapped_stocks"][0]["stock_name"] == "无映射股"

    assert len(matrix["columns"]) == 1
    column = matrix["columns"][0]
    assert column["theme_name"] == "PCB印制电路板"
    assert column["mainline_name"] == "PCB印制电路板"
    assert column["diagnostics"]["mapping_source"] == "mainline_daily_state"
    assert column["limit_up_count"] == 1
    assert column["board_groups"][1]["board_count"] == 3
    assert column["board_groups"][1]["stock_count"] == 1
    assert column["board_groups"][1]["stocks"][0]["stock_name"] == "PCB龙头"

    assert matrix["board_totals"] == {"4": 0, "3": 1, "2": 0, "1": 0}
    assert sum(matrix["board_totals"].values()) == sum(col["limit_up_count"] for col in matrix["columns"])


@pytest.mark.asyncio
async def test_limit_up_theme_matrix_builder_does_not_emit_non_limit_up_rows() -> None:
    trade_date = date(2026, 6, 18)
    matrix = await LimitUpThemeMatrixBuilder().build(trade_date=trade_date, conn=_FakeConn(trade_date))
    visible_stock_names = [
        stock["stock_name"]
        for column in matrix["columns"]
        for group in column["board_groups"]
        for stock in group["stocks"]
    ]

    assert "当日未涨停" not in visible_stock_names
    assert "未归类" not in [column["theme_name"] for column in matrix["columns"]]
    assert "__independent__" not in [column["theme_name"] for column in matrix["columns"]]
    assert not any(str(column["theme_name"]).isdigit() for column in matrix["columns"])

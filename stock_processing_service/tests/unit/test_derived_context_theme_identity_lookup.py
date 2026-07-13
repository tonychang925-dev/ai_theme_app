from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.analyst_workbench.derived_context_reader import (
    DerivedContextReader,
    WorkbenchDerivedContext,
)


class _FakeConn:
    def __init__(self) -> None:
        self.query = ""
        self.args = ()

    async def fetch(self, query: str, *args):
        self.query = query
        self.args = args
        return [{"subject_key": "9055378", "theme_name": "国产算力"}]


class _FakeSeatMoneyConn:
    def __init__(self, value) -> None:
        self.query = ""
        self.args = ()
        self.value = value

    async def fetchrow(self, query: str, *args):
        self.query = query
        self.args = args
        return {"seat_money_summary": self.value}


@pytest.mark.asyncio
async def test_theme_identity_lookup_reads_subject_binding_view() -> None:
    conn = _FakeConn()
    ctx = WorkbenchDerivedContext(trade_date="2026-07-09")

    rows = await DerivedContextReader()._fetch_theme_identity_lookup(
        conn,
        [
            {"subject_key": "9055378", "theme_name": "9055378"},
            {"subject_key": "9015778", "theme_name": "存储芯片"},
            {"subject_key": "9019807", "stock_name": "超捷股份", "theme_name": "9019807"},
        ],
        ctx,
    )

    assert "vw_subject_theme_binding" in conn.query
    assert conn.args == (["9015778", "9019807", "9055378"],)
    assert rows == [
        {
            "subject_key": "9055378",
            "theme_name": "国产算力",
            "_identity_source": "vw_subject_theme_binding",
        }
    ]
    assert ctx.missing_sources == []


@pytest.mark.asyncio
async def test_seat_money_summary_reads_latest_recap_snapshot_contract() -> None:
    conn = _FakeSeatMoneyConn(
        {
            "institution_buy_rows": [{"theme_name": "国产算力"}],
            "hot_money_buy_rows": [{"hot_money_name": "测试席位"}],
            "diagnostics": {"source": "structured"},
        }
    )

    summary = await DerivedContextReader()._fetch_seat_money_summary(conn, date(2026, 7, 9))

    assert "post_market_recap_snapshot" in conn.query
    assert "seat_money_summary" in conn.query
    assert conn.args == (date(2026, 7, 9),)
    assert summary["institution_buy_rows"][0]["theme_name"] == "国产算力"
    assert summary["diagnostics"]["source"] == "structured"

from __future__ import annotations

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


@pytest.mark.asyncio
async def test_theme_identity_lookup_reads_subject_binding_view() -> None:
    conn = _FakeConn()
    ctx = WorkbenchDerivedContext(trade_date="2026-07-09")

    rows = await DerivedContextReader()._fetch_theme_identity_lookup(
        conn,
        [
            {"subject_key": "9055378", "theme_name": "9055378"},
            {"subject_key": "9015778", "theme_name": "存储芯片"},
        ],
        ctx,
    )

    assert "vw_subject_theme_binding" in conn.query
    assert conn.args == (["9015778", "9055378"],)
    assert rows == [
        {
            "subject_key": "9055378",
            "theme_name": "国产算力",
            "_identity_source": "vw_subject_theme_binding",
        }
    ]
    assert ctx.missing_sources == []

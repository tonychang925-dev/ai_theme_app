from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.jobs.build_dragon_tiger_object_job import (
    BuildDragonTigerObjectJob,
)


@pytest.mark.asyncio
async def test_dragon_tiger_object_job_can_skip_external_fetch_when_cache_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeSnapshotService:
        def __init__(self, config) -> None:
            self.config = config

        def load_cached_top_list(self, trade_date: str):
            calls.append(f"load_top_list:{trade_date}")
            return None

        def load_cached_top_inst(self, trade_date: str):
            calls.append(f"load_top_inst:{trade_date}")
            return None

        def fetch_or_cache_top_list(self, trade_date: str):
            raise AssertionError("allow_fetch=False must not fetch top_list")

        def fetch_or_cache_top_inst(self, trade_date: str):
            raise AssertionError("allow_fetch=False must not fetch top_inst")

    import database_service.scripts.build_dragon_tiger_object as script_module

    monkeypatch.setattr(
        script_module,
        "TushareDragonTigerSnapshotService",
        FakeSnapshotService,
    )

    result = await BuildDragonTigerObjectJob().execute(
        trade_date=date(2026, 5, 28),
        allow_fetch=False,
    )

    assert calls == ["load_top_list:2026-05-28", "load_top_inst:2026-05-28"]
    assert result.status == "skipped_no_data"
    assert result.affected_rows == 0
    assert result.warnings == [
        "dragon_tiger raw snapshot unavailable; recap derivation does not fetch external data"
    ]

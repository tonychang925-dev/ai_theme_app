from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pytest

from stock_processing_service.application.use_cases.generate_post_market_derived_data import (
    _DragonTigerObjectBuilder,
)
from stock_processing_service.application.jobs.build_dragon_tiger_object_job import (
    BuildDragonTigerObjectJob,
)
from stock_processing_service.contracts.dto import BuildResult


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


@dataclass
class _SnapshotResult:
    trade_date: str
    dataset_name: str
    row_count: int
    cache_hit: bool
    snapshot_path: str
    records: list[dict]


@pytest.mark.asyncio
async def test_dragon_tiger_object_job_reports_empty_cached_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeSnapshotService:
        def __init__(self, config) -> None:
            self.config = config

        def load_cached_top_list(self, trade_date: str):
            return _SnapshotResult(
                trade_date=trade_date,
                dataset_name="dragon_tiger_top_list",
                row_count=0,
                cache_hit=True,
                snapshot_path="/raw/top_list.json",
                records=[],
            )

        def load_cached_top_inst(self, trade_date: str):
            return _SnapshotResult(
                trade_date=trade_date,
                dataset_name="dragon_tiger_top_inst",
                row_count=0,
                cache_hit=True,
                snapshot_path="/raw/top_inst.json",
                records=[],
            )

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

    assert result.status == "skipped_no_data"
    assert result.affected_rows == 0
    assert result.warnings == ["dragon_tiger raw snapshots exist but payload is empty"]
    assert result.metrics["top_list_rows"] == 0
    assert result.metrics["top_inst_rows"] == 0
    assert result.metrics["top_list_snapshot_path"] == "/raw/top_list.json"


@pytest.mark.asyncio
async def test_dragon_tiger_derived_builder_propagates_empty_snapshot_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeDragonTigerObjectJob:
        def __init__(self, write_port=None) -> None:
            self.write_port = write_port

        async def execute(self, trade_date: date, tushare_token: str = "", *, allow_fetch: bool = True):
            return BuildResult(
                name="build_dragon_tiger_object",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_no_data",
                warnings=["dragon_tiger raw snapshots exist but payload is empty"],
                metrics={
                    "top_list_rows": 0,
                    "top_inst_rows": 0,
                    "top_list_snapshot_path": "/raw/top_list.json",
                    "top_inst_snapshot_path": "/raw/top_inst.json",
                },
            )

    import stock_processing_service.application.jobs.build_dragon_tiger_object_job as job_module

    monkeypatch.setattr(job_module, "BuildDragonTigerObjectJob", FakeDragonTigerObjectJob)

    result = await _DragonTigerObjectBuilder(db_manager=object()).run(date(2026, 5, 28))

    assert result["status"] == "skipped_no_data"
    assert result["error_code"] == "DRAGON_TIGER_RAW_SNAPSHOT_EMPTY"
    assert result["error"] == "dragon_tiger raw snapshots exist but payload is empty"
    assert result["metrics"]["top_list_snapshot_path"] == "/raw/top_list.json"

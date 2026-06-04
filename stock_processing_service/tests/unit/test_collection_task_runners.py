from __future__ import annotations

import pytest

from stock_processing_service.application.services.collection_task_runners import (
    BuildDragonTigerObjectRunner,
)
from stock_processing_service.application.services.collection_task_registry import (
    CollectionTaskContext,
)


class _FakeBuildResult:
    def __init__(self, status: str, warnings: list[str], affected_rows: int = 0) -> None:
        self.status = status
        self.warnings = warnings
        self.affected_rows = affected_rows
        self.metrics = {"top_list_rows": 0, "top_inst_rows": 0}


class _FakeDragonTigerJob:
    async def execute(self, trade_date, tushare_token: str = ""):
        return _FakeBuildResult(
            status="skipped_no_data",
            warnings=["dragon_tiger raw snapshots exist but payload is empty"],
            affected_rows=0,
        )


class _FakeContainer:
    build_dragon_tiger_object = _FakeDragonTigerJob()


@pytest.mark.asyncio
async def test_dragon_tiger_runner_treats_no_data_as_skipped() -> None:
    runner = BuildDragonTigerObjectRunner()
    context = CollectionTaskContext(
        trade_date="2026-06-04",
        env={"TUSHARE_TOKEN": "token"},
        container=_FakeContainer(),
    )

    result = await runner.run(context)

    assert result.status == "skipped"
    assert result.current_label == "龙虎榜未生成 (dragon_tiger raw snapshots exist but payload is empty)"
    assert result.error_message == ""
    assert "dragon_tiger status=skipped_no_data rows=0" in result.logs

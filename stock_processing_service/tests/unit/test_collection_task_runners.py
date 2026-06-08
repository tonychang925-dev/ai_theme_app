from __future__ import annotations

import pytest

from stock_processing_service.application.services.collection_task_runners import (
    BuildDragonTigerObjectRunner,
    TushareKlineRunner,
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


class _FakeTushareDailyBarJob:
    def __init__(self, status: str, affected_rows: int, warnings: list[str] | None = None) -> None:
        self.status = status
        self.affected_rows = affected_rows
        self.warnings = warnings or []

    async def execute(self, trade_date, token: str, pause_seconds: float = 0.1):
        return _FakeBuildResult(
            status=self.status,
            warnings=self.warnings,
            affected_rows=self.affected_rows,
        )


class _FakeTushareContainer:
    def __init__(self, status: str, affected_rows: int, warnings: list[str] | None = None) -> None:
        self.build_tushare_daily_bar = _FakeTushareDailyBarJob(status, affected_rows, warnings)


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
    assert result.current_label == "数据为空，skip到下一个流程"
    assert result.error_message == ""
    assert "龙虎榜数据为空，skip到下一个流程: rows=0" in result.logs
    assert "龙虎榜详情: dragon_tiger raw snapshots exist but payload is empty" in result.logs


@pytest.mark.asyncio
async def test_tushare_kline_runner_fails_on_ok_no_data() -> None:
    runner = TushareKlineRunner()
    context = CollectionTaskContext(
        trade_date="2026-06-04",
        env={"TUSHARE_TOKEN": "token"},
        container=_FakeTushareContainer("ok_no_data", 0, ["tushare_api_returned_empty"]),
    )

    result = await runner.run(context)

    assert result.status == "failed"
    assert result.current_label == "Tushare日线采集完成 (ok_no_data)"
    assert result.error_message == "tushare daily bar returned ok_no_data rows=0"
    assert "tushare_kline status=ok_no_data rows=0" in result.logs
    assert "tushare_api_returned_empty" in result.logs


@pytest.mark.asyncio
async def test_tushare_kline_runner_fails_on_ok_existing() -> None:
    runner = TushareKlineRunner()
    context = CollectionTaskContext(
        trade_date="2026-06-04",
        env={"TUSHARE_TOKEN": "token"},
        container=_FakeTushareContainer("ok_existing", 0, ["tushare_api_unavailable"]),
    )

    result = await runner.run(context)

    assert result.status == "failed"
    assert result.current_label == "Tushare日线采集完成 (ok_existing)"
    assert result.error_message == "tushare daily bar returned ok_existing rows=0"
    assert "tushare_kline status=ok_existing rows=0" in result.logs
    assert "tushare_api_unavailable" in result.logs


@pytest.mark.asyncio
async def test_tushare_kline_runner_accepts_only_real_ok() -> None:
    runner = TushareKlineRunner()
    context = CollectionTaskContext(
        trade_date="2026-06-04",
        env={"TUSHARE_TOKEN": "token"},
        container=_FakeTushareContainer("ok", 5511),
    )

    result = await runner.run(context)

    assert result.status == "success"
    assert result.current_label == "Tushare日线采集完成 (ok)"
    assert result.error_message == ""
    assert "tushare_kline status=ok rows=5511" in result.logs

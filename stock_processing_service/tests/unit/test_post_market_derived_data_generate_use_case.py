from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import pytest

from stock_processing_service.application.use_cases.generate_post_market_derived_data import (
    PostMarketDerivedDataGenerateUseCase,
    _StockAbnormalSignalBuilder,
)


@dataclass
class _FakeReadinessResult:
    status: str = "failed_precondition"
    missing_tables: list[str] | None = None

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "missing_tables": self.missing_tables or ["money_flow_enhanced", "strong_stock_watch_history"],
        }


class _FakeReadinessService:
    def __init__(self, pool=None) -> None:
        self.pool = pool

    async def check(self, trade_date: date) -> _FakeReadinessResult:
        return _FakeReadinessResult()


class _FakeJobStatusService:
    events: list[tuple] = []

    def __init__(self, pool=None) -> None:
        self.pool = pool

    async def mark_running(self, trade_date: date, job_key: str, diagnostics=None) -> None:
        self.events.append(("running", job_key))

    async def mark_finished(
        self,
        trade_date: date,
        job_key: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        diagnostics=None,
    ) -> None:
        self.events.append(("finished", job_key, status, error_code, error_message))


class _Builder:
    def __init__(self, job_key: str, status: str, calls: list[str]) -> None:
        self._job_key = job_key
        self._status = status
        self._calls = calls

    async def run(self, trade_date: date) -> dict:
        self._calls.append(self._job_key)
        return {"job_key": self._job_key, "status": self._status, "affected_rows": 1 if self._status == "success" else 0}


@pytest.mark.asyncio
async def test_derived_data_generation_fast_fails_after_required_upstream_no_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-POSTMARKET-502: do not keep running downstream scripts after a required upstream is empty."""

    import stock_processing_service.application.services.post_market_job_status_service as status_module
    import stock_processing_service.application.services.post_market_readiness_service as readiness_module

    _FakeJobStatusService.events = []
    monkeypatch.setattr(status_module, "PostMarketJobStatusService", _FakeJobStatusService)
    monkeypatch.setattr(readiness_module, "PostMarketReadinessService", _FakeReadinessService)

    calls: list[str] = []
    uc = PostMarketDerivedDataGenerateUseCase(pool=object(), db_manager=object())
    uc.register_builder("theme_cycle_truth", _Builder("theme_cycle_truth", "success", calls))
    uc.register_builder("dragon_tiger_object_build", _Builder("dragon_tiger_object_build", "skipped_no_data", calls))
    uc.register_builder("theme_leader_candidate_build", _Builder("theme_leader_candidate_build", "failed_no_rows", calls))
    uc.register_builder("money_flow_enhanced_build", _Builder("money_flow_enhanced_build", "success", calls))
    uc.register_builder("stock_abnormal_signal_build", _Builder("stock_abnormal_signal_build", "success", calls))
    uc.register_builder("strong_stock_watch_build", _Builder("strong_stock_watch_build", "success", calls))

    result = await uc.execute(date(2026, 5, 28), force=False)

    assert result.status == "failed_precondition"
    assert calls == ["theme_cycle_truth", "dragon_tiger_object_build", "theme_leader_candidate_build"]
    skipped = [item for item in result.job_results if item.get("error_code") == "UPSTREAM_TASK_FAILED"]
    assert [item["job_key"] for item in skipped] == [
        "money_flow_enhanced_build",
        "stock_abnormal_signal_build",
        "strong_stock_watch_build",
    ]
    assert ("running", "money_flow_enhanced_build") not in _FakeJobStatusService.events
    assert (
        "finished",
        "money_flow_enhanced_build",
        "failed_precondition",
        "UPSTREAM_TASK_FAILED",
        "upstream theme_leader_candidate_build status=failed_no_rows",
    ) in _FakeJobStatusService.events


@pytest.mark.asyncio
async def test_stock_abnormal_signal_builder_uses_db_input_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """盘后新链已有 DB 快照，异动股构建必须走 Gateway Job，不得扫本地 JSONL。"""

    import stock_processing_service.application.jobs.build_stock_abnormal_signal_job as job_module

    calls: list[object] = []

    class _FakeResult:
        affected_rows = 3
        status = "ok"

    class _FakeJob:
        def __init__(self, db_gateway=None):
            calls.append(db_gateway)

        async def execute(self, trade_date):
            return _FakeResult()

    monkeypatch.setattr(job_module, "BuildStockAbnormalSignalJob", _FakeJob)

    db_gateway = object()
    builder = _StockAbnormalSignalBuilder(pool=None, db_manager=db_gateway)
    result = await builder.run(date(2026, 5, 29))

    assert result["job_key"] == "stock_abnormal_signal_build"
    assert result["affected_rows"] == 3
    assert calls == [db_gateway]


@pytest.mark.asyncio
async def test_build_stock_abnormal_signal_job_rejects_missing_db_gateway() -> None:
    """Guard: BuildStockAbnormalSignalJob with db_gateway=None must return failure.

    This test would have caught the bootstrap wiring gap where
    abnormal_signal_job was constructed without db_gateway.
    """
    from stock_processing_service.application.jobs.build_stock_abnormal_signal_job import (
        BuildStockAbnormalSignalJob,
    )

    job = BuildStockAbnormalSignalJob(
        write_port=object(),
        db_gateway=None,  # ← the gap: bootstrap forgot this
    )
    result = await job.execute(trade_date=date(2026, 6, 10))

    assert result.status.startswith("failed"), (
        f"expected failure when db_gateway=None, got status={result.status!r}"
    )
    assert "no db_gateway" in result.status, (
        f"expected 'no db_gateway' in status, got {result.status!r}"
    )
    assert result.affected_rows == 0


@pytest.mark.asyncio
async def test_build_stock_abnormal_signal_job_accepts_valid_wiring() -> None:
    """Guard: BuildStockAbnormalSignalJob with proper wiring does not crash early."""
    from stock_processing_service.application.jobs.build_stock_abnormal_signal_job import (
        BuildStockAbnormalSignalJob,
    )

    class _FakeGateway:
        async def get_subject_stock_daily_snapshot_by_trade_date(self, trade_date):
            return []  # empty → returns ok_no_inputs, not a crash

    job = BuildStockAbnormalSignalJob(
        write_port=object(),
        db_gateway=_FakeGateway(),
    )
    result = await job.execute(trade_date=date(2026, 6, 10))

    assert "failed" not in result.status, (
        f"valid wiring should not fail, got status={result.status!r}"
    )

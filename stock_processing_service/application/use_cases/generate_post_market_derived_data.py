"""P2-1/P2-2: 每日动态复盘派生数据生成 UseCase。

总编排：按顺序执行 theme_cycle_truth → dragon_tiger_object_build →
money_flow_enhanced_build → stock_abnormal_signal_build → strong_stock_watch_build。
每个子任务统一写 post_market_job_status，执行前后记录 readiness。

P2-2: theme_cycle_truth builder 已接入 A/B layer jobs。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

SUB_TASK_ORDER = [
    ("theme_cycle_truth",        "theme_cycle_truth_build"),
    ("dragon_tiger_object_build", "dragon_tiger_object_build"),
    ("money_flow_enhanced_build", "money_flow_enhanced_build"),
    ("stock_abnormal_signal_build", "stock_abnormal_signal_build"),
    ("strong_stock_watch_build",  "strong_stock_watch_build"),
]


@dataclass
class DerivedDataResult:
    trade_date: str
    status: str
    before_readiness: dict[str, Any] = field(default_factory=dict)
    after_readiness: dict[str, Any] = field(default_factory=dict)
    job_results: list[dict[str, Any]] = field(default_factory=list)
    missing_tables: list[str] = field(default_factory=list)


class PostMarketDerivedDataGenerateUseCase:

    def __init__(self, pool=None, db_manager=None):
        self._pool = pool
        self._db_manager = db_manager
        self._builders: dict[str, Any] = {}

    def register_builder(self, job_key: str, builder):
        self._builders[job_key] = builder

    def register_theme_cycle_truth(self) -> None:
        self._builders["theme_cycle_truth"] = _ThemeCycleTruthBuilder(
            pool=self._pool, db_manager=self._db_manager)

    async def execute(
        self, trade_date_val: date, force: bool = False, dry_run: bool = False,
    ) -> DerivedDataResult:
        from stock_processing_service.application.services.post_market_readiness_service import (
            PostMarketReadinessService,
        )
        from stock_processing_service.application.services.post_market_job_status_service import (
            PostMarketJobStatusService,
        )

        jss = PostMarketJobStatusService(pool=self._pool)
        rs = PostMarketReadinessService(pool=self._pool)

        await jss.mark_finished(trade_date_val, "post_market_derived_data", "running")
        before = await rs.check(trade_date_val)
        before_dict = before.to_dict()

        job_results: list[dict[str, Any]] = []
        for job_key, _builder_key in SUB_TASK_ORDER:
            builder = self._builders.get(job_key)
            if builder is None:
                logger.warning("P2 builder not wired: %s", job_key)
                if not dry_run:
                    await jss.mark_finished(trade_date_val, job_key, "failed_precondition",
                        error_code="BUILDER_NOT_WIRED",
                        error_message=f"builder not registered for {job_key}")
                job_results.append({"job_key": job_key, "status": "not_wired",
                    "message": f"builder not registered for {job_key}"})
                continue

            await jss.mark_finished(trade_date_val, job_key, "running")
            try:
                sub_result = await builder.run(trade_date_val)
                sub_status = sub_result.get("status", "failed")
                sub_rows = sub_result.get("affected_rows", 0)
                await jss.mark_finished(trade_date_val, job_key, sub_status,
                    diagnostics={"affected_rows": sub_rows, "result": sub_result})
                job_results.append({
                    "job_key": job_key, "status": sub_status, "affected_rows": sub_rows,
                    "result": sub_result,
                })
            except Exception as exc:
                logger.exception("sub task %s failed", job_key)
                await jss.mark_finished(trade_date_val, job_key, "failed",
                    error_code="EXCEPTION", error_message=str(exc)[:200])
                job_results.append({"job_key": job_key, "status": "failed", "error": str(exc)[:200]})

        after = await rs.check(trade_date_val)
        after_dict = after.to_dict()

        if after.status == "ready":
            await jss.mark_finished(trade_date_val, "post_market_derived_data", "success",
                diagnostics={"before": before_dict, "after": after_dict, "job_results": job_results})
            return DerivedDataResult(
                trade_date=trade_date_val.isoformat(), status="success",
                before_readiness=before_dict, after_readiness=after_dict, job_results=job_results,
            )

        await jss.mark_finished(trade_date_val, "post_market_derived_data", "failed_precondition",
            error_code="POST_MARKET_DERIVED_DATA_NOT_READY",
            diagnostics={"before": before_dict, "after": after_dict, "job_results": job_results})
        return DerivedDataResult(
            trade_date=trade_date_val.isoformat(), status="failed_precondition",
            before_readiness=before_dict, after_readiness=after_dict, job_results=job_results,
            missing_tables=after.missing_tables,
        )


class _NoOpIdempotencyPort:
    """P2-2: 简易幂等端口，derived-data/generate 允许重复执行。"""
    async def acquire_job_idempotency(self, job_key: str, ttl_seconds: int) -> bool:
        return True
    async def mark_job_completed(self, job_key: str, metadata=None) -> None:
        pass


class _ThemeCycleTruthBuilder:

    def __init__(self, pool=None, db_manager=None):
        self._pool = pool
        self._db_manager = db_manager

    async def run(self, trade_date: date) -> dict[str, Any]:
        batch_id = str(uuid.uuid4())[:8]
        trace_id = str(uuid.uuid4())
        step_results: list[dict[str, Any]] = []
        idem = _NoOpIdempotencyPort()

        if self._db_manager is None:
            return {"job_key": "theme_cycle_truth", "status": "failed_precondition",
                    "error": "no_db_manager"}

        db = self._db_manager

        # Step 1: evidence
        try:
            from stock_processing_service.application.jobs.build_theme_cycle_evidence_daily_job import (
                BuildThemeCycleEvidenceDailyJob,
            )
            job = BuildThemeCycleEvidenceDailyJob(
                read_port=db, write_port=db, event_port=db, idempotency_port=idem)
            r = await job.execute(trade_date=trade_date,
                snapshot_version=f"derived_evidence.{trade_date.isoformat()}",
                batch_id=batch_id, trace_id=trace_id)
            step_results.append({"step": "evidence", "status": r.status, "affected_rows": r.affected_rows})
        except Exception as e:
            step_results.append({"step": "evidence", "status": "failed", "error": str(e)[:200]})

        # Step 2: cycle_judgement (no idempotency_port param)
        try:
            from stock_processing_service.application.jobs.build_cycle_judgement_job import (
                BuildCycleJudgementJob,
            )
            job = BuildCycleJudgementJob(read_port=db, write_port=db, event_port=db)
            r = await job.execute(trade_date=trade_date, batch_id=batch_id, trace_id=trace_id)
            step_results.append({"step": "cycle_judgement", "status": r.status, "affected_rows": r.affected_rows})
        except Exception as e:
            step_results.append({"step": "cycle_judgement", "status": "failed", "error": str(e)[:200]})

        # Step 3: identity
        try:
            from stock_processing_service.application.jobs.build_identity_job import (
                BuildIdentityJob,
            )
            job = BuildIdentityJob(read_port=db, write_port=db, event_port=db, idempotency_port=idem)
            r = await job.execute(trade_date=trade_date,
                snapshot_version="derived_identity.v1", batch_id=batch_id, trace_id=trace_id)
            step_results.append({"step": "identity", "status": r.status, "affected_rows": r.affected_rows})
        except Exception as e:
            step_results.append({"step": "identity", "status": "failed", "error": str(e)[:200]})

        # Step 4: cycle_judgement refresh
        try:
            from stock_processing_service.application.jobs.build_cycle_judgement_job import (
                BuildCycleJudgementJob,
            )
            job = BuildCycleJudgementJob(read_port=db, write_port=db, event_port=db)
            r = await job.execute(trade_date=trade_date, batch_id=batch_id, trace_id=trace_id)
            step_results.append({"step": "cycle_refresh", "status": r.status, "affected_rows": r.affected_rows})
        except Exception as e:
            step_results.append({"step": "cycle_refresh", "status": "failed", "error": str(e)[:200]})

        # Step 5: mainline_state (no idempotency_port param)
        try:
            from stock_processing_service.application.jobs.build_mainline_state_job import (
                BuildMainlineStateJob,
            )
            job = BuildMainlineStateJob(read_port=db, write_port=db, event_port=db)
            r = await job.execute(trade_date=trade_date, batch_id=batch_id, trace_id=trace_id)
            step_results.append({"step": "mainline_state", "status": r.status, "affected_rows": r.affected_rows})
        except Exception as e:
            step_results.append({"step": "mainline_state", "status": "failed", "error": str(e)[:200]})

        # Verify final table
        row_count = 0
        if self._pool:
            async with self._pool.acquire() as conn:
                r = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM theme_cycle_judgement_v2 WHERE trade_date = $1::date",
                    trade_date)
                row_count = int(r["cnt"]) if r else 0

        if row_count > 0:
            return {"job_key": "theme_cycle_truth", "status": "success",
                    "affected_rows": row_count, "step_results": step_results}
        return {"job_key": "theme_cycle_truth", "status": "failed_no_rows",
                "affected_rows": 0, "step_results": step_results,
                "error": "theme_cycle_judgement_v2 rows=0"}

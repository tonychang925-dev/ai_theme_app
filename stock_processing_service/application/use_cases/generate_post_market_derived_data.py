"""P2-1/P2-2: 每日动态复盘派生数据生成 UseCase。

总编排：按顺序执行 theme_cycle_truth → dragon_tiger_object_build →
hot_money_activity_build → theme_leader_candidate_build →
money_flow_enhanced_build → stock_abnormal_signal_build → strong_stock_watch_build。
每个子任务统一写 post_market_job_status，执行前后记录 readiness。

P2-2: theme_cycle_truth builder 已接入 A/B layer jobs。
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SUB_TASK_ORDER = [
    ("theme_cycle_truth",             "theme_cycle_truth_build"),
    ("dragon_tiger_object_build",      "dragon_tiger_object_build"),
    ("hot_money_activity_build",       "hot_money_activity_build"),
    ("theme_leader_candidate_build",   "theme_leader_candidate_build"),
    ("money_flow_enhanced_build",      "money_flow_enhanced_build"),
    ("stock_abnormal_signal_build",    "stock_abnormal_signal_build"),
    ("strong_stock_watch_build",       "strong_stock_watch_build"),
]

REQUIRED_TASKS = {
    "theme_cycle_truth",
    "theme_leader_candidate_build",
    "money_flow_enhanced_build",
    "strong_stock_watch_build",
}

DEPENDENT_TASKS_BY_FAILURE = {
    "theme_cycle_truth": [
        "theme_leader_candidate_build",
        "money_flow_enhanced_build",
        "stock_abnormal_signal_build",
        "strong_stock_watch_build",
    ],
    "theme_leader_candidate_build": [
        "money_flow_enhanced_build",
        "stock_abnormal_signal_build",
        "strong_stock_watch_build",
    ],
    "money_flow_enhanced_build": [
        "stock_abnormal_signal_build",
        "strong_stock_watch_build",
    ],
}

FORCE_REBUILD_TABLES = [
    "strong_stock_watch_history",
    "stock_abnormal_signal",
    "money_flow_enhanced",
    "theme_leader_candidate",
    "dragon_tiger_object",
    "hot_money_trading_activity",
    "mainline_state_transition",
    "mainline_state_daily",
    "theme_cycle_judgement_v2",
    "theme_cycle_evidence_daily",
]

SUB_TASK_TIMEOUT_SEC = int(os.getenv("POST_MARKET_DERIVED_SUBTASK_TIMEOUT_SEC", "45"))
SCRIPT_TASK_TIMEOUT_SEC = int(os.getenv("POST_MARKET_DERIVED_SCRIPT_TIMEOUT_SEC", "45"))


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

    def register_dragon_tiger_object_build(self) -> None:
        self._builders["dragon_tiger_object_build"] = _DragonTigerObjectBuilder(
            pool=self._pool, db_manager=self._db_manager)

    def register_hot_money_activity_build(self, project_root: str = "") -> None:
        self._builders["hot_money_activity_build"] = _HotMoneyActivityBuilder(
            pool=self._pool, project_root=project_root)

    def register_theme_leader_candidate_build(self, project_root: str = "") -> None:
        self._builders["theme_leader_candidate_build"] = _ThemeLeaderCandidateBuilder(
            pool=self._pool, project_root=project_root)

    def register_money_flow_enhanced_build(self, project_root: str = "") -> None:
        self._builders["money_flow_enhanced_build"] = _MoneyFlowEnhancedBuilder(
            pool=self._pool, project_root=project_root)

    def register_stock_abnormal_signal_build(self, project_root: str = "") -> None:
        self._builders["stock_abnormal_signal_build"] = _StockAbnormalSignalBuilder(
            pool=self._pool, db_manager=self._db_manager, project_root=project_root)

    def register_strong_stock_watch_build(self) -> None:
        self._builders["strong_stock_watch_build"] = _StrongStockWatchBuilder(
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

        await jss.mark_running(trade_date_val, "post_market_derived_data")
        before = await rs.check(trade_date_val)
        before_dict = before.to_dict()

        job_results: list[dict[str, Any]] = []
        if force and not dry_run:
            cleanup = await self._cleanup_force_rebuild_rows(trade_date_val)
            job_results.append(cleanup)

        skipped_jobs: set[str] = set()
        for job_key, _builder_key in SUB_TASK_ORDER:
            if job_key in skipped_jobs:
                continue
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

            await jss.mark_running(trade_date_val, job_key)
            sub_result: dict[str, Any]
            try:
                sub_result = await asyncio.wait_for(
                    builder.run(trade_date_val),
                    timeout=SUB_TASK_TIMEOUT_SEC,
                )
                sub_status = sub_result.get("status", "failed")
                sub_rows = sub_result.get("affected_rows", 0)
                await jss.mark_finished(trade_date_val, job_key, sub_status,
                    error_code=sub_result.get("error_code"),
                    error_message=sub_result.get("error") or sub_result.get("message"),
                    diagnostics={"affected_rows": sub_rows, "result": sub_result})
                job_results.append({
                    "job_key": job_key, "status": sub_status, "affected_rows": sub_rows,
                    "result": sub_result,
                })
            except asyncio.TimeoutError:
                logger.exception("sub task %s timed out", job_key)
                await jss.mark_finished(trade_date_val, job_key, "failed",
                    error_code="TIMEOUT",
                    error_message=f"sub task timed out after {SUB_TASK_TIMEOUT_SEC}s")
                sub_result = {
                    "job_key": job_key,
                    "status": "failed",
                    "error_code": "TIMEOUT",
                    "error": f"sub task timed out after {SUB_TASK_TIMEOUT_SEC}s",
                }
                job_results.append(sub_result)
            except Exception as exc:
                logger.exception("sub task %s failed", job_key)
                await jss.mark_finished(trade_date_val, job_key, "failed",
                    error_code="EXCEPTION", error_message=str(exc)[:200])
                sub_result = {"job_key": job_key, "status": "failed", "error": str(exc)[:200]}
                job_results.append(sub_result)

            sub_status = str(sub_result.get("status") or "failed")
            if job_key in REQUIRED_TASKS and sub_status != "success":
                dependent_jobs = [
                    key for key in DEPENDENT_TASKS_BY_FAILURE.get(job_key, [])
                    if key not in skipped_jobs
                ]
                for dependent_job in dependent_jobs:
                    skipped_jobs.add(dependent_job)
                    if not dry_run:
                        await jss.mark_finished(
                            trade_date_val,
                            dependent_job,
                            "failed_precondition",
                            error_code="UPSTREAM_TASK_FAILED",
                            error_message=f"upstream {job_key} status={sub_status}",
                            diagnostics={"upstream_job_key": job_key, "upstream_result": sub_result},
                        )
                    job_results.append({
                        "job_key": dependent_job,
                        "status": "failed_precondition",
                        "affected_rows": 0,
                        "error_code": "UPSTREAM_TASK_FAILED",
                        "error": f"upstream {job_key} status={sub_status}",
                    })

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

    async def _cleanup_force_rebuild_rows(self, trade_date_val: date) -> dict[str, Any]:
        if self._pool is None:
            return {
                "job_key": "force_rebuild_cleanup",
                "status": "skipped",
                "error": "no_db_pool",
            }

        deleted: dict[str, int | None] = {}
        errors: dict[str, str] = {}
        async with self._pool.acquire() as conn:
            for table_name in FORCE_REBUILD_TABLES:
                try:
                    result = await conn.execute(
                        f"DELETE FROM {table_name} WHERE trade_date = $1::date",
                        trade_date_val,
                    )
                    try:
                        deleted[table_name] = int(str(result).split()[-1])
                    except Exception:
                        deleted[table_name] = None
                except Exception as exc:
                    errors[table_name] = str(exc)[:200]

        return {
            "job_key": "force_rebuild_cleanup",
            "status": "success" if not errors else "partial",
            "affected_rows": sum(value or 0 for value in deleted.values()),
            "deleted": deleted,
            "errors": errors,
        }


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


class _DragonTigerObjectBuilder:
    """P2-3: dragon_tiger_object_build — 调用现有的 BuildDragonTigerObjectJob。"""

    def __init__(self, pool=None, db_manager=None):
        self._pool = pool
        self._db_manager = db_manager

    async def run(self, trade_date: date) -> dict[str, Any]:
        if self._db_manager is None:
            return {"job_key": "dragon_tiger_object_build", "status": "failed_precondition",
                    "error": "no_db_manager"}

        import os
        try:
            from stock_processing_service.application.jobs.build_dragon_tiger_object_job import (
                BuildDragonTigerObjectJob,
            )
            token = os.environ.get("TUSHARE_TOKEN", "")
            job = BuildDragonTigerObjectJob(write_port=self._db_manager)
            result = await job.execute(trade_date=trade_date, tushare_token=token, allow_fetch=False)

            # Check object rows
            row_count = 0
            if self._pool:
                async with self._pool.acquire() as conn:
                    r = await conn.fetchrow(
                        "SELECT COUNT(*) AS cnt FROM dragon_tiger_object WHERE trade_date = $1::date",
                        trade_date)
                    row_count = int(r["cnt"]) if r else 0

            if row_count > 0:
                return {"job_key": "dragon_tiger_object_build", "status": "success",
                        "affected_rows": row_count}
            if result.affected_rows > 0:
                return {"job_key": "dragon_tiger_object_build", "status": "failed_no_rows",
                        "affected_rows": 0, "error_code": "DRAGON_TIGER_OBJECT_NO_ROWS",
                        "error": "dragon_tiger_object rows=0 after source rows were normalized",
                        "warnings": result.warnings, "metrics": result.metrics}
            warnings = list(result.warnings or [])
            metrics = dict(result.metrics or {})
            if any("payload is empty" in warning for warning in warnings):
                return {"job_key": "dragon_tiger_object_build", "status": "skipped_no_data",
                        "affected_rows": 0,
                        "error_code": "DRAGON_TIGER_RAW_SNAPSHOT_EMPTY",
                        "error": "dragon_tiger raw snapshots exist but payload is empty",
                        "warnings": warnings, "metrics": metrics}
            if any("snapshot unavailable" in warning for warning in warnings):
                return {"job_key": "dragon_tiger_object_build", "status": "skipped_no_data",
                        "affected_rows": 0,
                        "error_code": "DRAGON_TIGER_RAW_SNAPSHOT_UNAVAILABLE",
                        "error": "dragon_tiger raw snapshot unavailable",
                        "warnings": warnings, "metrics": metrics}
            return {"job_key": "dragon_tiger_object_build", "status": "skipped_no_data",
                    "affected_rows": 0,
                    "error_code": "DRAGON_TIGER_OBJECT_EMPTY",
                    "error": "dragon_tiger object build produced no rows",
                    "warnings": warnings, "metrics": metrics}
        except Exception as exc:
            return {"job_key": "dragon_tiger_object_build", "status": "failed",
                    "affected_rows": 0, "error": str(exc)[:200]}


class _HotMoneyActivityBuilder:
    """P2-3: hot_money_activity_build — 调用现有的 build_hot_money_trading_activity.py。"""

    def __init__(self, pool=None, project_root: str = ""):
        self._pool = pool
        self._project_root = project_root

    async def run(self, trade_date: date) -> dict[str, Any]:
        script = Path(self._project_root) / "database_service/scripts/build_hot_money_trading_activity.py"
        if not script.exists():
            return {"job_key": "hot_money_activity_build", "status": "failed_precondition",
                    "error": f"script not found: {script}"}

        td_str = trade_date.isoformat()
        token = os.environ.get("TUSHARE_TOKEN", "")
        argv = [sys.executable, str(script), "--trade-date", td_str, "--no-fetch"]
        if token:
            argv.extend(["--token", token])
        proc_result = await _run_subprocess(argv, timeout_sec=SCRIPT_TASK_TIMEOUT_SEC)
        exit_code = proc_result["returncode"]

        row_count = 0
        if self._pool:
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM hot_money_trading_activity WHERE trade_date = $1::date",
                    trade_date,
                )
                row_count = int(row["cnt"]) if row else 0

        if row_count > 0:
            return {"job_key": "hot_money_activity_build", "status": "success", "affected_rows": row_count}
        if (exit_code or 0) == 0:
            return {
                "job_key": "hot_money_activity_build",
                "status": "skipped_no_data",
                "affected_rows": 0,
                "error_code": "HOT_MONEY_ACTIVITY_EMPTY",
                "error": "hot_money_trading_activity rows=0 after source rows were normalized",
                "diagnostics": proc_result,
            }
        return {
            "job_key": "hot_money_activity_build",
            "status": "failed",
            "affected_rows": 0,
            "error": f"hot_money_activity exit_code={exit_code}",
            "diagnostics": proc_result,
        }


class _ThemeLeaderCandidateBuilder:
    """P2-4a: theme_leader_candidate_build — 执行 build_theme_leader_candidate.py。"""

    def __init__(self, pool=None, project_root: str = ""):
        self._pool = pool
        self._project_root = project_root

    async def run(self, trade_date: date) -> dict[str, Any]:
        import asyncio
        script = Path(self._project_root) / "database_service/scripts/build_theme_leader_candidate.py"
        if not script.exists():
            return {"job_key": "theme_leader_candidate_build", "status": "failed_precondition",
                    "error": f"script not found: {script}"}
        td_str = trade_date.isoformat()
        try:
            proc_result = await _run_subprocess(
                [sys.executable, str(script), "--trade-date", td_str],
                timeout_sec=SCRIPT_TASK_TIMEOUT_SEC,
            )
        except Exception as exc:
            return {"job_key": "theme_leader_candidate_build", "status": "failed",
                    "affected_rows": 0, "error": str(exc)[:200]}

        row_count = 0
        if self._pool:
            async with self._pool.acquire() as conn:
                r = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM theme_leader_candidate WHERE trade_date = $1::date", trade_date)
                row_count = int(r["cnt"]) if r else 0
        if row_count > 0:
            return {"job_key": "theme_leader_candidate_build", "status": "success", "affected_rows": row_count}
        stderr_text = str(proc_result.get("stderr") or "").strip()
        stdout_text = str(proc_result.get("stdout") or "").strip()
        error_text = stderr_text or stdout_text or "theme_leader_candidate rows=0"
        return {"job_key": "theme_leader_candidate_build", "status": "failed_no_rows",
                "affected_rows": 0, "error": error_text[:500],
                "diagnostics": {"exit_code": proc_result.get("returncode"), **proc_result}}


class _MoneyFlowEnhancedBuilder:
    """P2-4: money_flow_enhanced_build — 执行 build_money_flow_enhanced.py 脚本。"""

    def __init__(self, pool=None, project_root: str = ""):
        self._pool = pool
        self._project_root = project_root

    async def run(self, trade_date: date) -> dict[str, Any]:
        import asyncio

        # Precondition: theme_leader_candidate must have data
        lc_count = 0
        if self._pool:
            async with self._pool.acquire() as conn:
                r = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM theme_leader_candidate WHERE trade_date = $1::date", trade_date)
                lc_count = int(r["cnt"]) if r else 0
        if lc_count == 0:
            return {"job_key": "money_flow_enhanced_build", "status": "failed_precondition",
                    "error_code": "MONEY_FLOW_INPUT_LEADER_CANDIDATE_EMPTY",
                    "affected_rows": 0, "error": "theme_leader_candidate is empty"}

        script = Path(self._project_root) / "database_service/scripts/build_money_flow_enhanced.py"
        if not script.exists():
            return {"job_key": "money_flow_enhanced_build", "status": "failed_precondition",
                    "error": f"script not found: {script}"}

        td_str = trade_date.isoformat()
        try:
            proc_result = await _run_subprocess(
                [sys.executable, str(script), "--trade-date", td_str],
                timeout_sec=SCRIPT_TASK_TIMEOUT_SEC,
            )
        except Exception as exc:
            return {"job_key": "money_flow_enhanced_build", "status": "failed",
                    "affected_rows": 0, "error": str(exc)[:200]}

        row_count = 0
        if self._pool:
            async with self._pool.acquire() as conn:
                r = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM money_flow_enhanced WHERE trade_date = $1::date", trade_date)
                row_count = int(r["cnt"]) if r else 0

        if row_count > 0:
            return {"job_key": "money_flow_enhanced_build", "status": "success", "affected_rows": row_count}
        return {"job_key": "money_flow_enhanced_build", "status": "failed_no_rows",
                "affected_rows": 0, "error": f"exit={proc_result.get('returncode')}",
                "diagnostics": proc_result}


class _StockAbnormalSignalBuilder:
    """P2-6: stock_abnormal_signal_build — 通过 Gateway Job 读取 DB 真源。"""

    def __init__(self, pool=None, db_manager=None, project_root: str = ""):
        self._pool = pool
        self._db_manager = db_manager
        self._project_root = project_root

    async def run(self, trade_date: date) -> dict[str, Any]:
        if self._db_manager is None:
            return {"job_key": "stock_abnormal_signal_build", "status": "failed_precondition",
                    "error": "no_db_manager"}
        try:
            from stock_processing_service.application.jobs.build_stock_abnormal_signal_job import (
                BuildStockAbnormalSignalJob,
            )
            job = BuildStockAbnormalSignalJob(db_gateway=self._db_manager)
            result = await job.execute(trade_date=trade_date)
        except Exception as exc:
            return {"job_key": "stock_abnormal_signal_build", "status": "failed",
                    "affected_rows": 0, "error": str(exc)[:200]}

        row_count = int(getattr(result, "affected_rows", 0) or 0)
        status = str(getattr(result, "status", "") or "")
        if row_count > 0 or status in {"ok", "ok_no_signals"}:
            return {"job_key": "stock_abnormal_signal_build", "status": "success", "affected_rows": row_count}
        return {"job_key": "stock_abnormal_signal_build", "status": "failed_no_rows",
                "affected_rows": 0, "error": status or "stock_abnormal_signal rows=0"}


class _StrongStockWatchBuilder:
    """P2-5: strong_stock_watch_build — 调用 BuildStrongStockTrackingUseCase。"""

    def __init__(self, pool=None, db_manager=None):
        self._pool = pool
        self._db_manager = db_manager

    async def run(self, trade_date: date) -> dict[str, Any]:
        if self._db_manager is None:
            return {"job_key": "strong_stock_watch_build", "status": "failed_precondition",
                    "error": "no_db_manager"}

        # Precondition: money_flow must exist
        mf_count = 0
        if self._pool:
            async with self._pool.acquire() as conn:
                r = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM money_flow_enhanced WHERE trade_date = $1::date", trade_date)
                mf_count = int(r["cnt"]) if r else 0
        if mf_count == 0:
            return {"job_key": "strong_stock_watch_build", "status": "failed_precondition",
                    "error_code": "STRONG_STOCK_INPUT_MONEY_FLOW_EMPTY",
                    "affected_rows": 0, "error": "money_flow_enhanced is empty"}

        try:
            from stock_processing_service.application.use_cases.build_strong_stock_tracking import (
                BuildStrongStockTrackingUseCase,
            )
            uc = BuildStrongStockTrackingUseCase(
                read_ports=self._db_manager, write_ports=self._db_manager)
            result = await uc.execute(trade_date=trade_date, window_days=7, lookback_days=8)
        except Exception as exc:
            return {"job_key": "strong_stock_watch_build", "status": "failed",
                    "affected_rows": 0, "error": str(exc)[:200]}

        row_count = 0
        if self._pool:
            async with self._pool.acquire() as conn:
                r = await conn.fetchrow(
                    "SELECT COUNT(*) AS cnt FROM strong_stock_watch_history WHERE trade_date = $1::date", trade_date)
                row_count = int(r["cnt"]) if r else 0

        metrics = result.metrics or {}
        diag = {
            "candidate_count": metrics.get("candidate_count", 0),
            "promote_count": metrics.get("promote_count", 0),
            "prune_count": metrics.get("prune_count", 0),
            "history_written": metrics.get("history_written", 0),
            "pool_written": metrics.get("pool_written", 0),
        }

        if row_count > 0:
            return {"job_key": "strong_stock_watch_build", "status": "success",
                    "affected_rows": row_count, "diagnostics": diag}
        return {"job_key": "strong_stock_watch_build", "status": "failed_no_rows",
                "affected_rows": 0, "diagnostics": diag, "error": "strong_stock_watch_history rows=0"}


async def _run_subprocess(argv: list[str], *, timeout_sec: int) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
    except asyncio.TimeoutError:
        proc.kill()
        stdout, stderr = await proc.communicate()
        return {
            "returncode": proc.returncode,
            "timeout": True,
            "timeout_sec": timeout_sec,
            "stdout": (stdout or b"").decode("utf-8", errors="replace")[-1000:],
            "stderr": (stderr or b"").decode("utf-8", errors="replace")[-1000:],
            "argv": _sanitize_argv(argv),
        }
    return {
        "returncode": proc.returncode,
        "timeout": False,
        "timeout_sec": timeout_sec,
        "stdout": (stdout or b"").decode("utf-8", errors="replace")[-1000:],
        "stderr": (stderr or b"").decode("utf-8", errors="replace")[-1000:],
        "argv": _sanitize_argv(argv),
    }


def _sanitize_argv(argv: list[str]) -> list[str]:
    sanitized: list[str] = []
    skip_next = False
    for idx, item in enumerate(argv):
        if skip_next:
            sanitized.append("***")
            skip_next = False
            continue
        sanitized.append(item)
        if item == "--token" and idx + 1 < len(argv):
            skip_next = True
    return sanitized

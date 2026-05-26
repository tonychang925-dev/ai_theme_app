"""P2-1: 每日动态复盘派生数据生成 UseCase。

总编排：按顺序执行 theme_cycle_truth → dragon_tiger_object_build →
money_flow_enhanced_build → stock_abnormal_signal_build → strong_stock_watch_build。
每个子任务统一写 post_market_job_status，执行前后记录 readiness。
"""
from __future__ import annotations

import logging
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
    status: str  # success | failed_precondition | failed
    before_readiness: dict[str, Any] = field(default_factory=dict)
    after_readiness: dict[str, Any] = field(default_factory=dict)
    job_results: list[dict[str, Any]] = field(default_factory=list)
    missing_tables: list[str] = field(default_factory=list)
    error_message: str = ""


class PostMarketDerivedDataGenerateUseCase:
    """P2-1: 盘后复盘派生数据生成总编排。"""

    def __init__(self, pool=None):
        self._pool = pool
        self._builders: dict[str, Any] = {}

    def register_builder(self, job_key: str, builder):
        """注册子任务 builder。builder 需实现 async run(trade_date) -> dict。"""
        self._builders[job_key] = builder

    async def execute(
        self,
        trade_date_val: date,
        force: bool = False,
        dry_run: bool = False,
    ) -> DerivedDataResult:
        from stock_processing_service.application.services.post_market_readiness_service import (
            PostMarketReadinessService,
        )
        from stock_processing_service.application.services.post_market_job_status_service import (
            PostMarketJobStatusService,
        )

        jss = PostMarketJobStatusService(pool=self._pool)
        rs = PostMarketReadinessService(pool=self._pool)

        # 1. mark running
        await jss.mark_finished(trade_date_val, "post_market_derived_data", "running")

        # 2. before readiness
        before = await rs.check(trade_date_val)
        before_dict = before.to_dict()

        # 3. 执行子任务
        job_results: list[dict[str, Any]] = []
        for job_key, builder_key in SUB_TASK_ORDER:
            builder = self._builders.get(job_key)
            if builder is None:
                logger.warning("P2 builder not wired: %s", job_key)
                if not dry_run:
                    await jss.mark_finished(trade_date_val, job_key, "failed_precondition",
                        error_code="BUILDER_NOT_WIRED",
                        error_message=f"builder not registered for {job_key}")
                job_results.append({
                    "job_key": job_key,
                    "status": "not_wired",
                    "message": f"builder not registered for {job_key}",
                })
                continue

            await jss.mark_finished(trade_date_val, job_key, "running")
            try:
                sub_result = await builder.run(trade_date_val)
                sub_status = sub_result.get("status", "failed")
                sub_rows = sub_result.get("affected_rows", 0)
                await jss.mark_finished(trade_date_val, job_key, sub_status,
                    diagnostics={"affected_rows": sub_rows, "result": sub_result})
                job_results.append({
                    "job_key": job_key,
                    "status": sub_status,
                    "affected_rows": sub_rows,
                })
            except Exception as exc:
                logger.exception("sub task %s failed", job_key)
                await jss.mark_finished(trade_date_val, job_key, "failed",
                    error_code="EXCEPTION",
                    error_message=str(exc)[:200])
                job_results.append({
                    "job_key": job_key,
                    "status": "failed",
                    "error": str(exc)[:200],
                })

        # 4. after readiness
        after = await rs.check(trade_date_val)
        after_dict = after.to_dict()

        # 5. 终态判定
        if after.status == "ready":
            await jss.mark_finished(trade_date_val, "post_market_derived_data", "success",
                diagnostics={"before_readiness": before_dict, "after_readiness": after_dict, "job_results": job_results})
            return DerivedDataResult(
                trade_date=trade_date_val.isoformat(),
                status="success",
                before_readiness=before_dict,
                after_readiness=after_dict,
                job_results=job_results,
            )

        await jss.mark_finished(trade_date_val, "post_market_derived_data", "failed_precondition",
            error_code="POST_MARKET_DERIVED_DATA_NOT_READY",
            diagnostics={"before_readiness": before_dict, "after_readiness": after_dict, "job_results": job_results})
        return DerivedDataResult(
            trade_date=trade_date_val.isoformat(),
            status="failed_precondition",
            before_readiness=before_dict,
            after_readiness=after_dict,
            job_results=job_results,
            missing_tables=after.missing_tables,
        )

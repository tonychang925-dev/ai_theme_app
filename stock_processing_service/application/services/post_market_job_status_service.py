"""P1-3: 盘后复盘任务状态服务。

统一记录每日复盘各阶段任务状态，前端和调度层不再靠日志判断。
提供 mark_running / mark_finished / list_by_date 最小接口。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

VALID_STATUSES = frozenset({
    "pending",
    "running",
    "success",
    "failed_precondition",
    "failed_no_rows",
    "skipped_no_data",
    "failed",
})


class PostMarketJobStatusService:
    """盘后复盘任务状态服务。"""

    def __init__(self, pool=None):
        self._pool = pool

    def _validate_status(self, status: str) -> None:
        if status not in VALID_STATUSES:
            raise ValueError(f"invalid status: {status}, must be one of {sorted(VALID_STATUSES)}")

    async def _ensure_pool(self):
        if self._pool is None:
            raise RuntimeError("PostMarketJobStatusService: no db pool configured")

    async def mark_running(
        self,
        trade_date_val: date,
        job_key: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        """标记任务开始执行。"""
        self._validate_status("running")
        await self._ensure_pool()
        diag_json = __import__("json").dumps(diagnostics or {})
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO post_market_job_status (
                    trade_date, job_key, status, started_at, finished_at,
                    error_code, error_message, diagnostics, updated_at
                ) VALUES ($1, $2, 'running', now(), null, null, null, $3::jsonb, now())
                ON CONFLICT (trade_date, job_key) DO UPDATE SET
                    status = 'running',
                    started_at = coalesce(post_market_job_status.started_at, now()),
                    finished_at = null,
                    error_code = null,
                    error_message = null,
                    diagnostics = excluded.diagnostics,
                    updated_at = now()
                """,
                trade_date_val,
                job_key,
                diag_json,
            )

    async def mark_finished(
        self,
        trade_date_val: date,
        job_key: str,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> None:
        """标记任务完成。"""
        self._validate_status(status)
        await self._ensure_pool()
        diag_json = __import__("json").dumps(diagnostics or {})
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO post_market_job_status (
                    trade_date, job_key, status, started_at, finished_at,
                    error_code, error_message, diagnostics, updated_at
                ) VALUES ($1, $2, $3, now(), now(), $4, $5, $6::jsonb, now())
                ON CONFLICT (trade_date, job_key) DO UPDATE SET
                    status = excluded.status,
                    finished_at = now(),
                    error_code = excluded.error_code,
                    error_message = excluded.error_message,
                    diagnostics = excluded.diagnostics,
                    updated_at = now()
                """,
                trade_date_val,
                job_key,
                status,
                error_code,
                error_message,
                diag_json,
            )

    async def list_by_date(self, trade_date_val: date) -> list[dict[str, Any]]:
        """查询指定日期的所有任务状态。"""
        await self._ensure_pool()
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT job_key, status, started_at, finished_at,
                       error_code, error_message, diagnostics
                FROM post_market_job_status
                WHERE trade_date = $1
                ORDER BY job_key
                """,
                trade_date_val,
            )
        items = []
        for r in rows:
            items.append({
                "job_key": r["job_key"],
                "status": r["status"],
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "finished_at": r["finished_at"].isoformat() if r["finished_at"] else None,
                "error_code": r["error_code"] or None,
                "error_message": r["error_message"] or None,
                "diagnostics": r["diagnostics"] or {},
            })
        return items

    async def summary_by_date(self, trade_date_val: date) -> dict[str, Any]:
        """查询指定日期的状态摘要。"""
        items = await self.list_by_date(trade_date_val)
        has_running = any(it["status"] == "running" for it in items)
        has_failed = any(it["status"] in ("failed_precondition", "failed", "failed_no_rows") for it in items)
        all_success = len(items) > 0 and all(it["status"] == "success" for it in items)
        latest = sorted(items, key=lambda x: x.get("finished_at") or "", reverse=True)
        return {
            "trade_date": trade_date_val.isoformat(),
            "items": items,
            "summary": {
                "has_running": has_running,
                "has_failed": has_failed,
                "all_success": all_success,
                "latest_status": latest[0]["status"] if latest else "unknown",
            },
        }

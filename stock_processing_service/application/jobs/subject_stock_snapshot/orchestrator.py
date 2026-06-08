"""统一编排入口 — 前端不直接感知具体 Producer.

入口: stock_snapshot.build
  provider=jyhf          → JyhfSubjectStockDailySnapshotProducer
  provider=tushare_join  → TushareJoinSubjectStockDailySnapshotProducer

force 与 on_existing 优先级:
  force=true → on_existing=replace (由 Request.resolved_on_existing() 处理)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from stock_processing_service.application.jobs.subject_stock_snapshot.base import (
    SubjectStockSnapshotBuildRequest,
    SubjectStockSnapshotBuildResult,
)
from stock_processing_service.application.jobs.subject_stock_snapshot.config import (
    SubjectStockSnapshotConfig,
    load_config,
)
from stock_processing_service.application.jobs.subject_stock_snapshot.factory import (
    SubjectStockSnapshotProducerFactory,
)

logger = logging.getLogger(__name__)


class SubjectStockDailySnapshotOrchestrator:
    """统一入口：根据配置选择 Producer 并执行.

    前端调用示例:
      orchestrator.execute(trade_date=date.today())
      orchestrator.execute(trade_date=date.today(), provider="tushare_join", on_existing="replace")
    """

    def __init__(
        self,
        factory: SubjectStockSnapshotProducerFactory,
        db_pool=None,
        config: SubjectStockSnapshotConfig | None = None,
    ):
        self._factory = factory
        self._db_pool = db_pool
        self._config = config or load_config()

    async def execute(
        self,
        trade_date: date,
        *,
        provider: str | None = None,
        force: bool = False,
        on_existing: str | None = None,
        batch_id: str | None = None,
    ) -> SubjectStockSnapshotBuildResult:
        selected_provider = provider or self._config.provider or "jyhf"
        resolved_on_existing = (
            on_existing
            or self._config.on_existing
            or "skip"
        )

        producer = self._factory.get(selected_provider)
        trade_date_str = trade_date.isoformat()

        request = SubjectStockSnapshotBuildRequest(
            trade_date=trade_date,
            force=force,
            batch_id=batch_id,
            provider=selected_provider,
            on_existing=resolved_on_existing,  # type: ignore[arg-type]
        )

        started_at = datetime.now()
        result = await producer.build(request)
        finished_at = datetime.now()

        # ── 写审计记录 ──
        await self._record_run(request, result, started_at, finished_at)

        return result

    async def _record_run(
        self,
        request: SubjectStockSnapshotBuildRequest,
        result: SubjectStockSnapshotBuildResult,
        started_at: datetime,
        finished_at: datetime,
    ) -> None:
        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO subject_stock_daily_snapshot_build_run
                       (trade_date, provider, batch_id, status, affected_rows,
                        on_existing, force_mode,
                        stock_daily_count, mapped_stock_count, matched_stock_count,
                        missing_stock_count, subject_count, covered_subject_count,
                        coverage_pct,
                        config_json, metrics_json, warnings_json,
                        started_at, finished_at)
                       VALUES ($1,$2,$3,$4,$5, $6,$7, $8,$9,$10, $11,$12,$13, $14, $15,$16,$17, $18,$19)""",
                    request.trade_date,
                    request.provider,
                    request.batch_id or "",
                    result.status,
                    result.affected_rows,
                    request.resolved_on_existing(),
                    request.force,
                    result.metrics.get("stock_daily_count"),
                    result.metrics.get("mapped_stock_count"),
                    result.metrics.get("matched_stock_count"),
                    result.metrics.get("missing_stock_count"),
                    result.metrics.get("subject_count"),
                    result.metrics.get("covered_subject_count"),
                    result.metrics.get("coverage_pct"),
                    json.dumps({
                        "provider": request.provider,
                        "on_existing": request.resolved_on_existing(),
                        "force": request.force,
                        "limit_up_rule": "pct_chg_9_8",
                        "rank_method": "pct_chg_desc",
                        "stock_id_format": "local_6digit",
                    }, ensure_ascii=False),
                    json.dumps(result.metrics, ensure_ascii=False),
                    json.dumps(result.warnings, ensure_ascii=False),
                    started_at,
                    finished_at,
                )
        except Exception:
            logger.exception("Failed to write build_run audit record")

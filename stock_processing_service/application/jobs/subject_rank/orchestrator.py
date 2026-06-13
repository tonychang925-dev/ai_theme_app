"""统一编排入口 — 前端不直接感知具体 Producer.

入口: subject_rank.build
  provider=jyhf          → JyhfSubjectRankProducer
  provider=snapshot_agg  → SnapshotAggSubjectRankProducer

force 与 on_existing 优先级:
  force=true → on_existing=replace (由 Request.resolved_on_existing() 处理)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from stock_processing_service.application.jobs.subject_rank.base import (
    SubjectRankBuildRequest,
    SubjectRankBuildResult,
)
from stock_processing_service.application.jobs.subject_rank.config import (
    SubjectRankConfig,
    load_config,
)
from stock_processing_service.application.jobs.subject_rank.factory import (
    SubjectRankProducerFactory,
)

logger = logging.getLogger(__name__)


class SubjectRankOrchestrator:
    """统一入口：根据配置选择 Producer 并执行.

    调用示例:
      orchestrator.execute(trade_date=date.today())
      orchestrator.execute(trade_date=date.today(), provider="snapshot_agg", on_existing="replace")
    """

    def __init__(
        self,
        factory: SubjectRankProducerFactory,
        db_pool=None,
        config: SubjectRankConfig | None = None,
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
    ) -> SubjectRankBuildResult:
        selected_provider = provider or self._config.provider or "jyhf"
        resolved_on_existing = (
            on_existing
            or self._config.on_existing
            or "skip"
        )

        producer = self._factory.get(selected_provider)
        trade_date_str = trade_date.isoformat()

        request = SubjectRankBuildRequest(
            trade_date=trade_date,
            force=force,
            batch_id=batch_id,
            provider=selected_provider,
            on_existing=resolved_on_existing,  # type: ignore[arg-type]
        )

        started_at = datetime.now()
        try:
            result = await producer.build(request)
        except Exception as exc:
            result = SubjectRankBuildResult(
                provider=selected_provider,
                trade_date=trade_date_str,
                status="failed",
                affected_rows=0,
                warnings=[f"unhandled exception: {type(exc).__name__}: {exc}"],
            )
        finished_at = datetime.now()

        await self._record_run(request, result, started_at, finished_at)

        return result

    async def _record_run(
        self,
        request: SubjectRankBuildRequest,
        result: SubjectRankBuildResult,
        started_at: datetime,
        finished_at: datetime,
    ) -> None:
        try:
            async with self._db_pool.acquire() as conn:
                await conn.execute(
                    """INSERT INTO subject_rank_daily_build_run
                       (trade_date, provider, batch_id, status, affected_rows,
                        on_existing, force_mode,
                        snapshot_subject_count, ranked_subject_count,
                        top100_count, missing_name_count,
                        avg_heat, max_heat, min_heat,
                        config_json, metrics_json, warnings_json,
                        started_at, finished_at)
                       VALUES ($1,$2,$3,$4,$5, $6,$7, $8,$9, $10,$11, $12,$13,$14, $15,$16,$17, $18,$19)""",
                    request.trade_date,
                    request.provider,
                    request.batch_id or "",
                    result.status,
                    result.affected_rows,
                    request.resolved_on_existing(),
                    request.force,
                    result.metrics.get("snapshot_subject_count"),
                    result.metrics.get("ranked_subject_count"),
                    result.metrics.get("top100_count"),
                    result.metrics.get("missing_name_count"),
                    result.metrics.get("avg_heat"),
                    result.metrics.get("max_heat"),
                    result.metrics.get("min_heat"),
                    json.dumps({
                        "provider": request.provider,
                        "on_existing": request.resolved_on_existing(),
                        "force": request.force,
                        "rank_method": "heat_desc",
                        "heat_formula": "v1",
                    }, ensure_ascii=False),
                    json.dumps(result.metrics, ensure_ascii=False),
                    json.dumps(result.warnings, ensure_ascii=False),
                    started_at,
                    finished_at,
                )
        except Exception:
            logger.exception("Failed to write subject_rank build_run audit record")

from __future__ import annotations

from dataclasses import asdict
from collections import defaultdict
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from stock_processing_service.application.projectors import (
    AbnormalEventProjector,
    DailySnapshotProjector,
    LeaderboardProjector,
)
from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import (
    AbnormalDetectedPayload,
    EventEnvelope,
    LeaderboardUpdatedPayload,
    SnapshotBuiltPayload,
)
from stock_processing_service.contracts.snapshots import (
    StockAbnormalEvent,
    StockDailySnapshot,
    SubjectStockDailySnapshot,
    ThemeStockLeaderboard,
)
from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidenceBuilder
from stock_processing_service.domain.services.cycle_judgement_service import CycleJudgementService
from stock_processing_service.domain.services.state_transition_service import StateTransitionService
from stock_processing_service.ports import (
    IdempotencyPort,
    StockCachePort,
    StockEventPort,
    StockReadPort,
    SnapshotWritePort,
)


class BuildDailySnapshotJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: SnapshotWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        cache_port: StockCachePort | None = None,
        evidence_builder: CycleEvidenceBuilder | None = None,
        judgement_service: CycleJudgementService | None = None,
        transition_service: StateTransitionService | None = None,
        daily_projector: DailySnapshotProjector | None = None,
        abnormal_projector: AbnormalEventProjector | None = None,
        leaderboard_projector: LeaderboardProjector | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._cache_port = cache_port
        self._evidence_builder = evidence_builder or CycleEvidenceBuilder()
        self._judgement_service = judgement_service or CycleJudgementService()
        self._transition_service = transition_service or StateTransitionService()
        self._daily_projector = daily_projector or DailySnapshotProjector()
        self._abnormal_projector = abnormal_projector or AbnormalEventProjector()
        self._leaderboard_projector = leaderboard_projector or LeaderboardProjector()

    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        lookback_days: int = 5,
    ) -> BuildResult:
        job_key = f"build_daily_snapshot:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_daily_snapshot",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
            )

        calendar = await self._read_port.get_trade_calendar(trade_date)
        if calendar is None or not calendar.calendar_is_open:
            await self._idempotency_port.mark_job_completed(job_key, {"reason": "market_closed"})
            return BuildResult(
                name="build_daily_snapshot",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="market_closed",
            )
        await self._cache_set(f"sps:calendar:{trade_date}", asdict(calendar), ttl_seconds=7 * 24 * 3600)

        bars = await self._read_port.get_stock_daily_bars(trade_date)
        pool_rows = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        subject_keys = sorted({row.subject_key for row in pool_rows})
        context_rows = await self._read_port.get_subject_context_by_subject_keys(subject_keys, trade_date) if subject_keys else []
        prior_rows = await self._read_port.get_prior_stock_daily_snapshots(
            trade_date=trade_date,
            lookback_days=lookback_days,
            stock_ids=[row.stock_id for row in pool_rows] if pool_rows else None,
        )

        await self._cache_set(f"sps:subject_pool:{trade_date}", [asdict(r) for r in pool_rows], ttl_seconds=4 * 3600)
        for ctx in context_rows:
            await self._cache_set(
                f"sps:subject_context:{trade_date}:{ctx.subject_key}",
                asdict(ctx),
                ttl_seconds=2 * 3600,
            )

        evidences = self._evidence_builder.build_evidences(bars, pool_rows, context_rows, prior_rows)
        judgements = self._judgement_service.judge_many(evidences)

        prior_state_by_stock: dict[str, str] = {
            row.stock_id: str(row.payload.get("final_cycle_state", "unknown")) for row in prior_rows
        }
        current_state_by_stock: dict[str, str] = {j.stock_id: j.final_cycle_state for j in judgements}
        transitions = self._transition_service.build_transitions(current_state_by_stock, prior_state_by_stock)
        transition_by_stock = {t.stock_id: t for t in transitions}

        bars_by_stock = {bar.stock_id: bar for bar in bars}
        daily_rows, subject_daily_rows = self._daily_projector.project(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
            evidences=evidences,
            judgements=judgements,
            bars_by_stock=bars_by_stock,
            transition_by_stock=transition_by_stock,
        )
        abnormal_rows = self._abnormal_projector.project(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
            evidences=evidences,
            judgements=judgements,
        )
        leaderboard_rows = self._leaderboard_projector.project(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
            judgements=judgements,
        )

        affected = 0
        affected += await self._write_port.upsert_stock_daily_snapshot_rows(daily_rows)
        affected += await self._write_port.upsert_subject_stock_daily_snapshot_rows(subject_daily_rows)
        affected += await self._write_port.upsert_stock_abnormal_event_rows(abnormal_rows)
        affected += await self._write_port.upsert_theme_stock_leaderboard_rows(leaderboard_rows)

        for row in daily_rows:
            await self._cache_set(
                f"sps:stock_daily_snapshot:{trade_date}:{row.stock_id}",
                asdict(row),
                ttl_seconds=24 * 3600,
            )
        leaderboard_by_subject: dict[str, list[ThemeStockLeaderboard]] = defaultdict(list)
        for row in leaderboard_rows:
            leaderboard_by_subject[row.subject_key].append(row)
        for subject_key, rows in leaderboard_by_subject.items():
            await self._cache_set(
                f"sps:theme_leaderboard:{trade_date}:{subject_key}",
                [asdict(r) for r in rows],
                ttl_seconds=24 * 3600,
            )
        await self._cache_set(
            f"sps:stock_daily_snapshot:current:{trade_date}",
            snapshot_version,
            ttl_seconds=24 * 3600,
        )

        occurred_at = datetime.now(timezone.utc)
        await self._event_port.publish_stock_processing_event(
            EventEnvelope(
                event_id=str(uuid4()),
                event_name="snapshot_built",
                trade_date=trade_date,
                batch_id=batch_id,
                trace_id=trace_id,
                producer="stock_processing_service",
                occurred_at=occurred_at,
                payload_version="v1",
                payload=SnapshotBuiltPayload(
                    domain="daily_snapshot",
                    snapshot_version=snapshot_version,
                    object_name="stock_daily_snapshot",
                    row_count=len(daily_rows),
                    success=True,
                ),
            )
        )

        if abnormal_rows:
            abnormal_by_stock: dict[str, int] = defaultdict(int)
            abnormal_types_by_stock: dict[str, set[str]] = defaultdict(set)
            for row in abnormal_rows:
                abnormal_by_stock[row.stock_id] += 1
                abnormal_types_by_stock[row.stock_id].add(row.event_type)
            for stock_id, row_count in abnormal_by_stock.items():
                await self._event_port.publish_stock_processing_event(
                    EventEnvelope(
                        event_id=str(uuid4()),
                        event_name="abnormal_detected",
                        trade_date=trade_date,
                        batch_id=batch_id,
                        trace_id=trace_id,
                        producer="stock_processing_service",
                        occurred_at=occurred_at,
                        payload_version="v1",
                        payload=AbnormalDetectedPayload(
                            stock_id=stock_id,
                            trade_date=trade_date,
                            event_types=sorted(abnormal_types_by_stock.get(stock_id, set())),
                            row_count=row_count,
                        ),
                    )
                )

        for subject_key, rows in leaderboard_by_subject.items():
            await self._event_port.publish_stock_processing_event(
                EventEnvelope(
                    event_id=str(uuid4()),
                    event_name="leaderboard_updated",
                    trade_date=trade_date,
                    batch_id=batch_id,
                    trace_id=trace_id,
                    producer="stock_processing_service",
                    occurred_at=occurred_at,
                    payload_version="v1",
                    payload=LeaderboardUpdatedPayload(
                        subject_key=subject_key,
                        trade_date=trade_date,
                        row_count=len(rows),
                        snapshot_version=snapshot_version,
                    ),
                )
            )

        await self._idempotency_port.mark_job_completed(
            job_key,
            {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "affected_rows": affected,
            },
        )

        return BuildResult(
            name="build_daily_snapshot",
            trade_date=trade_date.isoformat(),
            affected_rows=affected,
            status="ok",
        )

    async def _cache_set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._cache_port is None:
            return
        await self._cache_port.set(key, value, ttl_seconds=ttl_seconds)

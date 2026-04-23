from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.domain.services.identity_decider import IdentityDecider
from stock_processing_service.domain.services.identity_llm_review_service import IdentityLLMReviewService
from stock_processing_service.domain.services.identity_scoring_service import IdentityScoringService
from stock_processing_service.domain.services.one_day_tour_detector import OneDayTourDetector
from stock_processing_service.ports import IdempotencyPort, StockEventPort, StockReadPort, StockWritePort


class BuildIdentityJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: StockWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        scoring_service: IdentityScoringService | None = None,
        tour_detector: OneDayTourDetector | None = None,
        llm_review_service: IdentityLLMReviewService | None = None,
        decider: IdentityDecider | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._scoring_service = scoring_service or IdentityScoringService()
        self._tour_detector = tour_detector or OneDayTourDetector()
        self._llm_review_service = llm_review_service or IdentityLLMReviewService()
        self._decider = decider or IdentityDecider()

    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
    ) -> BuildResult:
        job_key = f"build_identity:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_identity",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
            )

        pool_rows = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        subject_keys = sorted({row.subject_key for row in pool_rows})
        contexts = await self._read_port.get_subject_context_by_subject_keys(subject_keys, trade_date) if subject_keys else []
        bars = await self._read_port.get_stock_daily_bars(trade_date)

        ctx_by_subject = {c.subject_key: c for c in contexts}
        bars_by_stock = {bar.stock_id: bar for bar in bars}

        identity_registry_rows: list[dict[str, Any]] = []
        review_queue_rows: list[dict[str, Any]] = []

        grouped: dict[str, list[Any]] = {}
        for row in pool_rows:
            grouped.setdefault(row.subject_key, []).append(row)

        for subject_key, rows in grouped.items():
            subject_name = rows[0].subject_name
            context_tags = list((ctx_by_subject.get(subject_key).theme_context_tags if subject_key in ctx_by_subject else []) or [])

            pct_values: list[Decimal] = []
            for row in rows:
                bar = bars_by_stock.get(row.stock_id)
                if bar is not None:
                    pct_values.append(bar.pct_chg)
            avg_pct = sum(pct_values, start=Decimal("0")) / Decimal(str(len(pct_values) or 1))

            score = self._scoring_service.score(
                subject_key=subject_key,
                subject_name=subject_name,
                context_tags=context_tags,
                stock_count=len(rows),
            )
            tour_signal = self._tour_detector.detect(avg_pct_chg=avg_pct, stock_count=len(rows))
            llm_verdict = self._llm_review_service.review(
                composite_score=score.composite_score,
                one_day_tour_flag=tour_signal.one_day_tour_flag,
            )
            decision = self._decider.decide(
                composite_score=score.composite_score,
                llm_verdict=llm_verdict.verdict,
                one_day_tour_flag=tour_signal.one_day_tour_flag,
            )

            identity_row = {
                "trade_date": trade_date.isoformat(),
                "subject_key": subject_key,
                "subject_name": subject_name,
                "logic_score": str(score.logic_score),
                "market_score": str(score.market_score),
                "composite_score": str(score.composite_score),
                "one_day_tour_flag": tour_signal.one_day_tour_flag,
                "continuity_signal": tour_signal.continuity_signal,
                "identity_status": decision.identity_status,
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
                "source_trace_id": trace_id,
            }
            identity_registry_rows.append(identity_row)

            if decision.identity_status == "review_pending":
                review_queue_rows.append(
                    {
                        "trade_date": trade_date.isoformat(),
                        "subject_key": subject_key,
                        "subject_name": subject_name,
                        "reason": decision.reason,
                        "llm_confidence": str(llm_verdict.confidence),
                        "snapshot_version": snapshot_version,
                        "batch_id": batch_id,
                        "trace_id": trace_id,
                    }
                )

        written_registry = await self._write_port.upsert_theme_mainline_identity_registry_rows(identity_registry_rows)
        written_review = await self._write_port.upsert_mainline_identity_review_queue_rows(review_queue_rows)

        await self._event_port.publish_stock_processing_event(
            EventEnvelope(
                event_id=str(uuid4()),
                event_name="snapshot_built",
                trade_date=trade_date,
                batch_id=batch_id,
                trace_id=trace_id,
                producer="stock_processing_service",
                occurred_at=datetime.now(timezone.utc),
                payload_version="v1",
                payload=SnapshotBuiltPayload(
                    domain="identity",
                    snapshot_version=snapshot_version,
                    object_name="theme_mainline_identity_registry",
                    row_count=written_registry,
                    success=True,
                ),
            )
        )

        await self._idempotency_port.mark_job_completed(
            job_key,
            {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "identity_rows": written_registry,
                "review_rows": written_review,
            },
        )

        return BuildResult(
            name="build_identity",
            trade_date=trade_date.isoformat(),
            affected_rows=written_registry + written_review,
            status="ok",
        )

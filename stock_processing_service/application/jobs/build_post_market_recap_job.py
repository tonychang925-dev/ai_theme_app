from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.contracts.snapshots import PostMarketRecapSnapshot
from stock_processing_service.domain.services.strong_watch_service import StrongWatchService
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService
from stock_processing_service.ports import (
    IdempotencyPort,
    StockCachePort,
    StockEventPort,
    StockReadPort,
    StockWritePort,
)


class BuildPostMarketRecapJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: StockWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        cache_port: StockCachePort | None = None,
        candidate_service: W2SCandidateService | None = None,
        strong_watch_service: StrongWatchService | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._cache_port = cache_port
        self._candidate_service = candidate_service or W2SCandidateService()
        self._strong_watch_service = strong_watch_service or StrongWatchService()

    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        lookback_days: int = 5,
    ) -> BuildResult:
        job_key = f"build_post_market_recap:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_post_market_recap",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
            )

        bars = await self._read_port.get_stock_daily_bars(trade_date)
        pool_rows = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        prior_rows = await self._read_port.get_prior_stock_daily_snapshots(
            trade_date=trade_date,
            lookback_days=lookback_days,
            stock_ids=[row.stock_id for row in pool_rows] if pool_rows else None,
        )

        promoted_pool_rows, strong_watch_rows = self._strong_watch_service.build_promoted_pool(
            trade_date=trade_date,
            pool_rows=pool_rows,
            bars=bars,
        )
        candidates = self._candidate_service.build_candidates(
            bars=bars,
            pool_rows=promoted_pool_rows,
            prior_rows=prior_rows,
        )

        recap_doc = {
            "trade_date": trade_date.isoformat(),
            "snapshot_version": snapshot_version,
            "candidate_source": "strong_watch_pool",
            "strong_watch_input_count": len(strong_watch_rows),
            "strong_watch_promoted_count": len(promoted_pool_rows),
            "candidate_count": len(candidates),
            "top_candidates": [
                {
                    "stock_id": c.stock_id,
                    "stock_name": c.stock_name,
                    "subject_key": c.subject_key,
                    "subject_name": c.subject_name,
                    "candidate_score": str(c.candidate_score),
                    "candidate_level": c.candidate_level,
                    "evidence_rules": c.evidence_rules,
                }
                for c in candidates[:30]
            ],
        }

        snapshot = PostMarketRecapSnapshot(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
            source_trace_id=trace_id,
            recap_doc=recap_doc,
        )

        affected = await self._write_port.upsert_post_market_recap_snapshot(snapshot)

        if self._cache_port is not None:
            await self._cache_port.set(
                f"sps:post_market_recap:{trade_date}",
                asdict(snapshot),
                ttl_seconds=24 * 3600,
            )
            await self._cache_port.set(
                f"sps:post_market_recap:current:{trade_date}",
                snapshot_version,
                ttl_seconds=24 * 3600,
            )

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
                    domain="post_market",
                    snapshot_version=snapshot_version,
                    object_name="post_market_recap_snapshot",
                    row_count=1,
                    success=True,
                ),
            )
        )

        await self._idempotency_port.mark_job_completed(
            job_key,
            {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "candidate_count": len(candidates),
            },
        )

        return BuildResult(
            name="build_post_market_recap",
            trade_date=trade_date.isoformat(),
            affected_rows=affected,
            status="ok",
        )

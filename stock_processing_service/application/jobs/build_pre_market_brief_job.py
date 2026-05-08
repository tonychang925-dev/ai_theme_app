from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
from uuid import uuid4

from stock_processing_service.application.cache import SnapshotCacheWriter
from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import ALL_REJECT_REASON_CODES
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.contracts.snapshots import PreMarketBriefSnapshot
from stock_processing_service.domain.services.w2s_auction_scorer import W2SAuctionScorer
from stock_processing_service.domain.services.w2s_candidate_service import W2SCandidateService
from stock_processing_service.domain.services.w2s_confirm_service import W2SConfirmService
from stock_processing_service.ports import (
    IdempotencyPort,
    StockCachePort,
    StockEventPort,
    StockReadPort,
    SnapshotWritePort,
)


class BuildPreMarketBriefJob:
    def __init__(
        self,
        read_port: StockReadPort,
        write_port: SnapshotWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        cache_port: StockCachePort | None = None,
        candidate_service: W2SCandidateService | None = None,
        confirm_service: W2SConfirmService | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._cache_port = cache_port
        self._cache_writer = SnapshotCacheWriter(cache_port)
        self._candidate_service = candidate_service or W2SCandidateService()
        self._confirm_service = confirm_service or W2SConfirmService(W2SAuctionScorer())

    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        lookback_days: int = 5,
    ) -> BuildResult:
        job_key = f"build_pre_market_brief:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_pre_market_brief",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
                batch_id=batch_id,
                trace_id=trace_id,
                warnings=["idempotency_key_already_completed"],
                metrics={"job_key": job_key},
            )

        bars = await self._read_port.get_stock_daily_bars(trade_date)
        # ── D2 输入：消费盘后 D1 候选池，不是全量 subject_stock_pool ──
        # 优先从 strong_stock_watch_pool 读取 candidate_promoted=TRUE 的对象
        promoted_fn = getattr(self._read_port, "get_prior_strong_watch_pool_rows", None)
        if callable(promoted_fn):
            pools = await promoted_fn(trade_date=trade_date, lookback_days=lookback_days)
        else:
            # 兼容回退：仍从 subject_stock_pool 读取（旧路径，逐步淘汰）
            pools = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        prior = await self._read_port.get_prior_stock_daily_snapshots(
            trade_date=trade_date,
            lookback_days=lookback_days,
            stock_ids=[row.stock_id for row in pools] if pools else None,
        )
        candidates = self._candidate_service.build_candidates(bars=bars, pool_rows=pools, prior_rows=prior)

        auctions = await self._read_port.get_stock_auction_snapshot(
            trade_date=trade_date,
            stock_ids=[c.stock_id for c in candidates] if candidates else None,
        )
        confirmed = self._confirm_service.confirm(candidates=candidates, auctions=auctions)
        rejected = [row for row in confirmed if not row.approved]
        reject_codes = [row.reject_reason_code for row in rejected if row.reject_reason_code]
        reject_code_coverage_ok = len(rejected) == len(reject_codes)
        reject_code_valid_ok = all(code in ALL_REJECT_REASON_CODES for code in reject_codes)

        brief_doc = {
            "trade_date": trade_date.isoformat(),
            "snapshot_version": snapshot_version,
            "candidate_count": len(candidates),
            "confirmed_count": sum(1 for row in confirmed if row.approved),
            "reject_count": len(rejected),
            "reject_reason_coverage_ok": reject_code_coverage_ok,
            "reject_reason_valid_ok": reject_code_valid_ok,
            "picks": [
                {
                    "stock_id": row.stock_id,
                    "candidate_level": row.candidate_level,
                    "confirm_level": row.confirm_level,
                    "confirm_score": str(row.confirm_score),
                    "approved": row.approved,
                    "reject_reason_code": row.reject_reason_code,
                    "evidence_rules": row.evidence_rules,
                }
                for row in confirmed[:30]
            ],
        }

        snapshot = PreMarketBriefSnapshot(
            trade_date=trade_date,
            snapshot_version=snapshot_version,
            batch_id=batch_id,
            trace_id=trace_id,
            source_trace_id=trace_id,
            brief_doc=brief_doc,
        )

        affected = await self._write_port.upsert_pre_market_brief_snapshot(snapshot)

        if self._cache_port is not None:
            await self._cache_writer.write_value_cache(
                f"sps:pre_market_brief:{trade_date}",
                asdict(snapshot),
                ttl_seconds=SnapshotCacheWriter.TTL_24H,
            )
            await self._cache_writer.write_current_version(
                "sps:pre_market_brief",
                trade_date,
                snapshot_version,
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
                    domain="pre_market",
                    snapshot_version=snapshot_version,
                    object_name="pre_market_brief_snapshot",
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
                "confirmed_count": sum(1 for row in confirmed if row.approved),
            },
        )

        return BuildResult(
            name="build_pre_market_brief",
            trade_date=trade_date.isoformat(),
            affected_rows=affected,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            metrics={
                "candidate_count": len(candidates),
                "confirmed_count": sum(1 for row in confirmed if row.approved),
                "reject_count": len(rejected),
            },
            published_events=["snapshot_built"],
            cache_writes=2 if self._cache_port is not None else 0,
        )

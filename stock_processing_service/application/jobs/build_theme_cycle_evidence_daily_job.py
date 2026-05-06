from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.domain.services.theme_cycle_evidence_daily_builder import (
    ThemeCycleEvidenceDailyBuilder,
)
from stock_processing_service.ports import (
    AlgorithmStateWritePort,
    IdempotencyPort,
    StockEventPort,
    StockReadPort,
)


class BuildThemeCycleEvidenceDailyJob:
    """Generate theme_cycle_evidence_daily from pool + bar data.

    This is the Layer B truth source producer. It reads subject pool, daily bars,
    heat data, and prior cycle states through StockReadPort, builds four-layer
    evidence (event/leader/board/K-line), and writes to theme_cycle_evidence_daily
    through AlgorithmStateWritePort.
    """

    def __init__(
        self,
        read_port: StockReadPort,
        write_port: AlgorithmStateWritePort,
        event_port: StockEventPort,
        idempotency_port: IdempotencyPort,
        builder: ThemeCycleEvidenceDailyBuilder | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._builder = builder or ThemeCycleEvidenceDailyBuilder()

    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
    ) -> BuildResult:
        job_key = f"build_theme_cycle_evidence_daily:{trade_date.isoformat()}:{snapshot_version}"
        acquired = await self._idempotency_port.acquire_job_idempotency(job_key=job_key, ttl_seconds=6 * 3600)
        if not acquired:
            return BuildResult(
                name="build_theme_cycle_evidence_daily",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="skipped_idempotent",
                batch_id=batch_id,
                trace_id=trace_id,
            )

        pool_rows = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        subject_keys = sorted({r.subject_key for r in pool_rows})
        bars = await self._read_port.get_stock_daily_bars(trade_date)
        warnings: list[str] = []

        # Heat scores: read from subject context or pool metadata
        heat_scores: dict[str, Decimal] = {}
        for r in pool_rows:
            md = r.metadata if isinstance(r.metadata, dict) else {}
            hs = md.get("heat_latest") or md.get("heat") or md.get("avg_heat_5d")
            if hs is not None:
                try:
                    heat_scores[r.subject_key] = Decimal(str(hs))
                except Exception as e:
                    warnings.append(f"heat_score_parse:{r.subject_key}:{e}")

        # Previous cycle states: use prior TRADING day (not calendar -1).
        previous_states: dict[str, str] = {}
        calendar = await self._read_port.get_trade_calendar(trade_date)
        prev_trade_date = calendar.prev_trade_date if calendar else None
        prev_trade_date_missing = prev_trade_date is None
        if prev_trade_date_missing:
            warnings.append("prev_trade_date_missing:calendar_or_prev_trade_date_null")

        if prev_trade_date and subject_keys:
            try:
                cycles = await self._read_port.get_mainline_cycle_by_subject_keys(
                    subject_keys=subject_keys,
                    trade_date=prev_trade_date,
                )
                for c in cycles:
                    if c.final_cycle_state:
                        previous_states[c.subject_key] = c.final_cycle_state
            except Exception as e:
                warnings.append(f"prev_cycle_read_failed:{type(e).__name__}:{e}")

        # Fallback: prior snapshots (only use subject_key, never final_cycle_state as key).
        if not previous_states:
            try:
                prior_snaps = await self._read_port.get_prior_stock_daily_snapshots(
                    trade_date=trade_date,
                    lookback_days=3,
                    stock_ids=None,
                )
                for s in prior_snaps:
                    sk = str(s.payload.get("subject_key") or "")
                    cs = str(s.payload.get("final_cycle_state") or "")
                    if sk and cs and sk not in previous_states:
                        previous_states[sk] = cs
                if not previous_states:
                    warnings.append("prior_state_all_empty:no_prior_cycles_or_snapshots")
            except Exception as e:
                warnings.append(f"prior_snaps_read_failed:{type(e).__name__}:{e}")

        # Event stats: real event data from theme_history_event
        event_stats_by_subject: dict[str, object] = {}
        if subject_keys:
            try:
                event_stats_list = await self._read_port.get_subject_event_stats(
                    trade_date=trade_date,
                    subject_keys=subject_keys,
                )
                event_stats_by_subject = {str(e.subject_key): e for e in event_stats_list}
            except Exception as e:
                warnings.append(f"event_stats_read_failed:{type(e).__name__}:{e}")
        if not event_stats_by_subject:
            warnings.append("event_stats_empty:falling_back_to_pool_metadata")

        rows = self._builder.build_many(
            trade_date=trade_date,
            pool_rows=pool_rows,
            bars=bars,
            heat_scores=heat_scores,
            previous_states=previous_states,
            event_stats_by_subject=event_stats_by_subject,
        )

        write_rows = [
            {
                "subject_key": r.subject_key,
                "theme_name": r.theme_name,
                "trade_date": r.trade_date,
                "event_strength_score": str(r.event_strength_score),
                "event_continuity_score": str(r.event_continuity_score),
                "strong_event_count_7d": r.strong_event_count_7d,
                "event_recency_days": r.event_recency_days,
                "event_count_3d": r.event_count_3d,
                "event_count_7d": r.event_count_7d,
                "leader_alive_score": str(r.leader_alive_score),
                "leader_breakdown_flag": r.leader_breakdown_flag,
                "relay_strength_score": str(r.relay_strength_score),
                "front_row_survival_ratio": str(r.front_row_survival_ratio),
                "limit_up_count": r.limit_up_count,
                "limit_down_count": r.limit_down_count,
                "red_ratio": str(r.red_ratio),
                "big_drop_ratio": str(r.big_drop_ratio),
                "front_row_strength_score": str(r.front_row_strength_score),
                "theme_support_score": str(r.theme_support_score),
                "break_start_pivot": r.break_start_pivot,
                "above_ma10": r.above_ma10,
                "above_ma20": r.above_ma20,
                "previous_cycle_state": r.previous_cycle_state,
                "evidence_json": r.evidence_json,
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
            }
            for r in rows
        ]

        written = await self._write_port.upsert_theme_cycle_evidence_daily_rows(write_rows)

        # ── Write-verify: confirm DB truth was persisted ──
        if written > 0:
            verify_rows = await self._read_port.get_subject_cycle_evidence_daily(
                trade_date=trade_date,
                subject_keys=subject_keys,
            )
            if len(verify_rows) < len(write_rows):
                raise RuntimeError(
                    f"Write-verify failed: wrote {len(write_rows)} rows but "
                    f"only {len(verify_rows)} rows readable back. "
                    f"DatabaseGateway upsert may be a no-op stub."
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
                    domain="theme_cycle_evidence",
                    snapshot_version=snapshot_version,
                    object_name="theme_cycle_evidence_daily",
                    row_count=written,
                    success=True,
                ),
            )
        )

        await self._idempotency_port.mark_job_completed(
            job_key,
            {
                "trade_date": trade_date.isoformat(),
                "snapshot_version": snapshot_version,
                "row_count": written,
            },
        )

        return BuildResult(
            name="build_theme_cycle_evidence_daily",
            trade_date=trade_date.isoformat(),
            affected_rows=written,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            warnings=warnings,
            metrics={
                "evidence_row_count": written,
                "subject_key_count": len(subject_keys),
                "prior_state_hit_count": len(previous_states),
                "event_stats_hit_count": len(event_stats_by_subject),
                "prev_trade_date_missing": prev_trade_date_missing,
                "evidence_event_source": "event_stats" if event_stats_by_subject else "pool_metadata",
            },
            published_events=["snapshot_built"],
        )

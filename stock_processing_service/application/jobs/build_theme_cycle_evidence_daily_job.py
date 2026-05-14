from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import EventEnvelope, SnapshotBuiltPayload
from stock_processing_service.domain.services.theme_cycle_evidence_daily_builder import (
    ThemeCycleEvidenceDailyBuilder,
)
from stock_processing_service.domain.services.theme_kline_evidence_builder import (
    ThemeKlineEvidenceBuilder,
)
from stock_processing_service.ports import (
    AlgorithmStateWritePort,
    IdempotencyPort,
    StockEventPort,
    StockReadPort,
)


def _get(row, key, default=None):
    """兼容 dict 和 DTO 的属性访问。"""
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


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
        kline_builder: ThemeKlineEvidenceBuilder | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._idempotency_port = idempotency_port
        self._builder = builder or ThemeCycleEvidenceDailyBuilder()
        self._kline_builder = kline_builder or ThemeKlineEvidenceBuilder()

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

        # 兼容 dict/DTO：统一转为 SimpleNamespace 用于属性访问
        from types import SimpleNamespace
        def _ns(obj):
            return SimpleNamespace(**obj) if isinstance(obj, dict) else obj

        pool_rows_raw = await self._read_port.get_subject_stock_pool_by_trade_date(trade_date)
        # DB 列名 → DTO 属性名映射（DBThemeDataGateway 返回原始列名）
        _FIELD_MAP = {
            "rank_order_raw": "rank_order", "limit_up_raw": "limit_up",
            "is_leader_raw": "is_leader", "pool_rank": "rank_order",
        }
        for r in pool_rows_raw:
            if isinstance(r, dict):
                for old, new in _FIELD_MAP.items():
                    if old in r and new not in r:
                        r[new] = r[old]
                r.setdefault("subject_name", r.get("theme_name") or r.get("subject_key", ""))
                r.setdefault("metadata", {})
                r.setdefault("pool_rank", r.get("rank_order") or r.get("rank_order_raw"))
                r.setdefault("close_price", 0); r.setdefault("pct_chg", 0)
                r.setdefault("limit_up", False); r.setdefault("is_leader", False)
        pool_rows = [_ns(r) for r in pool_rows_raw]
        subject_keys = sorted({r.subject_key for r in pool_rows})
        bars_raw = await self._read_port.get_stock_daily_bars(trade_date)
        bars = [_ns(b) for b in bars_raw]

        # Heat scores: read from pool metadata.
        heat_scores: dict[str, Decimal] = {}
        for r in pool_rows:
            md = getattr(r, "metadata", None) or {}
            if isinstance(md, dict):
                hs = md.get("heat_latest") or md.get("heat") or md.get("avg_heat_5d")
            else:
                hs = None
            if hs is not None:
                heat_scores[r.subject_key] = Decimal(str(hs))

        # Previous cycle states: prior TRADING day (not calendar -1).
        calendar = _ns(await self._read_port.get_trade_calendar(trade_date))
        if calendar is None or calendar.prev_trade_date is None:
            raise RuntimeError(
                f"Evidence job: trade calendar unavailable for {trade_date}. "
                f"Cannot determine previous trading day for cycle state lookup."
            )
        prev_trade_date = calendar.prev_trade_date
        prev_trade_date_missing = False

        previous_states: dict[str, str] = {}
        if subject_keys:
            cycles_raw = await self._read_port.get_mainline_cycle_by_subject_keys(
                subject_keys=subject_keys,
                trade_date=prev_trade_date,
            )
            cycles = [_ns(c) for c in cycles_raw]
            for c in cycles:
                if c.final_cycle_state:
                    previous_states[c.subject_key] = c.final_cycle_state

        # Event stats: mandatory real event data from theme_history_event.
        # Every subject must have an entry; subjects with zero events get a zero-filled DTO.
        from stock_processing_service.contracts.dto import SubjectEventStatsDTO
        event_stats_by_subject: dict[str, object] = {}
        if subject_keys:
            event_stats_raw = await self._read_port.get_subject_event_stats(
                trade_date=trade_date,
                subject_keys=subject_keys,
            )
            event_stats_list = [_ns(e) for e in event_stats_raw]
            for e in event_stats_list:
                event_stats_by_subject[str(e.subject_key)] = e
            for sk in subject_keys:
                if sk not in event_stats_by_subject:
                    event_stats_by_subject[sk] = SubjectEventStatsDTO(
                        subject_key=sk,
                        theme_name=sk,
                        today_event_count=0,
                        recent_event_count=0,
                        distinct_event_days=0,
                        key_event_count=0,
                        sample_summaries=[],
                    )
        if not event_stats_by_subject and subject_keys:
            raise RuntimeError(
                f"Evidence job: subject_event_stats unavailable for {len(subject_keys)} subjects."
            )

        # ── K-line evidence: build from historical bars ──
        kline_evidence_by_subject: dict[str, object] = {}
        history_bar_count = 0
        unique_stock_count = 0
        history_query_scope = "none"
        if subject_keys:
            from datetime import timedelta
            start_date = trade_date - timedelta(days=ThemeKlineEvidenceBuilder.HISTORY_NATURAL_DAYS)
            all_pool_stock_ids = sorted({r.stock_id for r in pool_rows if r.stock_id})
            unique_stock_count = len(all_pool_stock_ids)
            history_query_scope = "pool_stock_ids" if all_pool_stock_ids else "all_stocks_empty_pool"
            history_bars = await self._read_port.get_stock_daily_bars_range(
                start_date=start_date,
                end_date=trade_date,
                stock_ids=all_pool_stock_ids if all_pool_stock_ids else None,
            )
            history_bar_count = len(history_bars)
            # Group by date
            bars_by_date: dict[str, list[object]] = {}
            trade_dates_set: set[str] = set()
            for b in history_bars:
                td_str = str(getattr(b, "trade_date", "")) if not isinstance(b, dict) else str(b.get("trade_date", ""))
                if td_str:
                    bars_by_date.setdefault(td_str, []).append(b)
                    trade_dates_set.add(td_str)
            sorted_dates = sorted(trade_dates_set)

            # Per-subject K-line evidence
            pools_by_subject: dict[str, list[str]] = {}
            for r in pool_rows:
                pools_by_subject.setdefault(r.subject_key, []).append(r.stock_id)

            for sk, stock_ids in pools_by_subject.items():
                kl = self._kline_builder.build_one(
                    subject_key=sk,
                    stock_ids=list(set(stock_ids)),
                    bars_by_date=bars_by_date,
                    trade_dates=sorted_dates,
                )
                kline_evidence_by_subject[sk] = kl

        rows = self._builder.build_many(
            trade_date=trade_date,
            pool_rows=pool_rows,
            bars=bars,
            heat_scores=heat_scores,
            previous_states=previous_states,
            event_stats_by_subject=event_stats_by_subject,
            kline_evidence_by_subject=kline_evidence_by_subject,
        )

        write_rows = []
        for r in rows:
            _ev = dict(r.evidence_json) if r.evidence_json else {}
            _ev.setdefault("meta", {})
            _ev["meta"].update({
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
                "previous_cycle_state": r.previous_cycle_state,
            })
            write_rows.append({
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
                "evidence_json": _ev,
                "snapshot_version": snapshot_version,
                "batch_id": batch_id,
                "trace_id": trace_id,
            })
        # ── End write_rows loop ──

        written = await self._write_port.upsert_theme_cycle_evidence_daily_rows(write_rows)

        # ── Write-verify: confirm DB truth was persisted ──
        if written > 0:
            verify_rows = await self._read_port.get_subject_cycle_evidence_daily(
                trade_date=trade_date,
                subject_keys=subject_keys,
            )
            verify_keys = {str(r.get("subject_key") or "") for r in verify_rows}
            write_keys = {str(r.get("subject_key") or "") for r in write_rows}
            missing_keys = write_keys - verify_keys
            if len(verify_rows) < len(write_rows):
                raise RuntimeError(
                    f"Write-verify failed: wrote {len(write_rows)} rows but "
                    f"only {len(verify_rows)} rows readable back. "
                    f"Missing subject_keys: {sorted(missing_keys)[:20]}. "
                    f"DatabaseGateway upsert may be a no-op stub."
                )
            if missing_keys:
                raise RuntimeError(
                    f"Write-verify partial failure: {len(missing_keys)} of {len(write_keys)} "
                    f"subject_keys not readable back. Missing: {sorted(missing_keys)[:20]}"
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
            warnings=[],
            metrics={
                "evidence_row_count": written,
                "subject_key_count": len(subject_keys),
                "prior_state_hit_count": len(previous_states),
                "event_stats_hit_count": len(event_stats_by_subject),
                "prev_trade_date_missing": prev_trade_date_missing,
                "evidence_event_source": "event_stats" if event_stats_by_subject else "pool_metadata",
                "kline_evidence_hit_count": len(kline_evidence_by_subject),
                "history_bar_count": history_bar_count,
                "unique_stock_count": unique_stock_count,
                "history_query_scope": history_query_scope,
                "kline_evidence_source": "theme_kline_evidence_builder" if kline_evidence_by_subject else "none",
                "kline_ok_count": sum(
                    1 for v in kline_evidence_by_subject.values()
                    if getattr(v, "kline_quality", "") == "ok"
                ),
                "kline_insufficient_count": sum(
                    1 for v in kline_evidence_by_subject.values()
                    if getattr(v, "kline_quality", "") in {"insufficient_history", "minimal"}
                ),
            },
            published_events=["snapshot_built"],
        )

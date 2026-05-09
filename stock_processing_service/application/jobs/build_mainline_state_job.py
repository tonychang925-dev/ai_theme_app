"""BuildMainlineStateJob — Layer B 主线状态快照与迁移。

编排 identity + cycle → mainline_state_daily + mainline_state_transition。
替代旧链 stock_service/scripts/build_mainline_state_tracking.py。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult, MainlineCycleDTO, MainlineIdentityDTO
from stock_processing_service.contracts.events import EventEnvelope
from stock_processing_service.domain.services.mainline_state_transition_service import (
    MainlineStateTransitionService,
    MainlineStateDailyDTO,
)
from stock_processing_service.ports import (
    AlgorithmStateWritePort,
    StockEventPort,
    StockReadPort,
)


class BuildMainlineStateJob:
    """Layer B 主线状态快照与迁移 Job。

    1. 读取当日 identity + cycle
    2. 读取前一日 mainline_state_daily
    3. 构建当日 state_daily 快照
    4. 构建 state_transition 迁移记录
    5. 写入 DB
    """

    RULE_VERSION = "mainline_state_transition.v2"

    def __init__(
        self,
        read_port: StockReadPort,
        write_port: AlgorithmStateWritePort,
        event_port: StockEventPort | None = None,
        transition_service: MainlineStateTransitionService | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._transition_service = transition_service or MainlineStateTransitionService()

    async def execute(
        self,
        trade_date: date,
        *,
        snapshot_version: str = "mainline_state.v2",
        batch_id: str = "",
        trace_id: str = "",
    ) -> BuildResult:
        batch_id = batch_id or uuid4().hex[:12]
        trace_id = trace_id or uuid4().hex[:12]

        # Step 1: 读取 identity + cycle
        identities_raw = await self._read_port.get_mainline_identity_by_subject_keys(
            [], trade_date
        )
        identities: dict[str, MainlineIdentityDTO] = {}
        for row in (identities_raw or []):
            dto = self._to_identity(row)
            identities[dto.subject_key] = dto

        cycles_raw = await self._read_port.get_mainline_cycle_by_subject_keys(
            [], trade_date
        )
        cycles: list[MainlineCycleDTO] = []
        for row in (cycles_raw or []):
            cycles.append(self._to_cycle(row))

        if not cycles:
            return BuildResult(
                name="build_mainline_state",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="ok_no_data",
                batch_id=batch_id,
                trace_id=trace_id,
            )

        # Step 2: 读取前一日 state_daily
        prior_snapshots: dict[str, MainlineStateDailyDTO] = {}
        try:
            prior_raw = await self._read_port.get_prior_mainline_state_daily(trade_date)
            for row in (prior_raw or []):
                sk = str(row.get("subject_key") or "").strip()
                if sk:
                    prior_snapshots[sk] = self._to_state_daily(row)
        except Exception:
            pass

        # Step 3: 构建当日 snapshot
        daily_snapshots = self._transition_service.build_daily_snapshots(
            trade_date=trade_date,
            cycles=cycles,
            identities=identities,
            prior_snapshots=prior_snapshots,
        )

        # Step 4: 构建 transition
        transitions = self._transition_service.build_transitions(
            trade_date=trade_date,
            daily_snapshots=daily_snapshots,
            prior_snapshots=prior_snapshots,
        )

        # Step 5: 写入 mainline_state_daily
        daily_rows: list[dict[str, Any]] = []
        for s in daily_snapshots:
            daily_rows.append({
                "trade_date": s.trade_date,
                "subject_key": s.subject_key,
                "theme_name": s.theme_name,
                "state": s.state,
                "state_score": float(s.state_score),
                "is_mainline": s.is_mainline,
                "mainline_strength_score": float(s.mainline_strength_score),
                "fade_watch_score": float(s.fade_watch_score),
                "fade_confirmed_score": float(s.fade_confirmed_score),
                "divergence_score": float(s.divergence_score),
                "repair_score": float(s.repair_score),
                "evidence_json": s.evidence_json,
                "source_version": self.RULE_VERSION,
            })
        daily_count = await self._write_port.upsert_mainline_state_daily_rows(daily_rows)

        # Step 6: 写入 mainline_state_transition
        transition_rows: list[dict[str, Any]] = []
        for t in transitions:
            transition_rows.append({
                "trade_date": t.trade_date,
                "subject_key": t.subject_key,
                "theme_name": t.theme_name,
                "from_state": t.from_state,
                "to_state": t.to_state,
                "transition_type": t.transition_type,
                "from_score": float(t.from_score),
                "to_score": float(t.to_score),
                "confidence": float(t.confidence),
                "trigger_flags": t.trigger_flags,
                "evidence_json": t.evidence_json,
                "source_version": self.RULE_VERSION,
            })
        trans_count = await self._write_port.upsert_mainline_state_transition_rows(transition_rows)

        # Step 7: 发布事件
        if self._event_port:
            try:
                await self._event_port.publish_stock_processing_event(
                    EventEnvelope(
                        event_id=str(uuid4()),
                        event_name="mainline_state_built",
                        trade_date=trade_date,
                        batch_id=batch_id,
                        trace_id=trace_id,
                        producer="stock_processing_service",
                        occurred_at=datetime.now(timezone.utc),
                        payload_version="v1",
                        payload={
                            "trade_date": trade_date.isoformat(),
                            "daily_snapshot_count": daily_count,
                            "transition_count": trans_count,
                            "upgrade_count": sum(1 for t in transitions if t.transition_type == "upgrade"),
                            "downgrade_count": sum(1 for t in transitions if t.transition_type == "downgrade"),
                            "fade_count": sum(1 for t in transitions if t.transition_type == "fade"),
                            "flat_count": sum(1 for t in transitions if t.transition_type == "flat"),
                        },
                    )
                )
            except Exception:
                pass

        return BuildResult(
            name="build_mainline_state",
            trade_date=trade_date.isoformat(),
            affected_rows=daily_count + trans_count,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            metrics={
                "daily_snapshot_count": daily_count,
                "transition_count": trans_count,
            },
        )

    @staticmethod
    def _to_identity(row: dict[str, Any]) -> MainlineIdentityDTO:
        return MainlineIdentityDTO(
            subject_key=str(row.get("subject_key") or ""),
            theme_name=str(row.get("theme_name") or ""),
            is_main_theme=bool(row.get("is_main_theme")),
            identity_status=str(row.get("identity_status") or "observed"),
            composite_score=float(row.get("composite_score") or 0),
        )

    @staticmethod
    def _to_cycle(row: dict[str, Any]) -> MainlineCycleDTO:
        return MainlineCycleDTO(
            subject_key=str(row.get("subject_key") or ""),
            theme_name=str(row.get("theme_name") or ""),
            final_cycle_state=str(row.get("final_cycle_state") or "start"),
            final_mainline_alive=bool(row.get("final_mainline_alive")),
            fade_watch=bool(row.get("fade_watch")),
            fade_confirmed=bool(row.get("fade_confirmed")),
            mainline_strength_score=float(row.get("mainline_strength_score") or 0),
            fade_watch_score=float(row.get("fade_watch_score") or 0),
            fade_confirmed_score=float(row.get("fade_confirmed_score") or 0),
            divergence_score=float(row.get("divergence_score") or 0),
            repair_score=float(row.get("repair_score") or 0),
        )

    @staticmethod
    def _to_state_daily(row: dict[str, Any]) -> MainlineStateDailyDTO:
        return MainlineStateDailyDTO(
            trade_date=row.get("trade_date", date.today()),
            subject_key=str(row.get("subject_key") or ""),
            theme_name=str(row.get("theme_name") or ""),
            state=str(row.get("state") or "start"),
            state_score=float(row.get("state_score") or 0),
            is_mainline=bool(row.get("is_mainline")),
            mainline_strength_score=float(row.get("mainline_strength_score") or 0),
            fade_watch_score=float(row.get("fade_watch_score") or 0),
            fade_confirmed_score=float(row.get("fade_confirmed_score") or 0),
            divergence_score=float(row.get("divergence_score") or 0),
            repair_score=float(row.get("repair_score") or 0),
        )

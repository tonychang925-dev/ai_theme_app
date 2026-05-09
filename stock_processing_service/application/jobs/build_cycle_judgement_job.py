"""BuildCycleJudgementJob — Layer B 周期判定写入。

将 CycleJudgementService 的判定结果写入 theme_cycle_judgement_v2。
替代旧链 stock_service/scripts/build_theme_cycle_judgement_v2.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timezone, datetime
from typing import Any
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.contracts.events import EventEnvelope, CycleBuiltPayload
from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidenceBuilder
from stock_processing_service.domain.services.cycle_judgement_service import CycleJudgementService
from stock_processing_service.ports import (
    AlgorithmStateWritePort,
    StockEventPort,
    StockReadPort,
)


class BuildCycleJudgementJob:
    """Layer B 周期判定 Job。

    1. 读取 cycle evidence
    2. 调用 CycleJudgementService 判定
    3. 写入 theme_cycle_judgement_v2
    4. （可选）发布事件
    """

    RULE_VERSION = "cycle_judgement.v2"

    def __init__(
        self,
        read_port: StockReadPort,
        write_port: AlgorithmStateWritePort,
        event_port: StockEventPort | None = None,
    ) -> None:
        self._read_port = read_port
        self._write_port = write_port
        self._event_port = event_port
        self._evidence_builder = CycleEvidenceBuilder()
        self._judge_service = CycleJudgementService()

    async def execute(
        self,
        trade_date: date,
        *,
        snapshot_version: str = "cycle_judgement.v2",
        batch_id: str = "",
        trace_id: str = "",
    ) -> BuildResult:
        batch_id = batch_id or uuid4().hex[:12]
        trace_id = trace_id or uuid4().hex[:12]

        # Step 1: 获取所有存续主线（alive）的 subject_keys
        # 从 theme_cycle_judgement_v2 读取上一交易日 final_mainline_alive=true 的 subjects
        # 同时从 theme_mainline_identity_registry 获取已确认主线
        prior_alive_keys: set[str] = set()
        try:
            prior_rows = await self._read_port.get_prior_cycle_alive_subjects(trade_date)
            for r in (prior_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if sk:
                    prior_alive_keys.add(sk)
        except Exception:
            pass

        # 合并已确认主线
        confirmed_keys: set[str] = set()
        try:
            identity_rows = await self._read_port.get_mainline_identity_by_subject_keys(
                [], trade_date
            )
            for r in (identity_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if sk and bool(r.get("is_main_theme")) and str(r.get("identity_status") or "") == "confirmed":
                    confirmed_keys.add(sk)
        except Exception:
            pass

        all_subject_keys = sorted(prior_alive_keys | confirmed_keys)
        if not all_subject_keys:
            return BuildResult(
                name="build_cycle_judgement",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="ok_no_data",
                batch_id=batch_id,
                trace_id=trace_id,
            )

        # Step 2: 构建证据 + 判定
        evidence_rows = await self._evidence_builder.build_batch(trade_date, all_subject_keys)
        judgements = self._judge_service.judge_many(evidence_rows)

        if not judgements:
            return BuildResult(
                name="build_cycle_judgement",
                trade_date=trade_date.isoformat(),
                affected_rows=0,
                status="ok_no_data",
                batch_id=batch_id,
                trace_id=trace_id,
            )

        # Step 3: 写入 theme_cycle_judgement_v2
        rows: list[dict[str, Any]] = []
        for j in judgements:
            rows.append({
                "trade_date": trade_date,
                "subject_key": j.subject_key,
                "theme_name": j.theme_name,
                "final_cycle_state": j.final_cycle_state,
                "final_mainline_alive": j.final_mainline_alive,
                "fade_watch": j.fade_watch,
                "fade_confirmed": j.fade_confirmed,
                "mainline_strength_score": float(j.mainline_strength_score),
                "fade_risk_score": float(j.fade_risk_score),
                "fade_watch_score": float(j.fade_watch_score),
                "fade_confirmed_score": float(j.fade_confirmed_score),
                "fade_confirmed_evidence_count": j.fade_confirmed_evidence_count,
                "confidence_score": float(j.confidence_score),
                "evidence_json": j.evidence_json,
                "rule_version": self.RULE_VERSION,
            })

        affected = await self._write_port.upsert_theme_cycle_judgement_v2_rows(rows)

        # Step 4: 发布事件
        if self._event_port:
            try:
                await self._event_port.publish_stock_processing_event(
                    EventEnvelope(
                        event_id=str(uuid4()),
                        event_name="cycle_built",
                        trade_date=trade_date,
                        batch_id=batch_id,
                        trace_id=trace_id,
                        producer="stock_processing_service",
                        occurred_at=datetime.now(timezone.utc),
                        payload_version="v1",
                        payload=CycleBuiltPayload(
                            trade_date=trade_date,
                            subject_count=len(all_subject_keys),
                            judged_count=len(judgements),
                            rows_written=affected,
                        ),
                    )
                )
            except Exception:
                pass

        return BuildResult(
            name="build_cycle_judgement",
            trade_date=trade_date.isoformat(),
            affected_rows=affected,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            metrics={
                "subject_count": len(all_subject_keys),
                "judged_count": len(judgements),
                "rows_written": affected,
            },
        )

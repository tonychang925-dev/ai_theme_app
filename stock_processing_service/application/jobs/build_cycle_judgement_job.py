"""BuildCycleJudgementJob — Layer B 周期判定写入（新链闭环）。

对 tracked universe（主线 + 存续 + 异动 + 新题材）写入 theme_cycle_judgement_v2。
替代旧链 stock_service/scripts/build_theme_cycle_judgement_v2.py。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidenceBuilder
from stock_processing_service.domain.services.cycle_judgement_service import (
    CycleJudgementService,
    CycleJudgement,
)
from stock_processing_service.ports import (
    AlgorithmStateWritePort,
    StockEventPort,
    StockReadPort,
)


class BuildCycleJudgementJob:
    """Layer B 周期判定 Job。

    1. 获取 tracked universe（confirmed + prior alive + hot rank）
    2. 构建 subject 级周期证据
    3. 调用 CycleJudgementService 判定
    4. 写入 theme_cycle_judgement_v2
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

        # Step 1: 构建 tracked universe
        tracked_keys: set[str] = set()

        # 1a. current confirmed
        try:
            id_rows = await self._read_port.get_mainline_identity_by_subject_keys([], trade_date)
            for r in (id_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if sk and bool(r.get("is_main_theme")) and str(r.get("identity_status") or "") == "confirmed":
                    tracked_keys.add(sk)
        except Exception:
            pass

        # 1b. prior cycle alive (NOT fade_confirmed)
        try:
            cyc_rows = await self._read_port.get_mainline_cycle_by_subject_keys([], trade_date)
            for r in (cyc_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if sk and bool(r.get("final_mainline_alive")) and not bool(r.get("fade_confirmed")):
                    tracked_keys.add(sk)
        except Exception:
            pass

        # 1c. hot rank top 100
        try:
            rank_rows = await self._read_port.get_subject_rank_daily(trade_date, limit=100)
            for r in (rank_rows or []):
                sk = str(r.get("subject_key") or "").strip()
                if sk:
                    tracked_keys.add(sk)
        except Exception:
            pass

        if not tracked_keys:
            return BuildResult(
                name="build_cycle_judgement",
                trade_date=trade_date.isoformat(),
                affected_rows=0, status="ok_no_data",
                batch_id=batch_id, trace_id=trace_id,
            )

        # Step 2: 读取 subject 级周期证据
        all_subject_keys = sorted(tracked_keys)
        evidence_raw = await self._read_port.get_subject_cycle_evidence_daily(
            trade_date, subject_keys=all_subject_keys,
        )

        # Step 3: 构建 CycleEvidence + 判定
        # CycleJudgementService 是 per-stock 的，这里做 subject 级聚合：
        # 取每个 subject 的第一条 stock evidence 代表该 subject
        builder = CycleEvidenceBuilder()
        rows: list[dict[str, Any]] = []
        seen_subjects: set[str] = set()

        for er in (evidence_raw or []):
            sk = str(er.get("subject_key") or "").strip()
            if not sk or sk in seen_subjects:
                continue
            seen_subjects.add(sk)

            try:
                # 用 raw evidence 构建精简的 CycleEvidence（subject 级）
                evidence = builder.from_subject_evidence_row(dict(er), trade_date)
                judgement = self._judge_service.judge_one(evidence)
                state = judgement.final_cycle_state
                rows.append({
                    "trade_date": trade_date,
                    "subject_key": sk,
                    "theme_name": judgement.subject_name or sk,
                    "final_cycle_state": state,
                    "final_mainline_alive": judgement.final_mainline_alive,
                    "fade_watch": (state == "fade_watch"),
                    "fade_confirmed": (state == "fade_confirmed"),
                    "mainline_strength_score": float(judgement.mainline_strength_score),
                    "fade_risk_score": float(judgement.fade_confirmed_score),
                    "fade_watch_score": float(judgement.fade_watch_score),
                    "fade_confirmed_score": float(judgement.fade_confirmed_score),
                    "fade_confirmed_evidence_count": judgement.fade_confirmed_evidence_count,
                    "confidence_score": 0.85,
                    "evidence_json": {},
                    "rule_version": self.RULE_VERSION,
                })
            except Exception:
                # 对该 subject 使用默认值（存续）
                rows.append({
                    "trade_date": trade_date,
                    "subject_key": sk,
                    "theme_name": str(er.get("theme_name") or sk),
                    "final_cycle_state": "divergence",
                    "final_mainline_alive": True,
                    "fade_watch": False,
                    "fade_confirmed": False,
                    "mainline_strength_score": float(er.get("mainline_strength_score") or 0),
                    "fade_risk_score": 0.0,
                    "fade_watch_score": 0.0,
                    "fade_confirmed_score": 0.0,
                    "fade_confirmed_evidence_count": 0,
                    "confidence_score": 0.5,
                    "evidence_json": {},
                    "rule_version": self.RULE_VERSION,
                })

        # Step 4: 写入 theme_cycle_judgement_v2
        affected = await self._write_port.upsert_theme_cycle_judgement_v2_rows(rows)

        return BuildResult(
            name="build_cycle_judgement",
            trade_date=trade_date.isoformat(),
            affected_rows=affected,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
            metrics={
                "tracked_subjects": len(tracked_keys),
                "judged_count": len(seen_subjects),
                "rows_written": affected,
            },
        )

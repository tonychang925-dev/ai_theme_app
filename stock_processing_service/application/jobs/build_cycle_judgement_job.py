"""BuildCycleJudgementJob — Layer B 周期判定写入（新链闭环）。

对 tracked universe（6 源：confirmed + prior alive + hot rank + abnormal + new + cluster）
写入 theme_cycle_judgement_v2。
替代旧链 stock_service/scripts/build_theme_cycle_judgement_v2.py。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from uuid import uuid4

from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.domain.services.cycle_evidence_builder import CycleEvidenceBuilder
from stock_processing_service.domain.services.cycle_judgement_service import CycleJudgementService
from stock_processing_service.domain.services.mainline_identity_universe_builder import (
    MainlineIdentityUniverseBuilder,
)
from stock_processing_service.ports import (
    AlgorithmStateWritePort,
    StockEventPort,
    StockReadPort,
)


class BuildCycleJudgementJob:
    """Layer B 周期判定 Job。

    使用 MainlineIdentityUniverseBuilder（6 源）构建 tracked universe，
    对每个 subject 计算 cycle 状态并写入 theme_cycle_judgement_v2。
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
        source_errors: dict[str, str] = {}

        # Step 1: 构建 tracked universe（复用 6 源 UniverseBuilder）
        try:
            universe_builder = MainlineIdentityUniverseBuilder(self._read_port)
            universe_rows = await universe_builder.build(trade_date)
            tracked_keys = {r.subject_key for r in universe_rows}
        except Exception as e:
            source_errors["universe_builder"] = str(e)
            # 降级：仅 confirmed + prior alive
            tracked_keys = set()
            try:
                id_rows = await self._read_port.get_mainline_identity_by_subject_keys([], trade_date)
                for r in (id_rows or []):
                    sk = str(r.get("subject_key") or "").strip()
                    if sk and bool(r.get("is_main_theme")) and str(r.get("identity_status") or "") == "confirmed":
                        tracked_keys.add(sk)
            except Exception as e2:
                source_errors["confirmed_fallback"] = str(e2)
            try:
                cyc_rows = await self._read_port.get_mainline_cycle_by_subject_keys([], trade_date)
                for r in (cyc_rows or []):
                    sk = str(r.get("subject_key") or "").strip()
                    if sk and bool(r.get("final_mainline_alive")) and not bool(r.get("fade_confirmed")):
                        tracked_keys.add(sk)
            except Exception as e3:
                source_errors["prior_alive_fallback"] = str(e3)

        if not tracked_keys:
            return BuildResult(
                name="build_cycle_judgement",
                trade_date=trade_date.isoformat(),
                affected_rows=0, status="ok_no_data",
                batch_id=batch_id, trace_id=trace_id,
                metrics={"source_errors": source_errors},
            )

        all_subject_keys = sorted(tracked_keys)

        # Step 2: 读取 subject 级周期证据
        evidence_raw = await self._read_port.get_subject_cycle_evidence_daily(
            trade_date, subject_keys=all_subject_keys,
        )
        evidence_by_subject: dict[str, dict] = {}
        for er in (evidence_raw or []):
            sk = str(er.get("subject_key") or "").strip()
            if sk:
                evidence_by_subject[sk] = dict(er)

        # Step 3: 对每个 tracked subject 计算 cycle
        builder = CycleEvidenceBuilder()
        rows: list[dict[str, Any]] = []
        seen_subjects: set[str] = set()
        missing_evidence: list[str] = []
        judge_errors: list[str] = []

        for sk in all_subject_keys:
            er = evidence_by_subject.get(sk)
            if not er:
                # P1-3: 缺 evidence 的 subject 显式标记，不静默跳过
                missing_evidence.append(sk)
                rows.append({
                    "trade_date": trade_date,
                    "subject_key": sk,
                    "theme_name": sk,
                    "final_cycle_state": "start",
                    "final_mainline_alive": True,  # 新题材默认存续，后续 evidence 增强后可升级
                    "fade_watch": False,
                    "fade_confirmed": False,
                    "mainline_strength_score": 0.0,
                    "fade_risk_score": 0.0,
                    "fade_watch_score": 0.0,
                    "fade_confirmed_score": 0.0,
                    "fade_confirmed_evidence_count": 0,
                    "confidence_score": 0.3,  # 低置信度，标记为 evidence 缺失
                    "evidence_json": {"missing_evidence": True},
                    "rule_version": self.RULE_VERSION,
                })
                continue

            try:
                evidence = builder.from_subject_evidence_row(er, trade_date)
                judgement = self._judge_service.judge_one(evidence)
                state = judgement.final_cycle_state
                seen_subjects.add(sk)
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
            except Exception as e:
                # P1-4: 判定异常写 start + alive=false，不写假 alive
                judge_errors.append(f"{sk}:{str(e)[:100]}")
                seen_subjects.add(sk)
                rows.append({
                    "trade_date": trade_date,
                    "subject_key": sk,
                    "theme_name": str(er.get("theme_name") or sk),
                    "final_cycle_state": "start",
                    "final_mainline_alive": False,
                    "fade_watch": False,
                    "fade_confirmed": False,
                    "mainline_strength_score": 0.0,
                    "fade_risk_score": 0.0,
                    "fade_watch_score": 0.0,
                    "fade_confirmed_score": 0.0,
                    "fade_confirmed_evidence_count": 0,
                    "confidence_score": 0.2,
                    "evidence_json": {"judge_error": str(e)[:200]},
                    "rule_version": self.RULE_VERSION,
                })

        # Step 4: 写入 theme_cycle_judgement_v2
        affected = 0
        if rows:
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
                "missing_evidence_count": len(missing_evidence),
                "judge_error_count": len(judge_errors),
                "rows_written": affected,
                "source_errors": source_errors,
                "missing_evidence_subjects": missing_evidence[:20],
                "judge_error_subjects": judge_errors[:10],
            },
        )

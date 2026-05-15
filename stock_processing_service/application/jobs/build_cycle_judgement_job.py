"""BuildCycleJudgementJob — Layer B 周期判定写入（新链闭环）。

对 tracked universe（6 源：confirmed + prior alive + hot rank + abnormal + new + cluster）
写入 theme_cycle_judgement_v2。
替代旧链 stock_service/scripts/build_theme_cycle_judgement_v2.py。
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
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
        universe_builder = MainlineIdentityUniverseBuilder(self._read_port)
        try:
            universe_rows = await universe_builder.build(trade_date)
            tracked_keys = {r.subject_key for r in universe_rows}
            # 合并 UniverseBuilder 内部的 source_errors
            if hasattr(universe_builder, "source_errors"):
                source_errors.update(universe_builder.source_errors)
            critical_source_errors = {
                k: v for k, v in source_errors.items()
                if k in {"confirmed", "prior_alive"}
            }
            if critical_source_errors:
                raise RuntimeError(
                    "build_cycle_judgement failed: critical universe source error; "
                    f"trade_date={trade_date.isoformat()}; source_errors={critical_source_errors}"
                )
        except Exception as e:
            source_errors["universe_builder"] = str(e)
            raise RuntimeError(
                "build_cycle_judgement failed: universe_builder_error; "
                f"trade_date={trade_date.isoformat()}; error={e}"
            ) from e

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

        missing_evidence = [sk for sk in all_subject_keys if sk not in evidence_by_subject]
        if missing_evidence:
            raise RuntimeError(
                "build_cycle_judgement failed: missing subject cycle evidence; "
                f"trade_date={trade_date.isoformat()}; count={len(missing_evidence)}; "
                f"subjects={missing_evidence[:20]}"
            )

        for sk in all_subject_keys:
            er = evidence_by_subject[sk]
            try:
                evidence = builder.from_subject_evidence_row(er, trade_date)
                judgement = self._judge_service.judge_one(evidence)
                state = judgement.final_cycle_state
                seen_subjects.add(sk)
                fade_reason_codes = list(judgement.fade_reason_codes or [])
                if not fade_reason_codes:
                    if evidence.leader_breakdown_flag:
                        fade_reason_codes.append("leader_breakdown")
                    if evidence.limit_down_count >= 1:
                        fade_reason_codes.append("limit_down")
                    if evidence.red_ratio <= Decimal("0.45"):
                        fade_reason_codes.append("red_ratio_weak")
                    if evidence.big_drop_ratio >= Decimal("0.30"):
                        fade_reason_codes.append("big_drop_ratio")
                    if evidence.relay_score <= Decimal("35"):
                        fade_reason_codes.append("relay_weak")
                    if evidence.support_score <= Decimal("35"):
                        fade_reason_codes.append("support_weak")
                score_flags = dict(evidence.score_flags or {})
                if judgement.score_flags:
                    score_flags.update(judgement.score_flags)
                decision_path = judgement.decision_path or (
                    f"state={state}; final_mainline_alive=not_fade_confirmed; "
                    f"fade_confirmed_score={judgement.fade_confirmed_score}; "
                    f"evidence_count={judgement.fade_confirmed_evidence_count}; "
                    f"support_break={judgement.support_break}"
                )
                rows.append({
                    "trade_date": trade_date,
                    "subject_key": sk,
                    "theme_name": judgement.subject_name or sk,
                    "cycle_state_rule": state,
                    "mainline_alive_rule": judgement.mainline_alive_rule,
                    "final_cycle_state": state,
                    "final_mainline_alive": judgement.final_mainline_alive,
                    "fade_watch": (state == "fade_watch"),
                    "fade_confirmed": (state == "fade_confirmed"),
                    "mainline_strength_score": float(judgement.mainline_strength_score),
                    "fade_risk_score": float(judgement.fade_confirmed_score),
                    "fade_watch_score": float(judgement.fade_watch_score),
                    "fade_confirmed_score": float(judgement.fade_confirmed_score),
                    "fade_confirmed_evidence_count": judgement.fade_confirmed_evidence_count,
                    "evidence_count": judgement.fade_confirmed_evidence_count,
                    "support_break": judgement.support_break,
                    "decision_path": decision_path,
                    "fade_reason_codes": fade_reason_codes,
                    "score_flags": score_flags,
                    "confidence_score": 0.85,
                    "snapshot_version": snapshot_version,
                    "batch_id": batch_id,
                    "trace_id": trace_id,
                    "evidence_json": {
                        "decision_path": decision_path,
                        "fade_reason_codes": fade_reason_codes,
                        "score_flags": score_flags,
                        "mainline_alive_rule": judgement.mainline_alive_rule,
                        "support_break": judgement.support_break,
                        "evidence_count": judgement.fade_confirmed_evidence_count,
                    },
                    "rule_version": self.RULE_VERSION,
                })
            except Exception as e:
                judge_errors.append(f"{sk}:{str(e)[:100]}")
                raise RuntimeError(
                    "build_cycle_judgement failed: judge_error; "
                    f"trade_date={trade_date.isoformat()}; subject_key={sk}; error={e}"
                ) from e

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

"""Thin application service for analyst workbench generation."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from stock_processing_service.application.use_cases.generate_post_market_derived_data import (
    PostMarketDerivedDataGenerateUseCase,
)

from .contracts import WorkbenchGenerateResult, WorkbenchGenerationStep
from .draft import DraftStore
from .session import SessionStore, WorkbenchStatus


ChartProvider = Callable[[str], Awaitable[list[dict[str, Any]]]]
EmotionProvider = Callable[[str], Awaitable[dict[str, Any]]]
TrendUpdater = Callable[[str, list[dict[str, Any]]], None]


@dataclass
class AnalystWorkbenchGenerateService:
    project_root: Path
    pool: Any = None
    db_manager: Any = None
    chart_provider: ChartProvider | None = None
    emotion_provider: EmotionProvider | None = None
    trend_updater: TrendUpdater | None = None
    base_dir: str = "tmp/analyst_workbench"
    python_executable: str = sys.executable
    cli_timeout_sec: int = 120

    async def generate(self, trade_date: date, *, force: bool = True) -> WorkbenchGenerateResult:
        trade_date_str = trade_date.isoformat()
        generation_steps: list[WorkbenchGenerationStep] = []
        steps_completed: list[str] = []
        session_store = SessionStore(base_dir=str(self._workbench_base_dir()))
        session = session_store.get(trade_date)
        if not session.can_generate:
            step = WorkbenchGenerationStep(
                step="generate_guard",
                status="failed_precondition",
                started_at=_now(),
                finished_at=_now(),
                error=f"cannot generate from status {session.status}",
            )
            session.generation_steps = [step.to_dict()]
            session_store.save(session)
            return WorkbenchGenerateResult(
                trade_date=trade_date_str,
                status="failed_precondition",
                steps_completed=(),
                generation_steps=(step,),
                session_status=session.status,
                draft_version=session.draft_version,
                derived_status="not_started",
                draft_status="not_started",
                error=step.error,
            )

        derived_step, derived_status, missing_tables = await self._run_derived_data(trade_date, force=force)
        generation_steps.append(derived_step)
        if derived_step.status == "success":
            steps_completed.append("derived_data")
        else:
            self._persist_generation_steps(trade_date, generation_steps, status=WorkbenchStatus.FAILED)
            return WorkbenchGenerateResult(
                trade_date=trade_date_str,
                status="failed_precondition" if derived_step.status == "failed_precondition" else "failed",
                steps_completed=tuple(steps_completed),
                generation_steps=tuple(generation_steps),
                derived_status=derived_status,
                draft_status="not_started",
                missing_tables=tuple(missing_tables),
                error=derived_step.error,
            )

        charts_step = await self._run_charts(trade_date_str)
        generation_steps.append(charts_step)
        if charts_step.status == "success":
            steps_completed.append("charts")

        emotion_step = await self._run_emotion(trade_date_str)
        generation_steps.append(emotion_step)
        if emotion_step.status == "success":
            steps_completed.append("emotion")

        draft_step = await self._run_draft_cli(trade_date_str)
        generation_steps.append(draft_step)
        if draft_step.status == "success":
            steps_completed.append("workbench")

        draft_store = DraftStore(base_dir=str(self._workbench_base_dir()))
        session_store = SessionStore(base_dir=str(self._workbench_base_dir()))
        session = session_store.get(trade_date)
        draft = draft_store.load(trade_date) if session.draft_version > 0 else None

        if draft_step.status == "failed":
            status = "failed"
        elif draft and draft.missing_fields:
            status = "partial"
        elif "workbench" in steps_completed:
            status = "completed"
        else:
            status = "partial"

        self._persist_generation_steps(trade_date, generation_steps)
        session = session_store.get(trade_date)

        return WorkbenchGenerateResult(
            trade_date=trade_date_str,
            status=status,
            steps_completed=tuple(steps_completed),
            generation_steps=tuple(generation_steps),
            session_status=session.status,
            draft_version=session.draft_version,
            derived_status=derived_status,
            draft_status=draft_step.status,
            missing_tables=tuple(missing_tables),
            missing_fields=tuple(draft.missing_fields if draft else ()),
            source_quality=float(draft.source_quality if draft else 0),
            error=draft_step.error,
        )

    async def _run_derived_data(self, trade_date: date, *, force: bool) -> tuple[WorkbenchGenerationStep, str, list[str]]:
        started = _now()
        try:
            uc = PostMarketDerivedDataGenerateUseCase(pool=self.pool, db_manager=self.db_manager)
            uc.register_theme_cycle_truth()
            uc.register_dragon_tiger_object_build()
            uc.register_hot_money_activity_build(project_root=str(self.project_root))
            uc.register_theme_leader_candidate_build(project_root=str(self.project_root))
            uc.register_money_flow_enhanced_build(project_root=str(self.project_root))
            uc.register_stock_abnormal_signal_build(project_root=str(self.project_root))
            uc.register_strong_stock_watch_build()
            result = await uc.execute(trade_date, force=force)
            diagnostics = {
                "before_readiness": result.before_readiness,
                "after_readiness": result.after_readiness,
                "job_results": result.job_results,
            }
            return (
                WorkbenchGenerationStep(
                    step="derived_data",
                    status=result.status,
                    started_at=started,
                    finished_at=_now(),
                    error="" if result.status == "success" else "derived data is not ready",
                    diagnostics=diagnostics,
                ),
                result.status,
                list(result.missing_tables or []),
            )
        except Exception as exc:
            return (
                WorkbenchGenerationStep(
                    step="derived_data",
                    status="failed",
                    started_at=started,
                    finished_at=_now(),
                    error=str(exc)[:500],
                ),
                "failed",
                [],
            )

    async def _run_charts(self, trade_date_str: str) -> WorkbenchGenerationStep:
        started = _now()
        try:
            if self.chart_provider is None:
                raise RuntimeError("chart_provider is not configured")
            charts = await self.chart_provider(trade_date_str)
            chart_dir = self.project_root / "frontend" / "public" / "api" / "analyst-charts"
            chart_dir.mkdir(parents=True, exist_ok=True)
            (chart_dir / f"{trade_date_str}.json").write_text(
                json.dumps(charts, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            if self.trend_updater is not None:
                self.trend_updater(trade_date_str, charts)
            return WorkbenchGenerationStep(
                step="charts",
                status="success",
                started_at=started,
                finished_at=_now(),
                diagnostics={"count": len(charts)},
            )
        except Exception as exc:
            return WorkbenchGenerationStep(
                step="charts",
                status="failed",
                started_at=started,
                finished_at=_now(),
                error=str(exc)[:500],
            )

    async def _run_emotion(self, trade_date_str: str) -> WorkbenchGenerationStep:
        started = _now()
        try:
            if self.emotion_provider is None:
                raise RuntimeError("emotion_provider is not configured")
            emotion = await self.emotion_provider(trade_date_str)
            if not emotion or not emotion.get("emotion_node"):
                return WorkbenchGenerationStep(
                    step="emotion",
                    status="partial",
                    started_at=started,
                    finished_at=_now(),
                    error="emotion_node missing",
                )
            emotion_dir = self.project_root / "frontend" / "public" / "api"
            emotion_dir.mkdir(parents=True, exist_ok=True)
            (emotion_dir / f"emotion-{trade_date_str}.json").write_text(
                json.dumps(emotion, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
            return WorkbenchGenerationStep(
                step="emotion",
                status="success",
                started_at=started,
                finished_at=_now(),
                diagnostics={"emotion_node": emotion.get("emotion_node", "")},
            )
        except Exception as exc:
            return WorkbenchGenerationStep(
                step="emotion",
                status="failed",
                started_at=started,
                finished_at=_now(),
                error=str(exc)[:500],
            )

    async def _run_draft_cli(self, trade_date_str: str) -> WorkbenchGenerationStep:
        started = _now()
        script = self.project_root / "scripts" / "generate_analyst_workbench.py"

        def run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [self.python_executable, str(script), "--date", trade_date_str],
                capture_output=True,
                text=True,
                timeout=self.cli_timeout_sec,
                cwd=str(self.project_root),
                env={**os.environ, "SPS_SKIP_FETCH": "1"},
            )

        try:
            result = await asyncio.to_thread(run)
            if result.returncode != 0:
                return WorkbenchGenerationStep(
                    step="draft",
                    status="failed",
                    started_at=started,
                    finished_at=_now(),
                    error=(result.stderr or result.stdout or "").strip()[-500:],
                )
            return WorkbenchGenerationStep(
                step="draft",
                status="success",
                started_at=started,
                finished_at=_now(),
            )
        except Exception as exc:
            return WorkbenchGenerationStep(
                step="draft",
                status="failed",
                started_at=started,
                finished_at=_now(),
                error=str(exc)[:500],
            )

    def _persist_generation_steps(
        self,
        trade_date: date,
        generation_steps: list[WorkbenchGenerationStep],
        *,
        status: str | None = None,
    ) -> None:
        session_store = SessionStore(base_dir=str(self._workbench_base_dir()))
        session = session_store.get(trade_date)
        session.generation_steps = [step.to_dict() for step in generation_steps]
        if status == WorkbenchStatus.FAILED and session.status in (
            WorkbenchStatus.NOT_STARTED,
            WorkbenchStatus.DRAFT_READY,
            WorkbenchStatus.FAILED,
        ):
            session.status = WorkbenchStatus.FAILED
        session_store.save(session)

    def _workbench_base_dir(self) -> Path:
        base = Path(self.base_dir)
        if base.is_absolute():
            return base
        return self.project_root / base


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

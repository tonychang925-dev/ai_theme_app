"""Thin application service for analyst workbench generation."""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from stock_processing_service.application.use_cases.generate_post_market_derived_data import (
    PostMarketDerivedDataGenerateUseCase,
)

from .contracts import WorkbenchGenerateResult, WorkbenchGenerationStep
from .draft import DraftStore
from .session import SessionStore, WorkbenchStatus


ChartProvider = Callable[[str, Any | None], Awaitable[list[dict[str, Any]]]]
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
    derived_timeout_sec: int = 90

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

        if session.status != WorkbenchStatus.GENERATING:
            session = session_store.transition(session, WorkbenchStatus.GENERATING)
        running_step = WorkbenchGenerationStep(
            step="derived_data",
            status="running",
            started_at=_now(),
        )
        generation_steps.append(running_step)
        self._persist_generation_steps(trade_date, generation_steps)

        derived_step, derived_status, missing_tables = await self._run_derived_data(trade_date, force=force)
        generation_steps[-1] = derived_step
        if derived_step.status == "success":
            steps_completed.append("derived_data")
        elif derived_step.status == "cancelled":
            self._persist_generation_steps(trade_date, generation_steps, status=WorkbenchStatus.FAILED)
            return WorkbenchGenerateResult(
                trade_date=trade_date_str,
                status="failed",
                steps_completed=tuple(steps_completed),
                generation_steps=tuple(generation_steps),
                session_status=WorkbenchStatus.FAILED,
                draft_version=0,
                derived_status=derived_status,
                draft_status="not_started",
                missing_tables=tuple(missing_tables),
                error=derived_step.error,
            )
        elif force:
            # Degraded mode: proceed with chart+emotion only, skip derived
            derived_step = WorkbenchGenerationStep(
                step="derived_data",
                status="success",
                started_at=derived_step.started_at,
                finished_at=_now(),
                diagnostics={"degraded": True, "missing_tables": missing_tables, "original_error": derived_step.error},
            )
            generation_steps[-1] = derived_step
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

        # ── Build AI Draft Context (PR1.1) ──
        context_step = await self._build_draft_context(trade_date_str)
        generation_steps.append(context_step)
        if context_step.status == "success":
            steps_completed.append("draft_context")
        elif context_step.status == "failed_precondition":
            self._persist_generation_steps(trade_date, generation_steps, status=WorkbenchStatus.FAILED)
            return WorkbenchGenerateResult(
                trade_date=trade_date_str,
                status="failed_precondition",
                steps_completed=tuple(steps_completed),
                generation_steps=tuple(generation_steps),
                session_status=WorkbenchStatus.FAILED,
                draft_version=0,
                derived_status=derived_status,
                draft_status="not_started",
                missing_tables=tuple(missing_tables),
                error=context_step.error,
            )

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
            result = await asyncio.wait_for(
                uc.execute(trade_date, force=force),
                timeout=self.derived_timeout_sec,
            )
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
        except asyncio.CancelledError:
            return (
                WorkbenchGenerationStep(
                    step="derived_data",
                    status="cancelled",
                    started_at=started,
                    finished_at=_now(),
                    error="derived data generation cancelled before completion",
                ),
                "cancelled",
                [],
            )
        except Exception as exc:
            status = "timeout" if isinstance(exc, asyncio.TimeoutError) else "failed"
            error = (
                f"derived data timeout after {self.derived_timeout_sec}s"
                if isinstance(exc, asyncio.TimeoutError)
                else str(exc)[:500]
            )
            return (
                WorkbenchGenerationStep(
                    step="derived_data",
                    status=status,
                    started_at=started,
                    finished_at=_now(),
                    error=error,
                ),
                status,
                [],
            )

    async def _run_charts(self, trade_date_str: str) -> WorkbenchGenerationStep:
        started = _now()
        try:
            if self.chart_provider is None:
                raise RuntimeError("chart_provider is not configured")
            charts = await self.chart_provider(trade_date_str, self.pool)
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

    async def _build_draft_context(self, trade_date_str: str) -> WorkbenchGenerationStep:
        """Build AI Draft context from generated chart/emotion data (PR1.1).

        Packages derived data into AnalystDraftContext so the AI draft
        generator has the full market picture, not just raw JSON files.
        """
        started = _now()
        try:
            from .draft_context_builder import (
                DraftContextBuilder,
                write_context_file,
            )
            from .derived_context_reader import DerivedContextReader
            builder = DraftContextBuilder(project_root=self.project_root)

            # Load the chart/emotion JSON we just generated
            chart_path = self.project_root / "frontend" / "public" / "api" / "analyst-charts" / f"{trade_date_str}.json"
            emotion_path = self.project_root / "frontend" / "public" / "api" / f"emotion-{trade_date_str}.json"

            charts = None
            if chart_path.exists():
                charts = json.loads(chart_path.read_text(encoding="utf-8"))
            emotion = None
            if emotion_path.exists():
                emotion = json.loads(emotion_path.read_text(encoding="utf-8"))

            td = date.fromisoformat(trade_date_str)
            derived_context = await DerivedContextReader(pool=self.pool).read(td)
            trend_data = await self._build_trend_data(td)

            ctx = builder.build(
                trade_date=trade_date_str,
                chart_json=charts,
                emotion_json=emotion,
                derived_context=derived_context,
                trend_data=trend_data,
            )

            # Write context file alongside the draft
            ctx_path = write_context_file(ctx, self._workbench_base_dir() / trade_date_str)
            diagnostics = {
                "context_path": str(ctx_path),
                "source_quality": ctx.source_quality,
                "missing_sources": ctx.missing_sources,
                "theme_count": len(ctx.themes),
                "strong_stock_count": len(ctx.strong_stocks),
                "trend_points": _trend_point_counts(ctx.trend_data),
                "quality": ctx.quality,
                "warnings": ctx.warnings,
            }
            if ctx.quality == "FAILED":
                return WorkbenchGenerationStep(
                    step="draft_context",
                    status="failed_precondition",
                    started_at=started,
                    finished_at=_now(),
                    error="draft context has no derived themes or strong stocks",
                    diagnostics=diagnostics,
                )
            return WorkbenchGenerationStep(
                step="draft_context",
                status="success",
                started_at=started,
                finished_at=_now(),
                diagnostics=diagnostics,
            )
        except Exception as exc:
            return WorkbenchGenerationStep(
                step="draft_context",
                status="failed",
                started_at=started,
                finished_at=_now(),
                error=str(exc)[:500],
            )

    async def _build_trend_data(self, trade_date: date) -> dict[str, Any]:
        """Build historical trend data from MarketMetricsSnapshot inputs."""
        try:
            from stock_processing_service.application.services.analyst_charts.chart_engine import (
                ChartReproductionEngine,
            )
            from stock_processing_service.application.services.market_metrics.service import (
                MarketMetricsService,
            )

            start = trade_date - timedelta(days=20)
            snapshots = await MarketMetricsService(board_provider=False)._get_range_async(start, trade_date)
            return ChartReproductionEngine.build_trend(snapshots)
        except Exception:
            return {}

    async def _run_draft_cli(self, trade_date_str: str) -> WorkbenchGenerationStep:
        started = _now()
        script = self.project_root / "scripts" / "generate_analyst_workbench.py"

        # PR1.1: pass draft context file if available
        context_path = self._workbench_base_dir() / trade_date_str / "draft_context.json"

        def run() -> subprocess.CompletedProcess[str]:
            cmd = [self.python_executable, str(script), "--date", trade_date_str]
            if context_path.exists():
                cmd.extend(["--context-file", str(context_path)])
            return subprocess.run(
                cmd,
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
            WorkbenchStatus.GENERATING,
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


def _trend_point_counts(trend_data: dict[str, Any]) -> dict[str, int]:
    return {
        key: len(value)
        for key, value in (trend_data or {}).items()
        if isinstance(value, list)
    }

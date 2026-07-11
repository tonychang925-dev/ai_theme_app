"""Phase 4.5.5 — Workbench generate service tests."""

from datetime import date

from stock_processing_service.application.services.analyst_workbench.contracts import (
    WorkbenchGenerationStep,
)
from stock_processing_service.application.services.analyst_workbench.draft import (
    AIDraft,
    DraftStore,
)
from stock_processing_service.application.services.analyst_workbench.generate_service import (
    AnalystWorkbenchGenerateService,
)
from stock_processing_service.application.services.analyst_workbench.session import (
    SessionStore,
    WorkbenchStatus,
)


class SuccessfulGenerateService(AnalystWorkbenchGenerateService):
    async def _run_derived_data(self, trade_date, *, force):
        return (
            WorkbenchGenerationStep(step="derived_data", status="success"),
            "success",
            [],
        )

    async def _run_draft_cli(self, trade_date_str):
        td = date.fromisoformat(trade_date_str)
        store = DraftStore(base_dir=str(self._workbench_base_dir()))
        draft = AIDraft(trade_date=td, draft_version=1)
        store.save(draft)
        session_store = SessionStore(base_dir=str(self._workbench_base_dir()))
        session = session_store.get(td)
        if session.status == WorkbenchStatus.NOT_STARTED:
            session = session_store.transition(session, WorkbenchStatus.GENERATING)
        session_store.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
        return WorkbenchGenerationStep(step="draft", status="success")

    async def _build_draft_context(self, trade_date_str):
        return WorkbenchGenerationStep(
            step="draft_context",
            status="success",
            diagnostics={
                "quality": "GOOD",
                "theme_count": 1,
                "strong_stock_count": 1,
            },
        )


class FailingDerivedGenerateService(AnalystWorkbenchGenerateService):
    async def _run_derived_data(self, trade_date, *, force):
        return (
            WorkbenchGenerationStep(
                step="derived_data",
                status="failed_precondition",
                error="missing tables",
            ),
            "failed_precondition",
            ["theme_cycle_judgement_v2"],
        )


class EmptyContextGenerateService(AnalystWorkbenchGenerateService):
    async def _run_derived_data(self, trade_date, *, force):
        return (
            WorkbenchGenerationStep(step="derived_data", status="success"),
            "success",
            [],
        )

    async def _run_draft_cli(self, trade_date_str):
        raise AssertionError("draft CLI should not run when draft_context failed")


async def _charts(_trade_date: str):
    return [{"chart_type": "market_breadth", "data": {"up_count": 1}}]


async def _emotion(_trade_date: str):
    return {"emotion_node": "REBOUND"}


async def _should_not_call(_trade_date: str):
    raise AssertionError("provider should not be called")


async def test_tc_p455_01_given_generate_when_success_then_steps_are_recorded(tmp_path):
    service = SuccessfulGenerateService(
        project_root=tmp_path,
        chart_provider=_charts,
        emotion_provider=_emotion,
        base_dir="tmp/analyst_workbench",
    )

    result = await service.generate(date(2026, 7, 10))

    assert result.status == "completed"
    assert result.steps_completed == ("derived_data", "charts", "emotion", "draft_context", "workbench")
    assert [step.step for step in result.generation_steps] == [
        "derived_data",
        "charts",
        "emotion",
        "draft_context",
        "draft",
    ]
    session = SessionStore(base_dir=str(tmp_path / "tmp" / "analyst_workbench")).get(date(2026, 7, 10))
    assert session.status == WorkbenchStatus.DRAFT_READY
    assert [step["step"] for step in session.generation_steps] == [
        "derived_data",
        "charts",
        "emotion",
        "draft_context",
        "draft",
    ]


async def test_tc_p455_01_given_derived_failure_when_generate_then_draft_not_started(tmp_path):
    service = FailingDerivedGenerateService(
        project_root=tmp_path,
        chart_provider=_should_not_call,
        emotion_provider=_should_not_call,
        base_dir="tmp/analyst_workbench",
    )

    result = await service.generate(date(2026, 7, 10))

    assert result.status == "failed_precondition"
    assert result.steps_completed == ()
    assert result.derived_status == "failed_precondition"
    assert result.draft_status == "not_started"
    assert result.missing_tables == ("theme_cycle_judgement_v2",)
    session = SessionStore(base_dir=str(tmp_path / "tmp" / "analyst_workbench")).get(date(2026, 7, 10))
    assert session.status == WorkbenchStatus.FAILED
    assert session.generation_steps[0]["step"] == "derived_data"


async def test_tc_p455_01_given_approved_session_when_generate_then_derived_not_called(tmp_path):
    td = date(2026, 7, 10)
    base_dir = str(tmp_path / "tmp" / "analyst_workbench")
    session_store = SessionStore(base_dir=base_dir)
    session = session_store.get(td)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    session = session_store.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = session_store.transition(session, WorkbenchStatus.IN_REVIEW)
    session_store.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1)

    service = FailingDerivedGenerateService(
        project_root=tmp_path,
        chart_provider=_should_not_call,
        emotion_provider=_should_not_call,
        base_dir="tmp/analyst_workbench",
    )

    result = await service.generate(td)

    assert result.status == "failed_precondition"
    assert result.derived_status == "not_started"
    assert result.generation_steps[0].step == "generate_guard"
    assert "APPROVED" in result.error


async def test_tc_p455_rb_given_empty_context_when_generate_then_draft_not_started(tmp_path):
    service = EmptyContextGenerateService(
        project_root=tmp_path,
        chart_provider=_charts,
        emotion_provider=_emotion,
        base_dir="tmp/analyst_workbench",
    )

    result = await service.generate(date(2026, 7, 10))

    assert result.status == "failed_precondition"
    assert result.draft_status == "not_started"
    assert result.generation_steps[-1].step == "draft_context"
    assert result.generation_steps[-1].status == "failed_precondition"
    assert "no derived themes or strong stocks" in result.error
    session = SessionStore(base_dir=str(tmp_path / "tmp" / "analyst_workbench")).get(date(2026, 7, 10))
    assert session.status == WorkbenchStatus.FAILED

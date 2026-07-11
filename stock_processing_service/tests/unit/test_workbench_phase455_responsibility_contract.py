"""Phase 4.5.5-RA responsibility boundary regression tests."""

from datetime import date

import pytest

from stock_processing_service.application.services.analyst_workbench.approval_gate import (
    ApprovalRequiredError,
)
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
from stock_processing_service.application.services.analyst_workbench.report_composer import (
    WorkbenchReportComposer,
)
from stock_processing_service.application.services.analyst_workbench.session import (
    SessionStore,
    WorkbenchStatus,
)
from stock_processing_service.application.services.analyst_workbench.snapshot import (
    ReviewSnapshot,
    SnapshotStore,
)


async def _should_not_call(_trade_date: str):
    raise AssertionError("generate pipeline must not be called after approval")


class ForbiddenGenerateService(AnalystWorkbenchGenerateService):
    async def _run_derived_data(self, trade_date, *, force):
        raise AssertionError("derived data must not be generated after approval")

    async def _run_draft_cli(self, trade_date_str):
        raise AssertionError("draft must not be regenerated after approval")


def _approve_snapshot(base_dir: str, td: date, snapshot: ReviewSnapshot) -> ReviewSnapshot:
    session_store = SessionStore(base_dir=base_dir)
    session = session_store.get(td)
    if session.status == WorkbenchStatus.NOT_STARTED:
        session = session_store.transition(session, WorkbenchStatus.GENERATING)
    if session.status == WorkbenchStatus.GENERATING:
        session = session_store.transition(
            session,
            WorkbenchStatus.DRAFT_READY,
            draft_version=snapshot.based_on_draft_version or 1,
        )
    if session.status == WorkbenchStatus.DRAFT_READY:
        session = session_store.transition(session, WorkbenchStatus.IN_REVIEW)
    SnapshotStore(base_dir=base_dir).save(snapshot)
    session_store.transition(
        session,
        WorkbenchStatus.APPROVED,
        snapshot_version=snapshot.snapshot_version,
        approved_by=snapshot.approved_by,
    )
    loaded = SnapshotStore(base_dir=base_dir).load(td)
    assert loaded is not None
    return loaded


async def test_tc_p455_lifecycle_given_draft_ready_when_require_formal_then_rejected(tmp_path):
    td = date(2026, 7, 10)
    base_dir = str(tmp_path / "analyst_workbench")
    session_store = SessionStore(base_dir=base_dir)
    session = session_store.get(td)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    session_store.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)

    with pytest.raises(ApprovalRequiredError, match="Approve the snapshot first"):
        WorkbenchReportComposer(workbench_base_dir=base_dir).require_formal(td)


async def test_tc_p455_e2e_given_analyst_override_when_composed_then_final_report_uses_snapshot(tmp_path):
    td = date(2026, 7, 10)
    base_dir = str(tmp_path / "analyst_workbench")

    ai_draft = AIDraft(
        trade_date=td,
        draft_version=1,
        cognition_cards=[
            {
                "main_theme": {
                    "ai_value": "机器人",
                    "analyst_value": "PCB",
                    "final_value": "PCB",
                    "override": True,
                    "reason": "资金从机器人切换",
                }
            }
        ],
    )
    DraftStore(base_dir=base_dir).save(ai_draft)
    snapshot = ReviewSnapshot.from_draft(
        ai_draft,
        snapshot_version=1,
        approved_by="analyst",
    )
    snapshot.cognition_cards = ai_draft.cognition_cards
    approved_snapshot = _approve_snapshot(base_dir, td, snapshot)

    newer_draft = AIDraft(
        trade_date=td,
        draft_version=2,
        cognition_cards=[
            {
                "main_theme": {
                    "ai_value": "机器人",
                    "final_value": "机器人",
                }
            }
        ],
    )
    DraftStore(base_dir=base_dir).save(newer_draft)

    result = WorkbenchReportComposer(workbench_base_dir=base_dir).compose(td)
    main_theme = result.report["cognition_reviews"][0]["main_theme"]

    assert result.mode == "formal"
    assert main_theme["ai_value"] == "机器人"
    assert main_theme["analyst_value"] == "PCB"
    assert main_theme["final_value"] == "PCB"
    assert result.report["workbench_approval"]["snapshot_hash"] == approved_snapshot.snapshot_hash


async def test_tc_p455_lifecycle_given_approved_snapshot_when_generate_then_snapshot_not_overwritten(tmp_path):
    td = date(2026, 7, 10)
    project_root = tmp_path
    base_dir = str(project_root / "tmp" / "analyst_workbench")
    draft = AIDraft(
        trade_date=td,
        draft_version=1,
        cognition_cards=[{"main_theme": {"final_value": "PCB"}}],
    )
    snapshot = ReviewSnapshot.from_draft(draft, snapshot_version=1, approved_by="analyst")
    snapshot.cognition_cards = draft.cognition_cards
    approved_snapshot = _approve_snapshot(base_dir, td, snapshot)

    service = ForbiddenGenerateService(
        project_root=project_root,
        chart_provider=_should_not_call,
        emotion_provider=_should_not_call,
        base_dir="tmp/analyst_workbench",
    )

    result = await service.generate(td)
    reloaded = SnapshotStore(base_dir=base_dir).load(td)

    assert result.status == "failed_precondition"
    assert result.derived_status == "not_started"
    assert result.generation_steps[0].step == "generate_guard"
    assert reloaded is not None
    assert reloaded.snapshot_hash == approved_snapshot.snapshot_hash
    assert reloaded.cognition_cards[0]["main_theme"]["final_value"] == "PCB"

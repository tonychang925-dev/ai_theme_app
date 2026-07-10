"""Phase 4.5.5 — Formal compose gate tests."""

from datetime import date

import pytest

from stock_processing_service.application.services.analyst_workbench.draft import (
    AIDraft,
    DraftStore,
)
from stock_processing_service.application.services.analyst_workbench.formal_gate import (
    FormalComposeGuardError,
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


def _approve_snapshot(base_dir: str, td: date, snapshot: ReviewSnapshot) -> None:
    ss = SessionStore(base_dir=base_dir)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=snapshot.based_on_draft_version or 1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)
    SnapshotStore(base_dir=base_dir).save(snapshot)
    ss.transition(session, WorkbenchStatus.APPROVED, snapshot_version=snapshot.snapshot_version, approved_by=snapshot.approved_by)


def test_tc_p455_03_b_given_newer_draft_when_formal_compose_then_uses_snapshot_hash(tmp_path):
    td = date(2026, 7, 10)
    base_dir = str(tmp_path / "analyst_workbench")
    draft_store = DraftStore(base_dir=base_dir)

    draft_v1 = AIDraft(
        trade_date=td,
        draft_version=1,
        cognition_cards=[{"main_theme": {"final_value": "PCB"}}],
    )
    draft_store.save(draft_v1)
    snapshot = ReviewSnapshot.from_draft(
        draft_v1,
        snapshot_version=1,
        approved_by="analyst",
    )
    snapshot.cognition_cards = [{"main_theme": {"final_value": "PCB"}}]
    _approve_snapshot(base_dir, td, snapshot)
    snapshot_hash = SnapshotStore(base_dir=base_dir).load(td).snapshot_hash

    draft_v2 = AIDraft(
        trade_date=td,
        draft_version=2,
        cognition_cards=[{"main_theme": {"final_value": "机器人"}}],
    )
    draft_store.save(draft_v2)

    result = WorkbenchReportComposer(workbench_base_dir=base_dir).compose(td)

    assert result.mode == "formal"
    assert result.report["cognition_reviews"][0]["main_theme"]["final_value"] == "PCB"
    assert result.report["workbench_approval"]["snapshot_hash"] == snapshot_hash
    assert result.report["workbench_approval"]["composition_mode"] == "formal"


def test_tc_p455_03_given_missing_hash_when_require_formal_then_rejected(tmp_path):
    td = date(2026, 7, 10)
    base_dir = str(tmp_path / "analyst_workbench")
    draft = AIDraft(trade_date=td, draft_version=1)
    snapshot = ReviewSnapshot.from_draft(draft, snapshot_version=1, approved_by="analyst")
    _approve_snapshot(base_dir, td, snapshot)

    snapshot_path = tmp_path / "analyst_workbench" / td.isoformat() / "snapshot.json"
    raw = snapshot_path.read_text(encoding="utf-8")
    snapshot_path.write_text(raw.replace(f'"snapshot_hash": "{SnapshotStore(base_dir=base_dir).load(td).snapshot_hash}"', '"snapshot_hash": ""'), encoding="utf-8")

    with pytest.raises(FormalComposeGuardError, match="snapshot_hash"):
        WorkbenchReportComposer(workbench_base_dir=base_dir).require_formal(td)

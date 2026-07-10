"""Phase 4.5.2 — Tests for Report Composer Approval Gate."""

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from stock_processing_service.application.services.analyst_workbench.approval_gate import (
    ApprovalGate,
    ApprovalRequiredError,
    ReportApproval,
)
from stock_processing_service.application.services.analyst_workbench.session import (
    SessionStore,
    WorkbenchSession,
    WorkbenchStatus,
)
from stock_processing_service.application.services.analyst_workbench.draft import (
    AIDraft,
    DraftStore,
)
from stock_processing_service.application.services.analyst_workbench.snapshot import (
    ReviewSnapshot,
    SnapshotStore,
)


@pytest.fixture
def tmp_store():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "analyst_workbench"
        yield str(base)


@pytest.fixture
def td():
    return date(2026, 7, 9)


# ── Approval Gate: NOT_STARTED ──

def test_not_started_returns_preview(tmp_store, td):
    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.check(td)
    assert approval.mode == "preview"
    assert approval.can_generate_report is False
    assert approval.snapshot is None
    assert approval.snapshot_version == 0
    assert "NOT_STARTED" in approval.reason


# ── Approval Gate: DRAFT_READY ──

def test_draft_ready_returns_preview(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)

    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.check(td)
    assert approval.mode == "preview"
    assert approval.can_generate_report is False
    assert approval.snapshot is None


# ── Approval Gate: APPROVED → formal report ──

def test_approved_returns_formal(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)

    # Create draft and snapshot
    draft = AIDraft(trade_date=td, draft_version=1,
                    attention_state={"charts_available": 3})
    ds = DraftStore(base_dir=tmp_store)
    ds.save(draft)

    snap = ReviewSnapshot.from_draft(draft, snapshot_version=1, approved_by="analyst")
    sst = SnapshotStore(base_dir=tmp_store)
    sst.save(snap)

    session = ss.transition(session, WorkbenchStatus.APPROVED,
                            snapshot_version=1, approved_by="analyst")

    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.check(td)
    assert approval.mode == "formal"
    assert approval.can_generate_report is True
    assert approval.snapshot is not None
    assert approval.snapshot_version == 1
    assert approval.approved_by == "analyst"


# ── Approval Gate: PUBLISHED → published report ──

def test_published_returns_published(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)

    draft = AIDraft(trade_date=td, draft_version=1)
    ds = DraftStore(base_dir=tmp_store)
    ds.save(draft)

    snap = ReviewSnapshot.from_draft(draft, snapshot_version=1, approved_by="analyst")
    sst = SnapshotStore(base_dir=tmp_store)
    sst.save(snap)

    session = ss.transition(session, WorkbenchStatus.APPROVED,
                            snapshot_version=1, approved_by="analyst")
    session = ss.transition(session, WorkbenchStatus.PUBLISHED)

    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.check(td)
    assert approval.mode == "published"
    assert approval.can_generate_report is True


# ── require_formal raises when no approved snapshot ──

def test_require_formal_raises_when_not_approved(tmp_store, td):
    gate = ApprovalGate(base_dir=tmp_store)
    with pytest.raises(ApprovalRequiredError) as exc:
        gate.require_formal(td)
    assert "NOT_STARTED" in str(exc.value)


def test_require_formal_passes_when_approved(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)

    draft = AIDraft(trade_date=td, draft_version=1)
    ds = DraftStore(base_dir=tmp_store)
    ds.save(draft)

    snap = ReviewSnapshot.from_draft(draft, snapshot_version=1)
    sst = SnapshotStore(base_dir=tmp_store)
    sst.save(snap)

    session = ss.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1)

    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.require_formal(td)
    assert approval.mode == "formal"


# ── Regenerate does not affect approved snapshot ──

def test_regenerate_does_not_overwrite_approved_snapshot(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)

    draft = AIDraft(trade_date=td, draft_version=1,
                    attention_state={"version": 1})
    ds = DraftStore(base_dir=tmp_store)
    ds.save(draft)

    snap_v1 = ReviewSnapshot.from_draft(draft, snapshot_version=1, approved_by="analyst")
    sst = SnapshotStore(base_dir=tmp_store)
    sst.save(snap_v1)

    session = ss.transition(session, WorkbenchStatus.APPROVED,
                            snapshot_version=1, approved_by="analyst")

    # Simulate regenerate: create draft v2, but snapshot should remain v1
    draft_v2 = AIDraft(trade_date=td, draft_version=2, supersedes_version=1,
                       attention_state={"version": 2})
    ds.save(draft_v2)
    session.draft_version = 2
    ss.save(session)

    # Snapshot should still be v1
    loaded = sst.load(td)
    assert loaded is not None
    assert loaded.snapshot_version == 1
    assert loaded.attention_state == {"version": 1}

    # Gate should still return formal with v1 snapshot
    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.check(td)
    assert approval.mode == "formal"
    assert approval.snapshot_version == 1


# ── IN_REVIEW returns preview ──

def test_in_review_returns_preview(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)

    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.check(td)
    assert approval.mode == "preview"
    assert approval.can_generate_report is False


# ── Edge case: APPROVED / PUBLISHED but snapshot missing → blocked ──

def test_approved_without_snapshot_returns_blocked(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)
    session = ss.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1, approved_by="analyst")
    # Session is APPROVED but no snapshot.json was ever created on disk

    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.check(td)
    assert approval.mode == "blocked"
    assert approval.can_generate_report is False
    assert "snapshot.json is missing" in approval.reason


def test_published_without_snapshot_returns_blocked(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)
    session = ss.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1)
    session = ss.transition(session, WorkbenchStatus.PUBLISHED)
    # No snapshot file written

    gate = ApprovalGate(base_dir=tmp_store)
    approval = gate.check(td)
    assert approval.mode == "blocked"
    assert "snapshot.json is missing" in approval.reason

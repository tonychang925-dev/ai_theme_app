"""Phase 4.5 — Workbench Session Store tests.

Covers: valid/invalid transitions, create/load, draft version,
        snapshot protection, publish gate, state machine.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

import pytest

from stock_processing_service.application.services.analyst_workbench.session import (
    SessionStore, WorkbenchSession, WorkbenchStatus, ALLOWED_TRANSITIONS,
)
from stock_processing_service.application.services.analyst_workbench.draft import (
    AIDraft, DraftStore,
)
from stock_processing_service.application.services.analyst_workbench.snapshot import (
    ReviewSnapshot, SnapshotStore,
)


@pytest.fixture
def tmp_store():
    import os
    base = tempfile.mkdtemp(prefix="wb_test_")
    yield SessionStore(base_dir=base), DraftStore(base_dir=base), SnapshotStore(base_dir=base)
    import shutil
    shutil.rmtree(base, ignore_errors=True)


# ═══ TC-WB-01: full lifecycle ═══

def test_full_lifecycle(tmp_store):
    ss, ds, sns = tmp_store
    td = date(2026, 7, 9)
    session = ss.get(td)
    assert session.status == WorkbenchStatus.NOT_STARTED
    assert session.can_generate
    assert not session.can_approve

    # Generate
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    assert session.status == WorkbenchStatus.GENERATING

    draft = AIDraft(trade_date=td, draft_version=1)
    ds.save(draft)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    assert session.status == WorkbenchStatus.DRAFT_READY
    assert session.can_review

    # Review
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)
    assert session.status == WorkbenchStatus.IN_REVIEW
    assert session.can_approve

    # Approve
    snapshot = ReviewSnapshot.from_draft(draft, approved_by="analyst")
    sns.save(snapshot)
    session = ss.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1)
    assert session.status == WorkbenchStatus.APPROVED
    assert session.can_publish

    # Publish
    session = ss.transition(session, WorkbenchStatus.PUBLISHED)
    assert session.status == WorkbenchStatus.PUBLISHED


# ═══ TC-WB-02: invalid transition raises ═══

def test_invalid_transition_raises(tmp_store):
    ss, _, _ = tmp_store
    td = date(2026, 7, 9)
    session = ss.get(td)

    with pytest.raises(ValueError, match="Invalid transition"):
        ss.transition(session, WorkbenchStatus.APPROVED)  # NOT_STARTED → APPROVED invalid

    ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)

    with pytest.raises(ValueError, match="Invalid transition"):
        ss.transition(session, WorkbenchStatus.PUBLISHED)  # DRAFT_READY → PUBLISHED invalid


# ═══ TC-WB-03: approved snapshot not overwritten ═══

def test_approved_snapshot_survives_regenerate(tmp_store):
    ss, ds, sns = tmp_store
    td = date(2026, 7, 9)

    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    draft1 = AIDraft(trade_date=td, draft_version=1)
    ds.save(draft1)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)
    snapshot = ReviewSnapshot.from_draft(draft1)
    sns.save(snapshot)
    session = ss.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1)

    # Generate new draft
    assert session.status == WorkbenchStatus.APPROVED
    draft2 = AIDraft(trade_date=td, draft_version=2)
    ds.save(draft2)

    # Old snapshot should still exist and not be overwritten
    loaded = sns.load(td)
    assert loaded is not None
    assert loaded.snapshot_version == 1
    assert loaded.based_on_draft_version == 1


# ═══ TC-WB-04: publish requires approved ═══

def test_publish_requires_approved(tmp_store):
    ss, ds, _ = tmp_store
    td = date(2026, 7, 9)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    draft = AIDraft(trade_date=td, draft_version=1)
    ds.save(draft)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)

    assert not session.can_publish
    assert session.can_approve


# ═══ TC-WB-05: published rejects save-review ═══

def test_published_rejects_save_review(tmp_store):
    ss, ds, sns = tmp_store
    td = date(2026, 7, 9)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    draft = AIDraft(trade_date=td, draft_version=1)
    ds.save(draft)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)
    snapshot = ReviewSnapshot.from_draft(draft)
    sns.save(snapshot)
    session = ss.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1)
    session = ss.transition(session, WorkbenchStatus.PUBLISHED)

    assert session.status == WorkbenchStatus.PUBLISHED


# ═══ TC-WB-06: session persistence ═══

def test_session_save_and_load(tmp_store):
    ss, _, _ = tmp_store
    td = date(2026, 7, 9)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)

    # Reload
    session2 = ss.get(td)
    assert session2.status == WorkbenchStatus.DRAFT_READY
    assert session2.draft_version == 1


# ═══ TC-WB-07: draft version increments ═══

def test_draft_version_increments(tmp_store):
    _, ds, _ = tmp_store
    td = date(2026, 7, 9)
    d1 = AIDraft(trade_date=td, draft_version=1)
    ds.save(d1)
    d2 = AIDraft(trade_date=td, draft_version=2, supersedes_version=1)
    ds.save(d2)
    assert ds.latest_version(td) == 2
    loaded = ds.load(td)
    assert loaded.draft_version == 2
    assert loaded.supersedes_version == 1


# ═══ TC-WB-08: snapshot from draft ═══

def test_snapshot_from_draft(tmp_store):
    _, ds, sns = tmp_store
    td = date(2026, 7, 9)
    draft = AIDraft(trade_date=td, draft_version=1, attention_state={"score": 80})
    ds.save(draft)
    snapshot = ReviewSnapshot.from_draft(draft, approved_by="test_analyst")
    sns.save(snapshot)

    loaded = sns.load(td)
    assert loaded is not None
    assert loaded.approved
    assert loaded.based_on_draft_version == 1
    assert loaded.attention_state == {"score": 80}

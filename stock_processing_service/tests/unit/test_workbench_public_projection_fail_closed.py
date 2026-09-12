from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException

import stock_processing_service.api_app as api_app
from stock_processing_service.application.services.analyst_workbench.approval_contract import (
    ApprovalPrincipal,
    ReviewStateStore,
    RuntimeIntegrityVerifier,
    project_root,
)
from stock_processing_service.application.services.analyst_workbench.draft import (
    AIDraft,
    DraftStore,
)
from stock_processing_service.application.services.analyst_workbench.session import (
    SessionStore,
    WorkbenchStatus,
)
from stock_processing_service.application.services.analyst_workbench.snapshot import (
    ReviewSnapshot,
    SnapshotStore,
)


TRADE_DATE = date(2026, 7, 10)


def _workspace_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path
    fake_api_path = root / "stock_processing_service" / "api_app.py"
    fake_api_path.parent.mkdir(parents=True)
    monkeypatch.setattr(api_app, "__file__", str(fake_api_path))
    base = root / "tmp" / "analyst_workbench"
    monkeypatch.setattr(
        api_app,
        "_require_workbench_principal",
        lambda request: ApprovalPrincipal("7", "analyst@example.test", "analyst"),
    )
    return base


def _prepare_state(base: Path, status: str) -> tuple[ReviewSnapshot, dict]:
    principal = ApprovalPrincipal("7", "analyst@example.test", "analyst")
    review_state = ReviewStateStore(base).save(
        trade_date=TRADE_DATE,
        workspace={"themes": [], "watch_groups": [], "overrides": {}},
        principal=principal,
    )
    draft = AIDraft(
        trade_date=TRADE_DATE,
        draft_version=1,
        cognition_cards=[
            {
                "subject_id": "theme:main",
                "subject_name": "主线",
                "state": "PCB",
                "score": 91,
            }
        ],
    )
    DraftStore(base_dir=base).save(draft)

    session_store = SessionStore(base_dir=base)
    session = session_store.get(TRADE_DATE)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    session = session_store.transition(
        session, WorkbenchStatus.DRAFT_READY, draft_version=1
    )
    session = session_store.transition(session, WorkbenchStatus.IN_REVIEW)

    snapshot = ReviewSnapshot.from_draft(
        draft,
        snapshot_version=1,
        approved_by=principal.identity,
        reviewed_by=principal.identity,
        review_state_hash=review_state["state_hash"],
        runtime_manifest_hash=RuntimeIntegrityVerifier.verify(project_root()),
    )
    snapshot.override_summary = {"total": 2}
    SnapshotStore(base_dir=base).save(snapshot)

    session = session_store.transition(
        session,
        WorkbenchStatus.APPROVED,
        snapshot_version=1,
        approved_by=principal.identity,
        snapshot_hash=snapshot.snapshot_hash,
    )
    if status == WorkbenchStatus.PUBLISHED:
        snapshot = SnapshotStore(base_dir=base).publish(
            snapshot, published_by=principal.identity
        )
        session = session_store.transition(
            session,
            WorkbenchStatus.PUBLISHED,
            snapshot_version=snapshot.snapshot_version,
            published_by=principal.identity,
            published_snapshot_hash=snapshot.snapshot_hash,
        )
    return snapshot, review_state


def _request() -> object:
    return type("Request", (), {"headers": {}})()


def _call_workspace() -> dict:
    return asyncio.run(
        api_app.get_analyst_workspace(TRADE_DATE.isoformat(), _request())
    )


def _projection_failure_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    base = _workspace_base(tmp_path, monkeypatch)
    _prepare_state(base, status)

    def fail_projection(cognition_cards, attention_state):
        raise RuntimeError("secret projection failure")

    monkeypatch.setattr(api_app, "_workspace_themes_from_cards", fail_projection)


def test_approved_workspace_uses_validated_snapshot_and_final_values(
    tmp_path, monkeypatch
) -> None:
    base = _workspace_base(tmp_path, monkeypatch)
    snapshot, _ = _prepare_state(base, WorkbenchStatus.APPROVED)
    projected_cards = []
    original_projection = api_app._workspace_themes_from_cards

    def spy_projection(cognition_cards, attention_state):
        projected_cards.append(cognition_cards)
        return original_projection(cognition_cards, attention_state)

    monkeypatch.setattr(api_app, "_workspace_themes_from_cards", spy_projection)
    result = _call_workspace()

    assert result["analyst_finalized"] is True
    assert result["is_ai_draft"] is False
    assert result["override_count"] == 2
    assert projected_cards == [snapshot.cognition_cards]
    assert result["themes"][0]["subject_name"] == "主线"
    assert result["themes"][0]["stage_judgement"] == "PCB"


@pytest.mark.parametrize(
    "status",
    [WorkbenchStatus.APPROVED, WorkbenchStatus.PUBLISHED],
)
def test_approved_projection_failure_does_not_fall_back_to_draft(
    tmp_path, monkeypatch, status: str
) -> None:
    _projection_failure_setup(tmp_path, monkeypatch, status)

    with pytest.raises(HTTPException) as excinfo:
        _call_workspace()

    assert excinfo.value.status_code == 500
    assert excinfo.value.detail == {
        "code": "approved_snapshot_projection_failed",
        "error": "Approved Snapshot public projection failed",
    }
    assert "secret projection failure" not in json.dumps(excinfo.value.detail)


def test_runtime_manifest_mismatch_still_fails_closed(tmp_path, monkeypatch) -> None:
    base = _workspace_base(tmp_path, monkeypatch)
    _prepare_state(base, WorkbenchStatus.APPROVED)
    snapshot_path = base / TRADE_DATE.isoformat() / "snapshots" / "snapshot_v1.json"
    raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    raw["runtime_manifest_hash"] = "0" * 64
    raw["snapshot_hash"] = ReviewSnapshot.from_dict(raw).compute_hash()
    snapshot_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(HTTPException) as excinfo:
        _call_workspace()
    assert excinfo.value.status_code == 503
    assert excinfo.value.status_code == 503


def test_review_state_mismatch_still_fails_closed(tmp_path, monkeypatch) -> None:
    base = _workspace_base(tmp_path, monkeypatch)
    _prepare_state(base, WorkbenchStatus.APPROVED)
    ReviewStateStore(base).save(
        trade_date=TRADE_DATE,
        workspace={
            "themes": [{"subject_name": "changed"}],
            "watch_groups": [],
            "overrides": {},
        },
        principal=ApprovalPrincipal("7", "analyst@example.test", "analyst"),
    )

    with pytest.raises(HTTPException) as excinfo:
        _call_workspace()
    assert excinfo.value.status_code == 503
    assert "review_state_mismatch" in excinfo.value.detail


def test_snapshot_hash_mismatch_still_fails_closed(tmp_path, monkeypatch) -> None:
    base = _workspace_base(tmp_path, monkeypatch)
    _prepare_state(base, WorkbenchStatus.APPROVED)
    snapshot_path = base / TRADE_DATE.isoformat() / "snapshots" / "snapshot_v1.json"
    raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    raw["cognition_cards"][0]["state"] = "tampered"
    snapshot_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(HTTPException) as excinfo:
        _call_workspace()
    assert excinfo.value.status_code == 503
    assert "hash_mismatch" in excinfo.value.detail


def test_draft_ready_without_snapshot_remains_preview(tmp_path, monkeypatch) -> None:
    base = _workspace_base(tmp_path, monkeypatch)
    principal = ApprovalPrincipal("7", "analyst@example.test", "analyst")
    draft = AIDraft(
        trade_date=TRADE_DATE,
        draft_version=1,
        cognition_cards=[
            {
                "subject_id": "theme:draft",
                "subject_name": "草稿",
                "state": "AI",
                "score": 70,
            }
        ],
    )
    DraftStore(base_dir=base).save(draft)
    session_store = SessionStore(base_dir=base)
    session = session_store.get(TRADE_DATE)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    session = session_store.transition(
        session, WorkbenchStatus.DRAFT_READY, draft_version=1
    )
    assert session.status == WorkbenchStatus.DRAFT_READY

    result = _call_workspace()
    assert result["is_ai_draft"] is True
    assert result["analyst_finalized"] is False
    assert result["draft_version"] == 1
    assert result["themes"][0]["stage_judgement"] == "AI"

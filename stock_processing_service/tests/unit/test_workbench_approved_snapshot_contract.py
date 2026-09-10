from datetime import date
import json

import pytest

from stock_processing_service.application.services.analyst_workbench.approval_contract import (
    ApprovalAuthorizationError,
    ApprovalPrincipal,
    ReviewStateError,
    ReviewStateStore,
    RuntimeIntegrityVerifier,
    build_runtime_manifest,
    project_root,
    require_approval_principal,
)
from stock_processing_service.application.services.analyst_workbench.draft import (
    AIDraft,
)
from stock_processing_service.application.services.analyst_workbench.review_merger import (
    AnalystReviewMerger,
)
from stock_processing_service.application.services.analyst_workbench.snapshot import (
    ReviewSnapshot,
)


def test_approval_principal_rejects_unauthenticated_and_default_literal():
    with pytest.raises(ApprovalAuthorizationError):
        require_approval_principal(None)
    with pytest.raises(ApprovalAuthorizationError):
        require_approval_principal("Bearer expired")


def test_approval_principal_binds_authenticated_authorized_actor(monkeypatch):
    import web_app_service.auth as auth

    monkeypatch.setattr(
        auth,
        "verify_token",
        lambda token: (
            {"sub": "7", "email": "Analyst@Example.Test", "role": "analyst"}
            if token == "valid"
            else None
        ),
    )
    principal = require_approval_principal("Bearer valid")
    assert principal.identity == "user:7:analyst@example.test"

    monkeypatch.setattr(
        auth,
        "verify_token",
        lambda token: {"sub": "8", "email": "user@example.test", "role": "user"},
    )
    with pytest.raises(ApprovalAuthorizationError, match="not authorized"):
        require_approval_principal("Bearer valid")


def test_persisted_analyst_override_changes_final_approved_values(tmp_path):
    trade_date = date(2026, 7, 10)
    principal = ApprovalPrincipal("7", "analyst@example.test", "analyst")
    store = ReviewStateStore(tmp_path)
    draft = AIDraft(
        trade_date=trade_date,
        draft_version=2,
        cognition_cards=[
            {
                "subject_id": "theme:main",
                "subject_name": "主线",
                "stage_judgement": "机器人",
            }
        ],
    )
    workspace = {
        "themes": [
            {
                "subject_id": "theme:main",
                "subject_name": "主线",
                "stage_judgement": "PCB",
                "field_overrides": {
                    "stage_judgement": {
                        "ai_value": "机器人",
                        "analyst_value": "PCB",
                        "reason": "资金切换",
                    }
                },
            }
        ]
    }
    state = store.save(trade_date=trade_date, workspace=workspace, principal=principal)
    merged = AnalystReviewMerger().merge(draft=draft, workspace=workspace)
    snapshot = ReviewSnapshot.from_merged(
        trade_date=trade_date,
        draft=draft,
        merged=merged,
        snapshot_version=1,
        approved_by=principal.identity,
        reviewed_by=principal.identity,
        review_state_hash=state["state_hash"],
        runtime_manifest_hash=RuntimeIntegrityVerifier.verify(project_root()),
    )

    judgement = snapshot.cognition_cards[0]["stage_judgement"]
    assert judgement["analyst_value"] == "PCB"
    assert judgement["final_value"] == "PCB"
    assert snapshot.review_state_hash == state["state_hash"]
    assert snapshot.reviewed_by == principal.identity
    assert snapshot.runtime_integrity_status == "verified"


def test_review_state_tampering_fails_closed(tmp_path):
    trade_date = date(2026, 7, 10)
    principal = ApprovalPrincipal("7", "analyst@example.test", "analyst")
    store = ReviewStateStore(tmp_path)
    state = store.save(
        trade_date=trade_date,
        workspace={"themes": [], "watch_groups": [], "overrides": {}},
        principal=principal,
    )
    state["overrides"] = {"injected": True}
    (tmp_path / trade_date.isoformat() / "review_state.json").write_text(
        json.dumps(state, ensure_ascii=False)
    )
    with pytest.raises(ReviewStateError, match="hash mismatch"):
        store.load(trade_date)


def test_runtime_manifest_covers_public_projection_closure():
    manifest = build_runtime_manifest(project_root())
    paths = {entry["path"] for entry in manifest["files"]}
    assert "stock_processing_service/api_app.py" in paths
    assert "web_app_service/auth/__init__.py" in paths
    assert any(path.endswith("snapshot_validator.py") for path in paths)
    assert any(path.endswith("review_merger.py") for path in paths)
    assert any(path.endswith("post_market_engine_report_composer.py") for path in paths)
    assert RuntimeIntegrityVerifier.verify(
        project_root()
    ) == RuntimeIntegrityVerifier.manifest_hash(manifest)

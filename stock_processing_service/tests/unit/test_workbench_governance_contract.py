from __future__ import annotations

import json
import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

import stock_processing_service.api_app as api_app
from stock_processing_service.application.services.analyst_workbench.approval_contract import (
    ApprovalPrincipal,
    ReviewStateStore,
    RuntimeIntegrityVerifier,
    project_root,
)
from stock_processing_service.application.services.analyst_workbench.approval_gate import (
    ApprovalGate,
    WorkbenchGovernedProductReadModel,
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
PRINCIPAL = ApprovalPrincipal("7", "analyst@example.test", "analyst")


@pytest.fixture
def base(tmp_path: Path) -> Path:
    return tmp_path / "analyst_workbench"


def draft(version: int, **overrides: object) -> AIDraft:
    values = {
        "trade_date": TRADE_DATE,
        "draft_version": version,
        "supersedes_version": version - 1,
        "assumptions": ["market-close-input"],
        "limitations": ["no-intraday-recalculation"],
        "narrative": {"main_story": "governed-public-judgment"},
    }
    values.update(overrides)
    return AIDraft(**values)


def approve(
    base: Path, *, draft_version: int = 1
) -> tuple[SessionStore, ReviewSnapshot]:
    session_store = SessionStore(base_dir=str(base))
    draft_store = DraftStore(base_dir=str(base))
    snapshot_store = SnapshotStore(base_dir=str(base))
    draft_store.save(draft(draft_version))
    ReviewStateStore(base).save(
        trade_date=TRADE_DATE,
        workspace={"themes": [], "watch_groups": [], "overrides": {}},
        principal=PRINCIPAL,
    )
    snapshot = ReviewSnapshot.from_draft(
        draft(draft_version),
        snapshot_version=1,
        approved_by=PRINCIPAL.identity,
        reviewed_by=PRINCIPAL.identity,
        review_state_hash=ReviewStateStore(base).load(TRADE_DATE)["state_hash"],
        runtime_manifest_hash=RuntimeIntegrityVerifier.verify(project_root()),
    )
    snapshot_store.save(snapshot)
    session = session_store.get(TRADE_DATE)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    session = session_store.transition(
        session, WorkbenchStatus.DRAFT_READY, draft_version=draft_version
    )
    session = session_store.transition(session, WorkbenchStatus.IN_REVIEW)
    session_store.transition(
        session,
        WorkbenchStatus.APPROVED,
        snapshot_version=1,
        approved_by=PRINCIPAL.identity,
        snapshot_hash=snapshot.snapshot_hash,
    )
    return session_store, snapshot


def test_g2b_at01_revisions_are_create_once(base: Path) -> None:
    drafts = DraftStore(base_dir=str(base))
    snapshots = SnapshotStore(base_dir=str(base))
    first_draft = drafts.save(draft(1))
    first_snapshot = snapshots.save(
        ReviewSnapshot.from_draft(
            draft(1),
            approved_by=PRINCIPAL.identity,
            reviewed_by=PRINCIPAL.identity,
        )
    )
    draft_bytes = first_draft.read_bytes()
    snapshot_bytes = first_snapshot.read_bytes()

    with pytest.raises(ValueError, match="already exists"):
        drafts.save(draft(1))
    with pytest.raises(ValueError, match="already exists"):
        snapshots.save(
            ReviewSnapshot.from_draft(
                draft(1),
                approved_by=PRINCIPAL.identity,
                reviewed_by=PRINCIPAL.identity,
            )
        )

    assert first_draft.read_bytes() == draft_bytes
    assert first_snapshot.read_bytes() == snapshot_bytes

    with ThreadPoolExecutor(max_workers=2) as executor:
        draft_results = list(
            executor.map(
                lambda version: _save_quietly(drafts, draft(version)),
                [2, 2],
            )
        )
        snapshot_results = list(
            executor.map(
                lambda version: _save_quietly(
                    snapshots,
                    ReviewSnapshot.from_draft(
                        draft(version),
                        snapshot_version=version,
                        approved_by=PRINCIPAL.identity,
                        reviewed_by=PRINCIPAL.identity,
                    ),
                ),
                [2, 2],
            )
        )
    assert draft_results.count(True) == 1
    assert snapshot_results.count(True) == 1
    assert drafts.latest_version(TRADE_DATE) == 2
    assert snapshots.latest_version(TRADE_DATE) == 2
    assert first_draft.read_bytes() == draft_bytes
    assert first_snapshot.read_bytes() == snapshot_bytes


def _save_quietly(store: DraftStore | SnapshotStore, value: AIDraft | ReviewSnapshot) -> bool:
    try:
        store.save(value)
        return True
    except ValueError:
        return False


def test_g2b_at02_numeric_authority_is_explicit_and_mtime_immune(base: Path) -> None:
    drafts = DraftStore(base_dir=str(base))
    for version in range(1, 11):
        drafts.save(draft(version))
    old = base / TRADE_DATE.isoformat() / "drafts" / "draft_v9.json"
    future = datetime.now(timezone.utc).timestamp() + 1000
    os.utime(old, (future, future))

    assert drafts.latest_version(TRADE_DATE) == 10
    assert drafts.load(TRADE_DATE).draft_version == 10


def test_g2b_at03_lineage_and_pointer_mismatch_fail_closed(base: Path) -> None:
    drafts = DraftStore(base_dir=str(base))
    drafts.save(draft(1))
    with pytest.raises(ValueError, match="out of order"):
        drafts.save(draft(3, supersedes_version=2))

    snapshots = SnapshotStore(base_dir=str(base))
    approved = ReviewSnapshot.from_draft(
        draft(1), approved_by=PRINCIPAL.identity, reviewed_by=PRINCIPAL.identity
    )
    snapshots.save(approved)
    bad_child = ReviewSnapshot.from_draft(
        draft(2),
        snapshot_version=2,
        approved_by=PRINCIPAL.identity,
        reviewed_by=PRINCIPAL.identity,
    )
    bad_child.supersedes_snapshot_version = 1
    bad_child.parent_snapshot_hash = "0" * 64
    with pytest.raises(ValueError, match="parent hash mismatch"):
        snapshots.save(bad_child)

    pointer = base / TRADE_DATE.isoformat() / "snapshot_authority.json"
    payload = json.loads(pointer.read_text())
    payload["current_version"] = 2
    pointer.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        snapshots.load(TRADE_DATE)


def test_g2b_at04_draft_and_review_are_preview_only(base: Path) -> None:
    session_store = SessionStore(base_dir=str(base))
    drafts = DraftStore(base_dir=str(base))
    drafts.save(draft(1))
    session = session_store.get(TRADE_DATE)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    session = session_store.transition(
        session, WorkbenchStatus.DRAFT_READY, draft_version=1
    )
    gate = ApprovalGate(base_dir=str(base))
    assert gate.check(TRADE_DATE).mode == "preview"
    assert WorkbenchGovernedProductReadModel(gate).read(TRADE_DATE) is None

    session = session_store.transition(session, WorkbenchStatus.IN_REVIEW)
    assert gate.check(TRADE_DATE).mode == "preview"
    assert WorkbenchGovernedProductReadModel(gate).read(TRADE_DATE) is None


def test_g2b_at05_integrity_failures_do_not_fall_back(base: Path) -> None:
    _, approved = approve(base)
    revision = base / TRADE_DATE.isoformat() / "snapshots" / "snapshot_v1.json"
    payload = json.loads(revision.read_text())
    payload["review_state_hash"] = "0" * 64
    revision.write_text(json.dumps(payload), encoding="utf-8")
    approval = ApprovalGate(base_dir=str(base)).check(TRADE_DATE)
    assert approval.mode == "blocked"
    assert approval.snapshot is None
    assert (
        WorkbenchGovernedProductReadModel(ApprovalGate(base_dir=str(base))).read(
            TRADE_DATE
        )
        is None
    )

    _, approved = approve(base / "runtime-drift")
    revision = base / "runtime-drift" / TRADE_DATE.isoformat() / "snapshots" / "snapshot_v1.json"
    payload = json.loads(revision.read_text())
    payload["runtime_manifest_hash"] = "0" * 64
    payload["snapshot_hash"] = ReviewSnapshot.from_dict(payload).compute_hash()
    revision.write_text(json.dumps(payload), encoding="utf-8")
    authority_path = (
        base / "runtime-drift" / TRADE_DATE.isoformat() / "snapshot_authority.json"
    )
    authority = json.loads(authority_path.read_text())
    authority["current_hash"] = payload["snapshot_hash"]
    authority_path.write_text(json.dumps(authority), encoding="utf-8")
    drifted = ApprovalGate(base_dir=str(base / "runtime-drift")).check(TRADE_DATE)
    assert drifted.mode == "blocked"
    assert "runtime manifest hash mismatch" in drifted.reason


def test_g2b_at06_generation_and_publication_require_principal(base: Path) -> None:
    def denied(request):
        raise api_app.HTTPException(status_code=401, detail="authentication required")

    original = api_app._require_workbench_principal
    api_app._require_workbench_principal = denied
    try:
        with pytest.raises(api_app.HTTPException) as draft_error:
            asyncio.run(
                api_app.generate_workbench_draft(TRADE_DATE.isoformat(), object())
            )
        with pytest.raises(api_app.HTTPException) as publish_error:
            asyncio.run(api_app.publish_workbench(TRADE_DATE.isoformat(), object()))
    finally:
        api_app._require_workbench_principal = original
    assert draft_error.value.status_code == 401
    assert publish_error.value.status_code == 401


def test_g2b_at07_publish_revalidates_and_creates_immutable_revision(
    base: Path,
) -> None:
    session_store, approved = approve(base)
    snapshots = SnapshotStore(base_dir=str(base))
    gate = ApprovalGate(base_dir=str(base))
    assert gate.check(TRADE_DATE).mode == "formal"
    published = snapshots.publish(approved, published_by=PRINCIPAL.identity)
    session = session_store.get(TRADE_DATE)
    session_store.transition(
        session,
        WorkbenchStatus.PUBLISHED,
        snapshot_version=published.snapshot_version,
        published_by=PRINCIPAL.identity,
        published_snapshot_hash=published.snapshot_hash,
    )
    approval = ApprovalGate(base_dir=str(base)).check(TRADE_DATE)
    assert approval.mode == "published"
    assert published.snapshot_version == 2
    assert published.supersedes_snapshot_version == 1
    assert published.parent_snapshot_hash == approved.snapshot_hash
    assert snapshots.load(TRADE_DATE, version=1).snapshot_hash == approved.snapshot_hash


def test_g2b_at08_governed_projection_is_public_and_fail_closed(
    base: Path, monkeypatch
) -> None:
    _, approved = approve(base)
    product = WorkbenchGovernedProductReadModel(ApprovalGate(base_dir=str(base))).read(
        TRADE_DATE
    )
    assert product is not None
    assert product.revision_id
    assert product.governance_state == "APPROVED"
    assert product.provenance_refs
    assert product.assumptions == ("market-close-input",)
    assert product.limitations == ("no-intraday-recalculation",)
    representation = json.dumps(product.to_dict(), ensure_ascii=False)
    for forbidden in (
        "snapshot.json",
        "snapshots/",
        str(base),
        PRINCIPAL.identity,
        "reviewed_by",
    ):
        assert forbidden not in representation

    class FixedReader:
        def __init__(self, value):
            self.value = value

        def read(self, trade_date: date):
            return self.value

    monkeypatch.setattr(
        api_app,
        "_get_workbench_governed_read_model",
        lambda: FixedReader(product),
    )
    enriched = api_app._enrich_v2_with_workbench_sections({"existing": 1}, TRADE_DATE)
    assert enriched["narrative_review"] == product.judgment_content["narrative"]

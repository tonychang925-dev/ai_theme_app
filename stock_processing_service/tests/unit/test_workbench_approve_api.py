from __future__ import annotations

import asyncio
from datetime import date

import pytest
from fastapi import HTTPException

from stock_processing_service import api_app
from stock_processing_service.application.services.analyst_workbench.draft import AIDraft, DraftStore
from stock_processing_service.application.services.analyst_workbench.session import SessionStore, WorkbenchStatus
from stock_processing_service.application.services.analyst_workbench.snapshot import ReviewSnapshot, SnapshotStore


@pytest.fixture
def isolated_workbench(monkeypatch, tmp_path):
    base_dir = tmp_path / "analyst_workbench"
    session_store = SessionStore(base_dir=str(base_dir))
    draft_store = DraftStore(base_dir=str(base_dir))
    snapshot_store = SnapshotStore(base_dir=str(base_dir))

    monkeypatch.setattr(
        api_app,
        "_get_wb_session_store",
        lambda: (session_store, WorkbenchStatus),
    )
    monkeypatch.setattr(api_app, "_get_wb_draft_store", lambda: draft_store)
    monkeypatch.setattr(
        api_app,
        "_get_wb_snapshot_store",
        lambda: (snapshot_store, ReviewSnapshot),
    )
    return session_store, draft_store, snapshot_store


@pytest.mark.asyncio
async def test_approve_workbench_rejects_unapprovable_status_with_http_error(isolated_workbench):
    with pytest.raises(HTTPException) as exc_info:
        await api_app.approve_workbench("2099-07-16", {"approved_by": "analyst"})

    assert exc_info.value.status_code == 409
    assert "Cannot approve from status NOT_STARTED" in exc_info.value.detail


@pytest.mark.asyncio
async def test_approve_workbench_creates_snapshot_from_in_review_draft(isolated_workbench):
    session_store, draft_store, snapshot_store = isolated_workbench
    td = date(2099, 7, 16)

    session = session_store.get(td)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    draft = AIDraft(trade_date=td, draft_version=1)
    draft_store.save(draft)
    session = session_store.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session_store.transition(session, WorkbenchStatus.IN_REVIEW)

    result = await api_app.approve_workbench("2099-07-16", {"approved_by": "analyst"})

    assert result["status"] == "approved"
    assert result["session_status"] == WorkbenchStatus.APPROVED
    assert result["snapshot_version"] == 1
    assert snapshot_store.load(td) is not None


@pytest.mark.asyncio
async def test_approve_workbench_still_approves_when_capital_enrichment_times_out(
    isolated_workbench,
    monkeypatch,
    tmp_path,
):
    session_store, draft_store, snapshot_store = isolated_workbench
    td = date(2099, 7, 16)
    workbench_dir = tmp_path / "tmp" / "analyst_workbench" / td.isoformat()
    workbench_dir.mkdir(parents=True)
    (workbench_dir / "draft_context.json").write_text(
        '{"trade_date":"2099-07-16","capital_quality":{}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(api_app, "_project_root", lambda: tmp_path)

    async def _timeout(_trade_date, _ctx):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(api_app, "_enrich_draft_context_with_capital", _timeout)

    session = session_store.get(td)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    draft = AIDraft(trade_date=td, draft_version=1)
    draft_store.save(draft)
    session = session_store.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session_store.transition(session, WorkbenchStatus.IN_REVIEW)

    result = await api_app.approve_workbench("2099-07-16", {"approved_by": "analyst"})
    snapshot = snapshot_store.load(td)

    assert result["status"] == "approved"
    assert snapshot is not None
    assert snapshot.capital_quality["approve_enrichment_status"] == "skipped"
    assert snapshot.capital_quality["approve_enrichment_error"] == "TimeoutError"


@pytest.mark.asyncio
async def test_approve_workbench_is_idempotent_when_snapshot_already_exists(isolated_workbench):
    session_store, draft_store, snapshot_store = isolated_workbench
    td = date(2099, 7, 16)

    session = session_store.get(td)
    session = session_store.transition(session, WorkbenchStatus.GENERATING)
    draft = AIDraft(trade_date=td, draft_version=1)
    draft_store.save(draft)
    session = session_store.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = session_store.transition(session, WorkbenchStatus.IN_REVIEW)
    snapshot = ReviewSnapshot.from_draft(draft, snapshot_version=1, approved_by="analyst")
    snapshot_store.save(snapshot)
    session_store.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1, approved_by="analyst")

    result = await api_app.approve_workbench("2099-07-16", {"approved_by": "analyst"})

    assert result["status"] == "approved"
    assert result["session_status"] == WorkbenchStatus.APPROVED
    assert result["snapshot_version"] == 1
    assert result["idempotent"] is True


def test_daily_review_get_path_uses_snapshot_when_builder_lists_are_empty(monkeypatch, tmp_path):
    td = date(2099, 7, 16)
    snapshot_store = SnapshotStore(base_dir=str(tmp_path / "tmp" / "analyst_workbench"))
    snapshot = ReviewSnapshot(
        trade_date=td,
        snapshot_version=1,
        approved=True,
        approved_at="2099-07-16T15:30:00+00:00",
        approved_by="analyst",
        approval_mode="analyst_approved",
        source_mode="analyst_workbench",
        composition_mode="formal",
        capital_active_amount=886.27,
        stock_structure=[
            {
                "stock_code": "600152.SH",
                "stock_name": "维科技术",
                "subject_key": "9035101",
                "theme_name": "钠离子电池",
                "role": "dragon",
                "watch_score": 62.0,
                "watch_priority": 71,
                "watch_status": "removed",
                "cycle_state": "divergence",
                "main_net_inflow": 12000000,
                "money_flow_tier": "LOW",
            }
        ],
    )
    snapshot_store.save(snapshot)
    monkeypatch.setattr(api_app, "_project_root", lambda: tmp_path)

    enriched = api_app._enrich_v2_with_formal_review(
        {
            "strong_stock_reviews": [],
            "watchlist_reviews": [],
            "stock_capital_reviews": [],
            "money_flow_reviews": [],
            "active_capital": {},
        },
        td,
    )

    formal = enriched["formal_review"]
    assert formal["stock_structure"]["stocks"][0]["stock_name"] == "维科技术"
    assert formal["capital_evidence"]["stocks"][0]["stock_code"] == "600152.SH"
    assert formal["next_day_plan"]["watch_stocks"][0]["stock_code"] == "600152.SH"
    assert formal["capital_evidence"]["market"]["active_amount"] == 886.27

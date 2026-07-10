"""Phase 4.5.5 — Analyst review merger tests."""

from datetime import date

from stock_processing_service.application.services.analyst_workbench.draft import AIDraft
from stock_processing_service.application.services.analyst_workbench.review_merger import (
    AnalystReviewMerger,
)
from stock_processing_service.application.services.analyst_workbench.snapshot import (
    ReviewSnapshot,
    SnapshotStore,
)


def test_tc_p455_02_given_analyst_override_when_merge_then_dual_track_final_value():
    draft = AIDraft(
        trade_date=date(2026, 7, 10),
        draft_version=1,
        cognition_cards=[
            {
                "subject_id": "theme:main",
                "subject_name": "主线",
                "stage_judgement": "机器人",
            }
        ],
        emotion_review={"emotion_node": "REBOUND"},
        chart_reviews=[{"chart_type": "market_breadth"}],
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
        ],
        "watch_groups": [{"id": "g1", "name": "承接方向", "subject_ids": ["theme:main"]}],
    }

    merged = AnalystReviewMerger().merge(draft=draft, workspace=workspace)

    assert merged["emotion_review"] == {"emotion_node": "REBOUND"}
    assert merged["chart_reviews"] == [{"chart_type": "market_breadth"}]
    assert merged["attention_state"]["watch_groups"][0]["name"] == "承接方向"

    card = merged["cognition_cards"][0]
    judgement = card["stage_judgement"]
    assert judgement["ai_value"] == "机器人"
    assert judgement["analyst_value"] == "PCB"
    assert judgement["final_value"] == "PCB"
    assert judgement["override"] is True
    assert judgement["reason"] == "资金切换"

    summary = merged["override_summary"]
    assert summary["total"] == 1
    assert summary["field_changes"][0]["final_value"] == "PCB"


def test_tc_p455_02_given_merged_review_when_snapshot_saved_then_hash_and_metadata(tmp_path):
    td = date(2026, 7, 10)
    draft = AIDraft(trade_date=td, draft_version=3)
    merged = {
        "attention_state": {"watch_groups": []},
        "cognition_cards": [{"subject_name": "PCB"}],
        "narrative": {"main": "资金切换"},
        "playbook": {"bias": "观察承接"},
        "emotion_review": {"emotion_node": "REBOUND"},
        "chart_reviews": [{"chart_type": "active_capital"}],
        "override_summary": {"total": 1},
    }

    snapshot = ReviewSnapshot.from_merged(
        trade_date=td,
        draft=draft,
        merged=merged,
        snapshot_version=2,
        approved_by="analyst",
    )
    store = SnapshotStore(base_dir=str(tmp_path / "analyst_workbench"))
    store.save(snapshot)
    loaded = store.load(td)

    assert loaded is not None
    assert loaded.approved is True
    assert loaded.approval_mode == "analyst_approved"
    assert loaded.source_mode == "formal"
    assert loaded.snapshot_hash
    assert loaded.snapshot_hash == loaded.compute_hash()
    assert loaded.based_on_draft_version == 3
    assert loaded.cognition_cards == [{"subject_name": "PCB"}]

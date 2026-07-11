"""Phase 4.5.4 — Acceptance tests for Daily Review Workbench Sections."""

import json
import tempfile
from datetime import date
from pathlib import Path

import pytest

from stock_processing_service.application.services.analyst_workbench.session import (
    SessionStore, WorkbenchStatus,
)
from stock_processing_service.application.services.analyst_workbench.draft import (
    AIDraft, DraftStore,
)
from stock_processing_service.application.services.analyst_workbench.snapshot import (
    ReviewSnapshot, SnapshotStore,
)
from stock_processing_service.application.services.analyst_workbench.chart_review_builder import (
    ChartReviewBuilder,
)
from stock_processing_service.application.services.analyst_workbench.emotion_review_builder import (
    EmotionReviewBuilder,
)
from stock_processing_service.application.services.analyst_workbench.report_composer import (
    WorkbenchReportComposer,
)


@pytest.fixture
def tmp_store():
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "analyst_workbench"
        yield str(base)


@pytest.fixture
def td():
    return date(2026, 7, 9)


# ═══ T01: AIDraft contains new fields ═══

def test_draft_has_emotion_and_chart_fields():
    draft = AIDraft(trade_date=date.today(), draft_version=1)
    assert draft.emotion_review == {}
    assert draft.chart_reviews == []


def test_draft_new_fields_in_json():
    draft = AIDraft(trade_date=date.today(), draft_version=1,
                    emotion_review={"emotion_node": "CLIMAX"},
                    chart_reviews=[{"chart_type": "market_breadth"}])
    d = draft.to_dict()
    assert d["emotion_review"] == {"emotion_node": "CLIMAX"}
    assert d["chart_reviews"] == [{"chart_type": "market_breadth"}]


# ═══ T01: backward compat — old draft without new fields still loads ═══

def test_old_draft_without_new_fields_loads(tmp_store, td):
    old_json = {
        "trade_date": td.isoformat(),
        "draft_version": 1,
        "attention_state": {},
        "cognition_cards": [],
        "narrative": {},
        "playbook": {},
        "source_quality": 0.8,
        "missing_fields": [],
    }
    ds = DraftStore(base_dir=tmp_store)
    p = ds._drafts_dir(td)
    p.mkdir(parents=True, exist_ok=True)
    (p / "draft_v1.json").write_text(json.dumps(old_json))

    loaded = ds.load(td, version=1)
    assert loaded is not None
    assert loaded.emotion_review == {}   # default
    assert loaded.chart_reviews == []    # default


# ═══ T01: snapshot contains new fields ═══

def test_snapshot_has_emotion_and_chart_fields():
    snap = ReviewSnapshot(trade_date=date.today(), snapshot_version=1)
    assert snap.emotion_review == {}
    assert snap.chart_reviews == []


# ═══ T01: backward compat — old snapshot without new fields still loads ═══

def test_old_snapshot_without_new_fields_loads(tmp_store, td):
    old_json = {
        "trade_date": td.isoformat(),
        "snapshot_version": 1,
        "approved": True,
        "approved_at": "",
        "approved_by": "",
        "attention_state": {},
        "cognition_cards": [],
        "narrative": {},
        "playbook": {},
        "override_summary": {},
    }
    sst = SnapshotStore(base_dir=tmp_store)
    p = sst._snapshot_dir(td)
    p.mkdir(parents=True, exist_ok=True)
    (p / "snapshot.json").write_text(json.dumps(old_json))

    loaded = sst.load(td)
    assert loaded is not None
    assert loaded.emotion_review == {}
    assert loaded.chart_reviews == []


# ═══ T05: from_draft copies new fields ═══

def test_from_draft_copies_emotion_and_chart_reviews():
    draft = AIDraft(trade_date=date.today(), draft_version=1,
                    emotion_review={"emotion_node": "ICE_POINT"},
                    chart_reviews=[{"chart_type": "relay_ecology"}])
    snap = ReviewSnapshot.from_draft(draft, snapshot_version=1)
    assert snap.emotion_review == {"emotion_node": "ICE_POINT"}
    assert snap.chart_reviews == [{"chart_type": "relay_ecology"}]
    assert snap.based_on_draft_version == 1


# ═══ T02: ChartReviewBuilder constructs 6 review types ═══

def test_chart_review_builder_with_sample_data():
    charts = [
        {
            "chart_type": "market_breadth",
            "data": {
                "up_count": 2800, "down_count": 1900,
                "limit_up_count": 87, "limit_down_count": 3,
                "composite_score": 3.5,
            },
            "interpretation": "市场宽度改善",
        },
        {
            "chart_type": "emotion_momentum",
            "data": {
                "emotion_momentum_score": 6.2, "label": "情绪活跃",
                "first_board_red_ratio": 0.55, "chain_board_big_loss_ratio": 0.08,
            },
        },
        {
            "chart_type": "active_capital",
            "data": {
                "active_amount_yi": 850, "total_amount_yi": 8200,
                "limit_up_count": 87, "label": "大幅流入",
            },
        },
        {
            "chart_type": "relay_ecology",
            "data": {
                "max_board_height": 5, "promotion_1_to_2": 0.42,
                "promotion_2_to_3": 0.35, "feedback_score": 12,
                "feedback_label": "反馈偏暖",
            },
        },
        {
            "chart_type": "institution_style",
            "data": {
                "directions": [
                    {"name": "半导体", "state": "启动关注"},
                    {"name": "机器人", "state": "主升修复"},
                    {"name": "消费电子", "state": "调整"},
                ],
            },
        },
        {
            "chart_type": "hot_money_style",
            "data": {
                "directions": [
                    {"name": "算力", "state": "退潮"},
                    {"name": "通信", "state": "调整"},
                ],
            },
        },
    ]

    reviews = ChartReviewBuilder().build(charts)
    assert len(reviews) == 6

    breadth = next(r for r in reviews if r["chart_type"] == "market_breadth")
    assert breadth["status"] == "活跃"
    assert breadth["score"] == 3.5
    assert "2800" in breadth["summary"]

    momentum = next(r for r in reviews if r["chart_type"] == "emotion_momentum")
    assert momentum["status"] == "亢奋"

    capital = next(r for r in reviews if r["chart_type"] == "active_capital")
    assert capital["status"] == "回流"

    relay = next(r for r in reviews if r["chart_type"] == "relay_ecology")
    assert relay["status"] == "改善"

    inst = next(r for r in reviews if r["chart_type"] == "institution_style")
    assert inst["status"] == "偏积极"

    hot = next(r for r in reviews if r["chart_type"] == "hot_money_style")
    assert hot["status"] == "偏防御"


# ═══ T03: EmotionReviewBuilder ═══

def test_emotion_review_builder_with_sample_data():
    emo = {
        "emotion_node": "REBOUND",
        "emotion_desc": "市场处于退潮后的修复阶段。",
        "emotion_score": 35,
        "confidence": 0.82,
        "strategy_bias": "可小仓参与核心修复",
        "key_evidence": ["涨停数回升", "连板晋级率改善"],
        "breadth_score": 42, "breadth_label": "改善",
        "momentum_score": 28, "momentum_label": "偏好",
        "relay_score": 35, "relay_label": "改善",
        "capital_score": 18, "capital_label": "中性",
        "style_score": 12, "style_label": "分歧",
    }
    review = EmotionReviewBuilder().build(emo)

    assert review["emotion_node"] == "REBOUND"
    assert review["emotion_label"] == "情绪修复"
    assert review["emotion_score"] == 35
    assert review["risk_level"] == "MEDIUM"
    assert review["confidence"] == 0.82
    assert "修复阶段" in review["summary"]
    assert len(review["key_evidence"]) == 2
    assert review["breadth_score"] == 42


def test_emotion_review_builder_empty_input():
    review = EmotionReviewBuilder().build({})
    assert review["emotion_node"] == ""
    assert review["risk_level"] == "UNKNOWN"
    assert review["source_quality"] == 0


# ═══ T06: WorkbenchReportComposer outputs first-class sections ═══

def test_composer_outputs_first_class_sections(tmp_store, td):
    # Setup approved snapshot with workbench data
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)

    draft = AIDraft(
        trade_date=td, draft_version=1,
        emotion_review={"emotion_node": "CLIMAX", "emotion_score": 75},
        chart_reviews=[{"chart_type": "market_breadth", "status": "活跃"}],
        attention_state={"charts_available": 3},
        cognition_cards=[{"subject_name": "机器人"}],
        narrative={"main_story": "测试叙事"},
        playbook={"strategy_bias": "观望"},
    )
    ds = DraftStore(base_dir=tmp_store)
    ds.save(draft)

    snap = ReviewSnapshot.from_draft(draft, snapshot_version=1, approved_by="analyst")
    sst = SnapshotStore(base_dir=tmp_store)
    sst.save(snap)

    session = ss.transition(session, WorkbenchStatus.APPROVED,
                            snapshot_version=1, approved_by="analyst")

    composer = WorkbenchReportComposer(workbench_base_dir=tmp_store)
    result = composer.compose(td, recap_doc=None)

    assert result.mode == "formal"
    report = result.report

    # First-class sections
    assert report["emotion_review"] == {"emotion_node": "CLIMAX", "emotion_score": 75}
    assert report["market_chart_reviews"] == [{"chart_type": "market_breadth", "status": "活跃"}]
    assert report["attention_review"] == {"charts_available": 3}
    assert report["cognition_reviews"] == [{"subject_name": "机器人"}]
    assert report["narrative_review"] == {"main_story": "测试叙事"}
    assert report["playbook_review"] == {"strategy_bias": "观望"}


# ═══ Regenerate does not affect snapshot report ═══

def test_regenerate_does_not_affect_snapshot_report(tmp_store, td):
    ss = SessionStore(base_dir=tmp_store)
    session = ss.get(td)
    session = ss.transition(session, WorkbenchStatus.GENERATING)
    session = ss.transition(session, WorkbenchStatus.DRAFT_READY, draft_version=1)
    session = ss.transition(session, WorkbenchStatus.IN_REVIEW)

    # v1 draft and snapshot
    draft_v1 = AIDraft(trade_date=td, draft_version=1,
                       emotion_review={"emotion_node": "CLIMAX"})
    ds = DraftStore(base_dir=tmp_store)
    ds.save(draft_v1)
    snap = ReviewSnapshot.from_draft(draft_v1, snapshot_version=1)
    sst = SnapshotStore(base_dir=tmp_store)
    sst.save(snap)
    session = ss.transition(session, WorkbenchStatus.APPROVED, snapshot_version=1)

    # Simulate re-generate: write draft_v2
    draft_v2 = AIDraft(trade_date=td, draft_version=2,
                       emotion_review={"emotion_node": "REBOUND"})
    ds.save(draft_v2)

    # Compose — must use snapshot_v1 data, not draft_v2
    composer = WorkbenchReportComposer(workbench_base_dir=tmp_store)
    result = composer.compose(td)
    assert result.mode == "formal"
    assert result.report["emotion_review"] == {"emotion_node": "CLIMAX"}  # v1, not v2

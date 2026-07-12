"""PR3 preflight — ReviewDocument diff API/model tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stock_processing_service import api_app
from stock_processing_service.application.services.review_document import (
    ReviewDocumentDiffService,
    FieldClass,
)


def test_review_document_diff_emits_identity_override_change() -> None:
    document = {
        "metadata": {"trade_date": "2026-07-09", "final_document_hash": "sha256:abc"},
        "audit": {
            "explicit_overrides": [
                {
                    "entity_key": "robot",
                    "field": "subject_name",
                    "ai_value": "人形机器人",
                    "analyst_value": "PCB",
                    "final_value": "PCB",
                    "reason": "资金切换",
                }
            ]
        },
    }

    diff = ReviewDocumentDiffService().diff(document).to_dict()

    assert diff["summary"]["total_changes"] == 1
    assert diff["summary"]["identity_changes"] == 1
    assert diff["changes"][0] == {
        "path": "themes[robot].name",
        "field_class": FieldClass.IDENTITY.value,
        "before": "人形机器人",
        "after": "PCB",
        "final_value": "PCB",
        "reason": "资金切换",
        "source": "explicit_override",
        "entity_key": "robot",
    }


def test_review_document_diff_empty_when_no_explicit_override() -> None:
    diff = ReviewDocumentDiffService().diff({"audit": {"explicit_overrides": []}}).to_dict()

    assert diff["changes"] == []
    assert diff["summary"]["total_changes"] == 0


@pytest.mark.asyncio
async def test_workbench_review_document_diff_api_returns_change_contract() -> None:
    trade_date = "2099-07-10"
    project_root = Path(api_app.__file__).resolve().parents[1]
    workbench_dir = project_root / "tmp" / "analyst_workbench" / trade_date

    if workbench_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {workbench_dir}")

    try:
        (workbench_dir / "drafts").mkdir(parents=True)
        (workbench_dir / "draft_context.json").write_text(
            json.dumps({
                "trade_date": trade_date,
                "market_state": {"facts": {"limit_up_count": 75}},
                "themes": [{"subject_key": "robot", "theme_name": "人形机器人"}],
                "capital_state": {"top_stocks": [{"theme_name": "PCB", "role_label": "机构"}]},
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        (workbench_dir / "drafts" / "draft_v1.json").write_text(
            json.dumps({
                "trade_date": trade_date,
                "emotion_review": {"phase": "REBOUND", "score": 39},
                "cognition_cards": [
                    {
                        "subject_id": "robot",
                        "subject_name": "人形机器人",
                        "field_overrides": {
                            "subject_name": {
                                "ai_value": "人形机器人",
                                "analyst_value": "PCB",
                                "final_value": "PCB",
                                "reason": "资金切换",
                            }
                        },
                    }
                ],
                "playbook": {"scenario": "REBOUND_ARBITRAGE"},
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        payload = await api_app.get_analyst_workspace_review_document_diff(trade_date)

        assert set(payload) == {"review_document_diff", "metadata"}
        changes = payload["review_document_diff"]["changes"]
        assert len(changes) == 1
        assert changes[0]["field_class"] == "IDENTITY"
        assert changes[0]["before"] == "人形机器人"
        assert changes[0]["after"] == "PCB"
        assert changes[0]["final_value"] == "PCB"
        assert payload["metadata"]["document_hash"].startswith("sha256:")
    finally:
        shutil.rmtree(workbench_dir, ignore_errors=True)

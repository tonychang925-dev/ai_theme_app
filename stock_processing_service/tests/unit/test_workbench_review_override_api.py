"""PR3 — Workbench ReviewDocument override persistence API tests."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stock_processing_service import api_app


@pytest.mark.asyncio
async def test_review_overrides_are_saved_and_applied_to_workspace_document() -> None:
    trade_date = "2099-07-11"
    project_root = Path(api_app.__file__).resolve().parents[1]
    workbench_dir = project_root / "tmp" / "analyst_workbench" / trade_date

    if workbench_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {workbench_dir}")

    try:
        (workbench_dir / "drafts").mkdir(parents=True)
        (workbench_dir / "draft_context.json").write_text(
            json.dumps({
                "trade_date": trade_date,
                "market_state": {
                    "facts": {
                        "limit_up_count": 75,
                        "limit_down_count": 29,
                        "up_count": 3561,
                        "down_count": 1609,
                    }
                },
                "themes": [
                    {"subject_key": "robot", "theme_name": "人形机器人", "role": "MAINLINE", "stage": "分歧"}
                ],
                "capital_state": {
                    "top_stocks": [
                        {"theme_name": "机器人", "role_label": "机构", "stock_name": "测试股份"}
                    ]
                },
                "strong_stocks": [
                    {"stock_code": "000001.SZ", "stock_name": "测试股份", "theme_name": "机器人"}
                ],
            }, ensure_ascii=False),
            encoding="utf-8",
        )
        (workbench_dir / "drafts" / "draft_v1.json").write_text(
            json.dumps({
                "trade_date": trade_date,
                "draft_version": 1,
                "emotion_review": {"phase": "REBOUND", "score": 39},
                "cognition_cards": [],
                "playbook": {"scenario": "REBOUND_ARBITRAGE"},
            }, ensure_ascii=False),
            encoding="utf-8",
        )

        before = await api_app.get_analyst_workspace(trade_date)
        before_hash = before["review_document"]["metadata"]["final_document_hash"]
        assert before["review_document"]["summary"]["primary_theme"]["final_value"] == "人形机器人"

        saved = await api_app.save_analyst_workspace_review_overrides(
            trade_date,
            {
                "overrides": [
                    {
                        "field_path": "themes[robot].name",
                        "field_class": "IDENTITY",
                        "ai_value": "人形机器人",
                        "analyst_value": "PCB",
                        "final_value": "PCB",
                        "reason": "资金切换",
                        "author": "analyst",
                        "timestamp": "2026-07-09T16:00:00+08:00",
                    }
                ]
            },
        )

        assert saved["status"] == "saved"
        assert saved["metadata"]["override_count"] == 1
        assert saved["review_document"]["summary"]["primary_theme"]["final_value"] == "PCB"
        assert saved["metadata"]["document_hash"] != before_hash
        assert saved["review_document_diff"]["changes"][0]["before"] == "人形机器人"
        assert saved["review_document_diff"]["changes"][0]["after"] == "PCB"

        persisted = await api_app.get_analyst_workspace_review_overrides(trade_date)
        assert persisted["overrides"][0]["field_path"] == "themes[robot].name"

        after = await api_app.get_analyst_workspace(trade_date)
        assert after["review_document"]["summary"]["primary_theme"]["final_value"] == "PCB"
        assert after["review_document"]["themes"][0]["name"]["final_value"] == "PCB"
        assert after["diagnostics"]["override_count"] == 1
    finally:
        shutil.rmtree(workbench_dir, ignore_errors=True)

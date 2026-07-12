"""Phase 4.5.7 PR2 guard — Analyst Workspace exposes ReviewDocument only."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from stock_processing_service import api_app


ALLOWED_TOP_LEVEL = {"review_document", "metadata", "diagnostics"}
FORBIDDEN_TOP_LEVEL = {
    "emotion_review",
    "chart_reviews",
    "chart_data",
    "trend_data",
    "formal_review",
    "recap_doc",
    "legacy",
    "themes",
    "watch_groups",
    "cognition_cards",
}


@pytest.mark.asyncio
async def test_workbench_api_returns_review_document_only_contract() -> None:
    trade_date = "2099-07-09"
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
                    {"subject_key": "pcb", "theme_name": "PCB", "role": "MAINLINE", "stage": "承接"}
                ],
                "capital_state": {
                    "top_stocks": [
                        {"theme_name": "PCB", "role_label": "机构", "stock_name": "测试股份"}
                    ]
                },
                "strong_stocks": [
                    {"stock_code": "000001.SZ", "stock_name": "测试股份", "theme_name": "PCB"}
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

        payload = await api_app.get_analyst_workspace(trade_date)

        assert set(payload) == ALLOWED_TOP_LEVEL
        assert not (set(payload) & FORBIDDEN_TOP_LEVEL)
        assert payload["review_document"]["metadata"]["trade_date"] == trade_date
        assert payload["review_document"]["market"]["limit_up_count"] == 75
        assert payload["review_document"]["themes"][0]["name"]["final_value"] == "PCB"
    finally:
        shutil.rmtree(workbench_dir, ignore_errors=True)

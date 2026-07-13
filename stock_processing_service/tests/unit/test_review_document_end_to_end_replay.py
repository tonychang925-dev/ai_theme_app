"""End-to-end ReviewDocument replay pipeline contract.

PR4.2.12.3: one generated ReviewDocument must be persisted as an artifact and
then replayed by the golden guard without reading legacy/static artifacts.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from stock_processing_service import api_app


PROJECT_ROOT = Path(api_app.__file__).resolve().parents[1]
TRADE_DATE = "2099-07-13"
BASELINE_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "tests"
    / "fixtures"
    / "review_document"
    / "golden"
    / "2026-07-09_ui_baseline.yaml"
)


def _workbench_dir() -> Path:
    return PROJECT_ROOT / "tmp" / "analyst_workbench" / TRADE_DATE


def _artifact_path() -> Path:
    return _workbench_dir() / "review_document.json"


def _write_golden_like_input(workbench_dir: Path) -> None:
    (workbench_dir / "drafts").mkdir(parents=True)
    (workbench_dir / "draft_context.json").write_text(
        json.dumps({
            "trade_date": TRADE_DATE,
            "market_state": {
                "facts": {
                    "limit_up_count": 75,
                    "limit_down_count": 29,
                    "up_count": 2357,
                    "down_count": 2642,
                    "active_capital_yi": 2707,
                }
            },
            "themes": [
                {"subject_key": "9055378", "role": "MAINLINE", "stage": "承接"},
                {"subject_key": "9018144", "theme_name": "PCB印制电路板", "role": "MAINLINE", "stage": "启动"},
                {"subject_key": "9014001", "role": "SECONDARY", "stage": "分歧"},
            ],
            "capital_state": {
                "active_amount": 2707,
                "institution": [{"theme_name": "存储芯片", "role_label": "机构"}],
                "hot_money": [{"theme_name": "人形机器人", "role_label": "游资"}],
            },
            "strong_stocks": [
                {
                    "stock_code": "603137.SH",
                    "stock_name": "603137.SH",
                    "themes": [{"name": "存储芯片"}],
                    "board_height": 8,
                }
            ],
            "plan_state": {
                "scenario": "混沌观望",
                "allowed_actions": ["观察", "轻仓"],
                "forbidden_actions": ["重仓", "追高"],
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (workbench_dir / "drafts" / "draft_v1.json").write_text(
        json.dumps({
            "trade_date": TRADE_DATE,
            "draft_version": 1,
            "emotion_review": {"phase": "REBOUND", "score": 39, "risk_level": "中"},
            "cognition_cards": [
                {"subject_id": "9055378", "subject_name": "存储芯片"},
                {"subject_id": "9018144", "subject_name": "PCB印制电路板"},
                {"subject_id": "9014001", "subject_name": "人形机器人"},
            ],
            "playbook": {
                "scenario": "混沌观望",
                "allowed_actions": ["观察", "轻仓"],
                "forbidden_actions": ["重仓", "追高"],
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_generate_persist_replay_pipeline_exposes_stock_identity_gap() -> None:
    workbench_dir = _workbench_dir()
    if workbench_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {workbench_dir}")

    try:
        _write_golden_like_input(workbench_dir)

        payload = await api_app.get_analyst_workspace(TRADE_DATE)
        artifact_path = _artifact_path()
        assert artifact_path.exists()

        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert artifact == payload["review_document"]
        assert artifact["metadata"]["final_document_hash"].startswith("sha256:")

        result = subprocess.run(
            [
                str(PROJECT_ROOT / ".venv" / "bin" / "python"),
                str(PROJECT_ROOT / "scripts" / "verify_review_document.py"),
                "--date",
                "2026-07-09",
                "--baseline",
                str(BASELINE_PATH),
                "--document",
                str(artifact_path),
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 1
        assert "ReviewDocument Replay" in result.stdout
        assert "Artifact:\n✓ found" in result.stdout
        assert "Hash:\n✓ valid sha256:" in result.stdout
        assert "Schema:\n✓ review_document_v1" in result.stdout
        assert "Coverage:" in result.stdout
        assert "market  PASS" in result.stdout
        assert "emotion PASS" in result.stdout
        assert "capital PASS" in result.stdout
        assert "themes  PASS" in result.stdout
        assert "stocks  FAIL required_names: stocks[].name missing" in result.stdout
        assert "plan    PASS" in result.stdout
        assert "READY=False" in result.stdout
        assert "Blocking:\n- stock.identity_missing" in result.stdout
    finally:
        shutil.rmtree(workbench_dir, ignore_errors=True)

"""ReviewDocument artifact persistence contract.

PR4.2.12.1: the assembled ReviewDocument must become a replayable artifact.
The artifact contains only the final ReviewDocument display contract.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from stock_processing_service import api_app


PROJECT_ROOT = Path(api_app.__file__).resolve().parents[1]
TRADE_DATE = "2099-07-12"


def _workbench_dir() -> Path:
    return PROJECT_ROOT / "tmp" / "analyst_workbench" / TRADE_DATE


def _artifact_path() -> Path:
    return _workbench_dir() / "review_document.json"


def _setup_replayable_workbench(workbench_dir: Path) -> None:
    (workbench_dir / "drafts").mkdir(parents=True)
    (workbench_dir / "draft_context.json").write_text(
        json.dumps({
            "trade_date": TRADE_DATE,
            "market_state": {
                "facts": {
                    "limit_up_count": 75,
                    "limit_down_count": 29,
                    "up_count": 3561,
                    "down_count": 1609,
                    "active_capital_yi": 5058.28,
                }
            },
            "themes": [
                {"subject_key": "storage", "theme_name": "存储芯片", "role": "MAINLINE", "stage": "承接"},
                {"subject_key": "robot", "theme_name": "人形机器人", "role": "SECONDARY", "stage": "分歧"},
            ],
            "capital_state": {
                "institution": [{"theme_name": "存储芯片", "role_label": "机构"}],
                "hot_money": [{"theme_name": "人形机器人", "role_label": "游资"}],
            },
            "strong_stocks": [
                {
                    "stock_code": "002747.SZ",
                    "stock_name": "埃斯顿",
                    "themes": [{"name": "人形机器人"}],
                    "board_height": 2,
                }
            ],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    (workbench_dir / "drafts" / "draft_v1.json").write_text(
        json.dumps({
            "trade_date": TRADE_DATE,
            "draft_version": 1,
            "emotion_review": {"phase": "CHAOS", "score": 39, "risk_level": "中"},
            "cognition_cards": [],
            "playbook": {
                "scenario": "混沌观望",
                "allowed_actions": ["观察", "轻仓"],
                "forbidden_actions": ["重仓", "追高"],
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_workspace_persists_replayable_review_document_artifact() -> None:
    workbench_dir = _workbench_dir()
    if workbench_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {workbench_dir}")

    try:
        _setup_replayable_workbench(workbench_dir)

        payload = await api_app.get_analyst_workspace(TRADE_DATE)
        artifact_path = _artifact_path()

        assert artifact_path.exists()
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        assert artifact == payload["review_document"]
        assert artifact["metadata"]["final_document_hash"].startswith("sha256:")

        keys = _collect_keys(artifact)
        for forbidden in ("snapshot", "derived_context", "attention_state", "review_document_context"):
            assert forbidden not in keys
    finally:
        shutil.rmtree(workbench_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_review_document_artifact_can_be_replayed_by_golden_guard() -> None:
    workbench_dir = _workbench_dir()
    if workbench_dir.exists():
        raise AssertionError(f"test workbench dir already exists: {workbench_dir}")

    try:
        _setup_replayable_workbench(workbench_dir)
        await api_app.get_analyst_workspace(TRADE_DATE)

        result = subprocess.run(
            [
                str(PROJECT_ROOT / ".venv" / "bin" / "python"),
                str(PROJECT_ROOT / "scripts" / "verify_review_document.py"),
                "--date",
                "2026-07-09",
                "--baseline",
                str(PROJECT_ROOT / "stock_processing_service" / "tests" / "fixtures" / "review_document" / "golden" / "2026-07-09_ui_baseline.yaml"),
                "--document",
                str(_artifact_path()),
            ],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 1
        assert "market  PASS" in result.stdout
        assert "emotion PASS" in result.stdout
        assert "themes  PASS" in result.stdout
        assert "stocks  FAIL" in result.stdout
        assert "plan    PASS" in result.stdout
        assert "READY=False" in result.stdout
    finally:
        shutil.rmtree(workbench_dir, ignore_errors=True)


def _collect_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys.update(_collect_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_keys(item))
    return keys

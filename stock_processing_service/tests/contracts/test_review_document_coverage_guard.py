"""ReviewDocument field coverage and golden UI replay guards."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[3]
MATRIX_PATH = PROJECT_ROOT / "docs" / "architecture" / "ReviewDocument_Field_Coverage_Matrix.yaml"
BASELINE_PATH = (
    PROJECT_ROOT
    / "stock_processing_service"
    / "tests"
    / "fixtures"
    / "review_document"
    / "golden"
    / "2026-07-09_ui_baseline.yaml"
)
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "verify_review_document.py"


def _load_yaml(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def test_field_coverage_matrix_is_machine_checkable() -> None:
    matrix = _load_yaml(MATRIX_PATH)

    assert matrix["version"] == "review_document_field_coverage_v1"
    fields = matrix["fields"]
    assert isinstance(fields, dict)

    required_fields = {
        "market.limit_up_count",
        "market.up_count",
        "market.down_count",
        "emotion.phase",
        "emotion.score",
        "evidence.trend_series",
        "capital.active_amount",
        "capital.institution",
        "capital.hot_money",
        "themes.name",
        "stocks.name",
        "stocks.themes.name",
        "limit_up.categories",
        "plan.scenario",
        "risk.risk_level",
    }
    assert required_fields <= set(fields)

    for field_name, spec in fields.items():
        assert spec["ui"], field_name
        assert spec["review_document"]["path"], field_name
        assert spec["context"]["path"], field_name
        assert spec["snapshot"]["source"], field_name
        assert spec["field_class"] in {"FACT", "ASSESSMENT", "IDENTITY", "PLAN", "EVIDENCE"}
        assert spec["transform"], field_name
        assert spec["quality"] in {"required", "optional"}
        assert isinstance(spec.get("forbidden", []), list)


def test_golden_ui_baseline_is_semantic_and_compact() -> None:
    baseline = _load_yaml(BASELINE_PATH)

    assert baseline["version"] == "review_document_golden_ui_v1"
    assert baseline["trade_date"] == "2026-07-09"
    raw = BASELINE_PATH.read_text(encoding="utf-8")
    assert len(raw) < 2500
    assert "review_document:" not in raw
    assert "snapshot:" not in raw


def test_golden_replay_reports_missing_fields_without_repairing(tmp_path: Path) -> None:
    incomplete_document = {
        "market": {
            "limit_up_count": 75,
            "up_count": 3561,
            "down_count": 1609,
        },
        "emotion": {
            "phase": "CHAOS",
            "score": 39,
        },
        "capital": {
            "active_amount": 5058.28,
            "institution": [],
            "hot_money": [],
        },
        "themes": [
            {"theme_key": "9055378", "name": {"final_value": "9055378"}},
        ],
        "stocks": [
            {"stock_code": "002747.SZ", "stock_name": "埃斯顿", "theme_name": "__independent__"},
        ],
        "plan": {},
    }
    doc_path = tmp_path / "review_document.json"
    doc_path.write_text(json.dumps(incomplete_document, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [
            str(PROJECT_ROOT / ".venv" / "bin" / "python"),
            str(SCRIPT_PATH),
            "--date",
            "2026-07-09",
            "--baseline",
            str(BASELINE_PATH),
            "--document",
            str(doc_path),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "market  PASS" in result.stdout
    assert "emotion PASS" in result.stdout
    assert "themes  FAIL" in result.stdout
    assert "stocks  FAIL" in result.stdout
    assert "plan    FAIL" in result.stdout
    assert "READY=False" in result.stdout

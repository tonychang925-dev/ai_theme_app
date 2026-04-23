from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from stock_processing_service.tests.replay._replay_runner import run_real_replay


def test_replay_runner_contract_with_temp_inputs(
    tmp_path: Path, monkeypatch
) -> None:
    old_rows = [
        {
            "trade_date": "2026-04-07",
            "stock_id": "002361.SZ",
            "subject_key": "military_new_material",
            "candidate_score": 80.0,
            "decision": "confirmed",
        }
    ]
    new_rows = [
        {
            "trade_date": "2026-04-07",
            "stock_id": "002361.SZ",
            "subject_key": "military_new_material",
            "candidate_score": 78.0,
            "decision": "watch",
        }
    ]

    old_path = tmp_path / "old.json"
    new_path = tmp_path / "new.json"
    old_path.write_text(json.dumps(old_rows, ensure_ascii=False), encoding="utf-8")
    new_path.write_text(json.dumps(new_rows, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setenv("REPLAY_SHENJIAN_OLD_JSON", str(old_path))
    monkeypatch.setenv("REPLAY_SHENJIAN_NEW_JSON", str(new_path))

    result = run_real_replay("SHENJIAN", date(2026, 4, 7))
    assert result.summary["trade_date"] == "2026-04-07"
    assert int(result.summary["old_count"]) == 1
    assert int(result.summary["new_count"]) == 1
    assert int(result.summary["changed"]) == 1

    summary_path = result.output_dir / "summary"
    diff_path = result.output_dir / "diff_samples.jsonl"
    explanation_path = result.output_dir / "diff_explanation.md"
    assert summary_path.exists()
    assert diff_path.exists()
    assert explanation_path.exists()

    diff_lines = [json.loads(line) for line in diff_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert diff_lines
    assert all("reason_category" in row for row in diff_lines)


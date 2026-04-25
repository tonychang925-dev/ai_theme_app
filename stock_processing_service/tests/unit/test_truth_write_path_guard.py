from __future__ import annotations

from pathlib import Path


FORBIDDEN_TOKEN = "upsert_stock_daily_snapshot_rows("


def test_no_truth_write_path_in_stock_processing_production_code() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []

    for py in root.rglob("*.py"):
        rel = py.relative_to(root)
        rel_str = str(rel)
        if rel_str.startswith("tests/"):
            continue
        text = py.read_text(encoding="utf-8")
        if FORBIDDEN_TOKEN in text:
            offenders.append(rel_str)

    assert not offenders, (
        "truth-table write path leaked into stock_processing_service production code: "
        + ", ".join(sorted(offenders))
    )


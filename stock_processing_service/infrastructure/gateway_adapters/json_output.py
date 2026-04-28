from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any


def is_json_only_mode() -> bool:
    mode = str(os.getenv("SPS_OUTPUT_MODE", "json_only")).strip().lower()
    return mode == "json_only"


def _date_key_from_payload(payload: dict[str, Any]) -> str:
    value = payload.get("trade_date")
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return "unknown_date"
    return str(value)


def _base_dir() -> Path:
    raw = os.getenv("SPS_OUTPUT_DIR", "tmp/new_chain_runs")
    return Path(raw).resolve()


def dump_json_only(
    *,
    object_name: str,
    payload: dict[str, Any],
) -> int:
    trade_date = _date_key_from_payload(payload)
    root = _base_dir() / trade_date
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{object_name}.jsonl"
    record = {
        "written_at": datetime.now().isoformat(timespec="seconds"),
        "object_name": object_name,
        "payload": payload,
    }
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, default=str))
        f.write("\n")
    return 1


def dump_json_only_rows(
    *,
    object_name: str,
    rows: list[dict[str, Any]],
) -> int:
    if not rows:
        return 0
    count = 0
    for row in rows:
        count += dump_json_only(object_name=object_name, payload=row)
    return count

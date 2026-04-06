from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_validation_dataset(dataset_path: str) -> list[dict[str, Any]]:
    path = Path(dataset_path)
    if not path.exists():
        raise FileNotFoundError(f"dataset not found: {path}")

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        events = data.get("events", [])
    elif isinstance(data, list):
        events = data
    else:
        raise ValueError("validation dataset must be a JSON object or list")

    if not isinstance(events, list):
        raise ValueError("validation dataset events must be a list")
    return [event for event in events if isinstance(event, dict)]


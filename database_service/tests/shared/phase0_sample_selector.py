from __future__ import annotations

from typing import Any


def select_phase0_samples(events: list[dict[str, Any]], sample_size: int) -> list[dict[str, Any]]:
    requested = max(1, int(sample_size))
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []

    for event in events:
        key = str(
            event.get("event_id")
            or event.get("id")
            or f"title::{event.get('title', '')}"
        )
        if key in seen:
            continue
        seen.add(key)
        selected.append(event)
        if len(selected) >= requested:
            break

    return selected


"""Experiment filtering logic for W2S backtest."""

from __future__ import annotations

from typing import Any

from .w2s_models import EXPERIMENT_GROUPS, VISIBLE_EXPERIMENTS


def matches_experiment(row: dict[str, Any], experiment_id: str) -> bool:
    """Check if a snapshot row matches experiment conditions."""
    group = EXPERIMENT_GROUPS.get(experiment_id)
    if group is None:
        return False

    conditions = group.get("conditions") or {}
    for key, expected in conditions.items():
        actual = row.get(key)

        if key == "pool_entry_type":
            if actual not in expected:
                return False
        elif key == "mainline_strength_score_min":
            actual_val = float(actual or 0)
            if actual_val < expected:
                return False
        elif key == "fade_confirmed":
            if bool(actual) != expected:
                return False
        elif key == "leader_role_proxy":
            if actual not in expected:
                return False
        elif key == "confirm_level":
            if actual not in expected:
                return False

    return True


def filter_for_experiment(
    rows: list[dict[str, Any]],
    experiment_id: str,
) -> list[dict[str, Any]]:
    """Filter rows for a given experiment."""
    return [row for row in rows if matches_experiment(row, experiment_id)]


def get_visible_experiments() -> list[str]:
    return list(VISIBLE_EXPERIMENTS)


def get_all_experiments() -> list[str]:
    return list(EXPERIMENT_GROUPS.keys())

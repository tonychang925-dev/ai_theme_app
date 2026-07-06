"""CycleFSM — versioned FSM loaded from YAML policy.

Add new cycle nodes without code changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class CycleFSM:
    """Versioned Finite State Machine for Cycle Node transitions.

    Loaded from YAML. validates every transition against allowed states.
    """

    def __init__(self, policy_path: str | Path) -> None:
        self.policy_path = Path(policy_path)
        with open(self.policy_path) as fh:
            self.config: dict[str, Any] = yaml.safe_load(fh)

        self.version: str = self.config["version"]
        self.valid_from: str = self.config["valid_from"]
        self.states: dict[str, dict[str, Any]] = self.config["states"]

    @property
    def state_names(self) -> tuple[str, ...]:
        return tuple(self.states.keys())

    def is_valid_state(self, name: str) -> bool:
        return name in self.states

    def is_valid_transition(self, from_node: str, to_node: str) -> bool:
        if from_node not in self.states:
            return False
        allowed = self.states[from_node].get("allowed_transitions", [])
        return to_node in allowed

    def allowed_next(self, node: str) -> tuple[str, ...]:
        if node not in self.states:
            return ()
        return tuple(self.states[node].get("allowed_transitions", []))

    def label(self, node: str) -> str:
        return self.states.get(node, {}).get("label", node)

    def description(self, node: str) -> str:
        return self.states.get(node, {}).get("description", "")

    def valid_transitions_for(self, node: str) -> tuple[str, ...]:
        return self.allowed_next(node)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "valid_from": self.valid_from,
            "state_count": len(self.states),
        }

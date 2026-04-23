from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StateTransition:
    stock_id: str
    from_state: str
    to_state: str
    transition_type: str


class StateTransitionService:
    def build_transitions(self, current_states: dict[str, str], prior_states: dict[str, str]) -> list[StateTransition]:
        transitions: list[StateTransition] = []
        for stock_id, to_state in current_states.items():
            from_state = prior_states.get(stock_id, "unknown")
            if from_state == to_state:
                transition_type = "unchanged"
            elif from_state == "unknown":
                transition_type = "new_entry"
            elif to_state in {"fade_watch", "fade_confirmed"}:
                transition_type = "weakened"
            elif to_state in {"start", "fermentation", "acceleration", "repair"}:
                transition_type = "strengthened"
            else:
                transition_type = "state_shift"
            transitions.append(
                StateTransition(
                    stock_id=stock_id,
                    from_state=from_state,
                    to_state=to_state,
                    transition_type=transition_type,
                )
            )
        return transitions

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class StateTransition:
    stock_id: str
    from_state: str
    to_state: str
    transition_type: str
    confidence: Decimal
    trigger_flags: list[str]


class StateTransitionService:
    _RANK = {
        "fade_confirmed": 0,
        "fade_watch": 1,
        "start": 2,
        "fermentation": 3,
        "divergence": 4,
        "repair": 5,
        "acceleration": 6,
    }

    def _rank(self, state: str) -> int:
        return self._RANK.get(state, -1)

    def _transition_type(self, from_state: str, to_state: str) -> str:
        if to_state == "fade_confirmed":
            return "fade"
        if from_state == to_state:
            return "flat"
        from_rank = self._rank(from_state)
        to_rank = self._rank(to_state)
        if from_rank == -1 or to_rank == -1:
            return "flat"
        if to_rank > from_rank:
            return "upgrade"
        if to_rank < from_rank:
            return "downgrade"
        return "flat"

    def _trigger_flags(self, from_state: str, to_state: str, transition_type: str) -> list[str]:
        flags: list[str] = [f"from={from_state}", f"to={to_state}"]
        if transition_type == "fade":
            flags.append("enter_fade_confirmed")
        if transition_type == "upgrade":
            flags.append("state_rank_up")
        if transition_type == "downgrade":
            flags.append("state_rank_down")
        if from_state in {"fade_watch", "fade_confirmed"} and to_state in {"repair", "acceleration"}:
            flags.append("recovery_signal")
        if from_state == "unknown":
            flags.append("prior_state_missing")
        return flags

    def _confidence(self, from_state: str, to_state: str, transition_type: str) -> Decimal:
        if transition_type == "fade":
            return Decimal("0.95")
        if from_state == "unknown":
            return Decimal("0.65")
        gap = abs(self._rank(to_state) - self._rank(from_state))
        if transition_type == "flat":
            return Decimal("0.75")
        if gap >= 3:
            return Decimal("0.90")
        if gap == 2:
            return Decimal("0.85")
        return Decimal("0.80")

    def build_transitions(self, current_states: dict[str, str], prior_states: dict[str, str]) -> list[StateTransition]:
        transitions: list[StateTransition] = []
        for stock_id, to_state in current_states.items():
            from_state = prior_states.get(stock_id, "unknown")
            transition_type = self._transition_type(from_state, to_state)
            trigger_flags = self._trigger_flags(from_state, to_state, transition_type)
            confidence = self._confidence(from_state, to_state, transition_type)
            transitions.append(
                StateTransition(
                    stock_id=stock_id,
                    from_state=from_state,
                    to_state=to_state,
                    transition_type=transition_type,
                    confidence=confidence,
                    trigger_flags=trigger_flags,
                )
            )
        return transitions

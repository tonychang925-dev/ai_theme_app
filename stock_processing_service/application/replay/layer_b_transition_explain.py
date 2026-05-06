from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True)
class LayerBTransitionExplain:
    subject_key: str
    trade_date: str
    previous_cycle_state: str | None
    final_cycle_state: str | None
    final_mainline_alive: bool | None
    scores: dict[str, Any]
    state_decision_trace: list[dict[str, Any]]
    alive_decision_reason: str
    evidence_drivers: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject_key": self.subject_key,
            "trade_date": self.trade_date,
            "previous_cycle_state": self.previous_cycle_state,
            "final_cycle_state": self.final_cycle_state,
            "final_mainline_alive": self.final_mainline_alive,
            "scores": self.scores,
            "state_decision_trace": self.state_decision_trace,
            "alive_decision_reason": self.alive_decision_reason,
            "evidence_drivers": self.evidence_drivers,
        }


class LayerBTransitionExplainBuilder:
    THRESH_MAINLINE_ALIVE = Decimal("60")
    THRESH_MAINLINE_LEADER = Decimal("40")
    THRESH_MAINLINE_EVENT_CONTINUITY = Decimal("40")
    THRESH_FADE_WATCH = Decimal("50")
    THRESH_FADE_CONFIRMED = Decimal("60")
    THRESH_DIVERGENCE = Decimal("60")
    THRESH_REPAIR = Decimal("65")
    THRESH_ACCELERATION = Decimal("75")
    THRESH_FERMENTATION = Decimal("60")

    def build(
        self,
        *,
        trade_date: str,
        subject_key: str,
        evidence: dict[str, Any],
        cycle: dict[str, Any],
    ) -> LayerBTransitionExplain:
        previous_state = self._str(evidence.get("previous_cycle_state") or cycle.get("previous_cycle_state")) or None
        final_state = self._str(cycle.get("final_cycle_state")) or None
        alive_raw = cycle.get("final_mainline_alive")
        alive = bool(alive_raw) if alive_raw is not None else None
        scores = {
            "mainline_strength_score": cycle.get("mainline_strength_score"),
            "fade_watch_score": cycle.get("fade_watch_score"),
            "fade_confirmed_score": cycle.get("fade_confirmed_score"),
            "divergence_score": cycle.get("divergence_score"),
            "repair_score": cycle.get("repair_score"),
        }
        evidence_count = self._int(cycle.get("fade_confirmed_evidence_count") or cycle.get("evidence_count"))
        trace = [
            self._rule(
                "fade_confirmed",
                self._dec(cycle.get("fade_confirmed_score")) >= self.THRESH_FADE_CONFIRMED and evidence_count >= 3,
                f"fade_confirmed_score={cycle.get('fade_confirmed_score')} threshold=60 evidence_count={evidence_count} threshold=3",
            ),
            self._rule(
                "repair",
                self._dec(cycle.get("repair_score")) >= self.THRESH_REPAIR
                and (previous_state in {"divergence", "fade_watch"}),
                f"repair_score={cycle.get('repair_score')} threshold=65 previous_cycle_state={previous_state}",
            ),
            self._rule(
                "divergence",
                self._dec(cycle.get("divergence_score")) >= self.THRESH_DIVERGENCE,
                f"divergence_score={cycle.get('divergence_score')} threshold=60",
            ),
            self._rule(
                "fade_watch",
                self._dec(cycle.get("fade_watch_score")) >= self.THRESH_FADE_WATCH,
                f"fade_watch_score={cycle.get('fade_watch_score')} threshold=50",
            ),
            self._rule(
                "acceleration",
                self._dec(cycle.get("mainline_strength_score")) >= self.THRESH_ACCELERATION,
                f"mainline_strength_score={cycle.get('mainline_strength_score')} threshold=75",
            ),
            self._rule(
                "fermentation",
                self._dec(cycle.get("mainline_strength_score")) >= self.THRESH_FERMENTATION,
                f"mainline_strength_score={cycle.get('mainline_strength_score')} threshold=60",
            ),
        ]
        if final_state:
            trace.append(
                {
                    "rule": "final_cycle_state",
                    "passed": True,
                    "reason": f"selected_state={final_state}; decision_path={cycle.get('decision_path') or ''}",
                }
            )
        return LayerBTransitionExplain(
            subject_key=subject_key,
            trade_date=trade_date,
            previous_cycle_state=previous_state,
            final_cycle_state=final_state,
            final_mainline_alive=alive,
            scores=scores,
            state_decision_trace=trace,
            alive_decision_reason=self._alive_reason(evidence=evidence, cycle=cycle, final_state=final_state, alive=alive),
            evidence_drivers={
                "leader_alive_score": evidence.get("leader_alive_score"),
                "leader_breakdown_flag": evidence.get("leader_breakdown_flag"),
                "relay_strength_score": evidence.get("relay_strength_score"),
                "red_ratio": evidence.get("red_ratio"),
                "big_drop_ratio": evidence.get("big_drop_ratio"),
                "theme_support_score": evidence.get("theme_support_score"),
                "break_start_pivot": evidence.get("break_start_pivot"),
            },
        )

    def _alive_reason(
        self,
        *,
        evidence: dict[str, Any],
        cycle: dict[str, Any],
        final_state: str | None,
        alive: bool | None,
    ) -> str:
        if alive is True:
            return "alive_conditions_passed"
        if final_state == "fade_confirmed":
            return "state=fade_confirmed treated as not alive"
        if alive is False:
            return f"persisted final_mainline_alive=false; old-chain-compatible policy only hard-kills fade_confirmed, final_cycle_state={final_state}"
        checks = [
            ("mainline_strength_score", self._dec(cycle.get("mainline_strength_score")), self.THRESH_MAINLINE_ALIVE),
            ("leader_alive_score", self._dec(evidence.get("leader_alive_score")), self.THRESH_MAINLINE_LEADER),
        ]
        failed = [f"{name}={value} below threshold={threshold}" for name, value, threshold in checks if value < threshold]
        continuity_ok = (
            self._int(evidence.get("strong_event_count_7d")) > 0
            or self._dec(evidence.get("event_continuity_score")) >= self.THRESH_MAINLINE_EVENT_CONTINUITY
        )
        if not continuity_ok:
            failed.append("strong_event_count_7d=0 and event_continuity_score below threshold=40")
        if failed:
            return "; ".join(failed)
        return "alive flag missing"

    @staticmethod
    def _rule(rule: str, passed: bool, reason: str) -> dict[str, Any]:
        return {"rule": rule, "passed": bool(passed), "reason": reason}

    @staticmethod
    def _dec(value: Any) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _str(value: Any) -> str:
        return str(value or "").strip()

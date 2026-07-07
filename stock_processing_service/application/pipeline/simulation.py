"""Phase C — HistoricalSimulation + SimulationTimeline.

Not Replay (playback of existing results).
Simulation: step-by-step, each day only sees data available up to that day.

Flow:
  Day D: state_D loaded
    → diff(state_{D-1}, state_D)
    → Compiler.compile(state_D, state_{D-1}, diff)
    → Store.append(hypotheses)
    → Verify D-1's hypotheses against D's reality
    → Advance
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from stock_processing_service.contracts.market_cognition_phase_b import (
    CompiledNodeTransitionHypothesis,
)
from stock_processing_service.contracts.market_cognition_v1_5 import DailyMarketState


# ──────────────────────────────────────────────
#  SimulationVerdict
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SimulationVerdict:
    """Lightweight verdict: did the hypothesis pan out?"""

    hypothesis_id: str
    subject_id: str
    generated_on: date
    deadline: date
    verified_on: date

    expected_transition: str
    actual_node: str
    actual_transition: str  # e.g. "CLIMAX → FIRST_DIVERGENCE" or "CLIMAX → CLIMAX"

    label: str  # CONFIRMED | FALSIFIED | PENDING

    def is_confirmed(self) -> bool:
        return self.label == "CONFIRMED"

    def is_falsified(self) -> bool:
        return self.label == "FALSIFIED"

    def is_pending(self) -> bool:
        return self.label == "PENDING"


# ──────────────────────────────────────────────
#  SimulationDay
# ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SimulationDay:
    """One day in the simulation timeline."""

    trade_date: date
    state: DailyMarketState | None = None
    hypotheses: tuple[CompiledNodeTransitionHypothesis, ...] = ()
    verdicts: tuple[SimulationVerdict, ...] = ()


# ──────────────────────────────────────────────
#  SimulationTimeline
# ──────────────────────────────────────────────


@dataclass
class SimulationTimeline:
    """Complete simulation timeline — unified container."""

    days: list[SimulationDay] = field(default_factory=list)
    _hash: str | None = field(default=None, repr=False)

    @property
    def states(self) -> tuple[DailyMarketState, ...]:
        return tuple(day.state for day in self.days if day.state is not None)

    @property
    def hypotheses(self) -> tuple[CompiledNodeTransitionHypothesis, ...]:
        result: list[CompiledNodeTransitionHypothesis] = []
        for day in self.days:
            result.extend(day.hypotheses)
        return tuple(result)

    @property
    def verdicts(self) -> tuple[SimulationVerdict, ...]:
        result: list[SimulationVerdict] = []
        for day in self.days:
            result.extend(day.verdicts)
        return tuple(result)

    def append(self, day: SimulationDay) -> None:
        self.days.append(day)
        self._hash = None  # invalidate cache

    def compute_hash(self) -> str:
        """Deterministic hash of the entire timeline.

        Covers: all trade_dates, state_ids, hypothesis_ids, verdict labels.
        Same simulation inputs → same hash.
        """
        payload: dict[str, Any] = {"days": []}
        for day in self.days:
            day_entry: dict[str, Any] = {
                "trade_date": day.trade_date.isoformat(),
            }
            if day.state is not None:
                day_entry["state_id"] = day.state.state_id
            day_entry["hypotheses"] = [
                {
                    "hypothesis_id": h.hypothesis_id,
                    "current_node": h.current_node,
                    "expected_transition": h.expected_transition,
                }
                for h in day.hypotheses
            ]
            day_entry["verdicts"] = [
                {
                    "hypothesis_id": v.hypothesis_id,
                    "label": v.label,
                    "expected_transition": v.expected_transition,
                    "actual_node": v.actual_node,
                }
                for v in day.verdicts
            ]
            payload["days"].append(day_entry)

        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


# ──────────────────────────────────────────────
#  HistoricalSimulation
# ──────────────────────────────────────────────


class HistoricalSimulation:
    """Step-by-step historical simulation. No future data leakage.

    Each day:
      1. Load state (pre-built or from world)
      2. If prev_state exists: diff → compile → store.append
      3. Verify previous day's hypotheses (available_at guard)
      4. Advance

    Dependencies are injected — simulation does NOT own them.
    """

    def __init__(
        self,
        world: Any,  # MarketWorldModel
        compiler: Any,  # WorldStateTransitionCompiler
        store: Any,  # NodeTransitionHypothesisStore
    ) -> None:
        self.world = world
        self.compiler = compiler
        self.store = store

    def simulate(
        self,
        start_date: date,
        end_date: date,
    ) -> SimulationTimeline:
        """Run full simulation from start_date to end_date.

        States are loaded from world.history (must be pre-populated).
        Each day only has access to data available up to and including
        that day — no future peek.
        """
        timeline = SimulationTimeline()

        # Build state lookup from world.history
        state_by_date: dict[date, DailyMarketState] = {}
        for s in self.world.history:
            state_by_date[s.trade_date] = s

        prev_state: DailyMarketState | None = None
        pending_verifications: list[tuple[CompiledNodeTransitionHypothesis, date, date]] = []
        # (hypothesis, generated_on, deadline)

        current = start_date
        while current <= end_date:
            # Skip non-trading days (no state available)
            state = state_by_date.get(current)
            if state is None:
                current += timedelta(days=1)
                continue

            # ── Step 1: Compile hypotheses from prev_state → state ──
            day_hypotheses: tuple[CompiledNodeTransitionHypothesis, ...] = ()
            if prev_state is not None:
                try:
                    diff = self.world.diff(prev_state, state)
                    day_hypotheses = self.compiler.compile(state, prev_state, diff)
                except Exception:
                    day_hypotheses = ()

                # Store.append each hypothesis
                policy_dict = state.policy_snapshot.to_dict()
                for h in day_hypotheses:
                    try:
                        self.store.append(
                            h,
                            state.state_id,
                            policy_dict,
                            state.evidence_refs,
                        )
                    except Exception:
                        pass  # duplicate → skip, already stored

                # Add to pending verifications
                for h in day_hypotheses:
                    deadline = _next_trade_day(current)
                    pending_verifications.append((h, current, deadline))

            # ── Step 2: Verify pending hypotheses ──
            day_verdicts: list[SimulationVerdict] = []
            still_pending: list[tuple[CompiledNodeTransitionHypothesis, date, date]] = []

            for hyp, generated_on, deadline in pending_verifications:
                if not _can_verify(current, deadline):
                    # available_at guard: cannot verify before deadline
                    still_pending.append((hyp, generated_on, deadline))
                    continue

                verdict = self._verify(hyp, generated_on, deadline, current, state)
                day_verdicts.append(verdict)

            pending_verifications = still_pending

            # ── Step 3: Record day ──
            timeline.append(SimulationDay(
                trade_date=current,
                state=state,
                hypotheses=day_hypotheses,
                verdicts=tuple(day_verdicts),
            ))

            prev_state = state
            current += timedelta(days=1)

        return timeline

    def _verify(
        self,
        hypothesis: CompiledNodeTransitionHypothesis,
        generated_on: date,
        deadline: date,
        verified_on: date,
        current_state: DailyMarketState,
    ) -> SimulationVerdict:
        """Verify one hypothesis against current day's reality.

        Checks whether the expected_transition actually occurred.
        """
        subject_id = _extract_subject_id(hypothesis.hypothesis_id)

        # Find the actual node for this subject in current state
        actual_node = ""
        for node in current_state.cycle_nodes:
            if node.subject_id == subject_id:
                actual_node = node.name
                break

        expected = hypothesis.expected_transition
        actual_transition = f"{hypothesis.current_node} → {actual_node}"

        if actual_node == expected:
            label = "CONFIRMED"
        elif actual_node and actual_node != hypothesis.current_node:
            # Node changed but not to the expected one
            label = "FALSIFIED"
        else:
            # Node hasn't changed at all (still at current_node)
            # If deadline has passed and no change → falsified
            label = "FALSIFIED"

        return SimulationVerdict(
            hypothesis_id=hypothesis.hypothesis_id,
            subject_id=subject_id,
            generated_on=generated_on,
            deadline=deadline,
            verified_on=verified_on,
            expected_transition=expected,
            actual_node=actual_node,
            actual_transition=actual_transition,
            label=label,
        )


# ──────────────────────────────────────────────
#  Trade calendar helpers
# ──────────────────────────────────────────────


def _next_trade_day(trade_date: date) -> date:
    """Simple next trading day (skip weekends)."""
    next_day = trade_date + timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += timedelta(days=1)
    return next_day


def _can_verify(current_date: date, deadline: date) -> bool:
    """available_at guard: can only verify on or after deadline."""
    return current_date >= deadline


def _extract_subject_id(hypothesis_id: str) -> str:
    """Extract subject_id from hypothesis_id.

    Format: hyp:YYYY-MM-DD:subject_id:hash
    Example: hyp:2026-07-03:theme:9026027:80aeb9e8b2692562
    """
    parts = hypothesis_id.split(":")
    if len(parts) >= 4 and parts[0] == "hyp":
        return ":".join(parts[2:-1])
    return hypothesis_id

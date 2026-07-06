"""Historical Simulation + SimulationTimeline.

Phase C — Simulation.
Not Replay (playback of existing results).
Simulation: step-by-step, only using available_at <= day data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from stock_processing_service.contracts.market_cognition_v1_5 import DailyMarketState


@dataclass(frozen=True, slots=True)
class SimulationDay:
    """One day in the simulation timeline."""
    date: date
    state: DailyMarketState | None = None
    hypotheses: tuple[Any, ...] = ()
    verdicts: tuple[Any, ...] = ()


@dataclass
class SimulationTimeline:
    """Complete simulation timeline — unified container for all simulation results."""

    days: list[SimulationDay] = field(default_factory=list)

    @property
    def states(self) -> tuple[DailyMarketState, ...]:
        return tuple(
            day.state for day in self.days if day.state is not None
        )

    @property
    def hypotheses(self) -> tuple[Any, ...]:
        result: list[Any] = []
        for day in self.days:
            result.extend(day.hypotheses)
        return tuple(result)

    @property
    def verdicts(self) -> tuple[Any, ...]:
        result: list[Any] = []
        for day in self.days:
            result.extend(day.verdicts)
        return tuple(result)

    def append(self, day: SimulationDay) -> None:
        self.days.append(day)


class HistoricalSimulation:
    """Step-by-step historical simulation. No future data leakage."""

    def __init__(self, world: Any) -> None:  # MarketWorldModel
        self.world = world

    def simulate(
        self, start_date: date, end_date: date
    ) -> SimulationTimeline:
        """Run simulation from start_date to end_date."""
        timeline = SimulationTimeline()

        prev_state: DailyMarketState | None = None
        current = start_date
        while current <= end_date:
            try:
                state = self.world.update(current)
            except Exception:
                current += date.resolution
                continue

            hypotheses: tuple[Any, ...] = ()
            if hasattr(self.world.pipeline, "compiler") and prev_state is not None:
                try:
                    hypotheses = self.world.pipeline.compiler.compile(
                        state, prev_state
                    )
                except Exception:
                    pass

            verdicts: tuple[Any, ...] = ()
            # Phase C.2: verify previous day's hypotheses

            timeline.append(SimulationDay(
                date=current,
                state=state,
                hypotheses=hypotheses,
                verdicts=verdicts,
            ))

            prev_state = state
            current += date.resolution

        return timeline

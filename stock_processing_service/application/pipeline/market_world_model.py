"""MarketWorldModel — Owner of World State.

Pipeline builds state. WorldModel maintains it.
Future Belief / Attention / Goal / Mental Simulation hang off WorldModel.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from stock_processing_service.contracts.market_cognition_v1_5 import (
    DailyMarketState,
    StateDiff,
)
from stock_processing_service.domain.policies.policy_registry import PolicyRegistry


@dataclass
class MarketWorldModel:
    """Owner of Market World State.

    Responsibilities:
      - Maintain current_state and history (State Chain)
      - Provide snapshot / rollback / diff
      - Own PolicyRegistry for versioned policy management
      - Reserve M9 Bridge entry points (all Optional, currently None)

    Pipeline is injected — WorldModel does NOT build state directly.
    """

    pipeline: Any = None  # CognitionPipeline (injected, avoids circular import)
    registry: PolicyRegistry = field(default_factory=PolicyRegistry)

    # ── World State ──
    current_state: DailyMarketState | None = None
    history: tuple[DailyMarketState, ...] = ()

    # ── M9 Bridge — all Optional, current implementation = None ──
    working_memory: None = None
    belief_state: None = None
    attention_state: None = None
    goal_state: None = None

    # ── Public API ──

    def update(self, trade_date: date) -> DailyMarketState:
        """Pipeline.run() → update current_state → append history."""
        if self.pipeline is None:
            raise RuntimeError("MarketWorldModel.pipeline is not set")
        state = self.pipeline.run(trade_date)
        self.history += (state,)
        self.current_state = state
        return state

    def snapshot(self) -> DailyMarketState | None:
        """Return current immutable state snapshot."""
        return self.current_state

    def rollback(self, state_id: str) -> DailyMarketState:
        """Rollback to a specific historical state_id."""
        for s in reversed(self.history):
            if s.state_id == state_id:
                self.current_state = s
                return s
        raise KeyError(f"State {state_id} not found in history")

    def diff(
        self, s1: DailyMarketState, s2: DailyMarketState
    ) -> StateDiff:
        """Compute structured diff between two World States."""
        s1_nodes = {n.subject_id: n.name for n in s1.cycle_nodes}
        s2_nodes = {n.subject_id: n.name for n in s2.cycle_nodes}

        node_changes = []
        all_subjects = set(s1_nodes.keys()) | set(s2_nodes.keys())
        for sid in all_subjects:
            from_n = s1_nodes.get(sid)
            to_n = s2_nodes.get(sid)
            if from_n != to_n:
                from stock_processing_service.contracts.market_cognition_v1_5 import (
                    NodeChange,
                )
                node_changes.append(NodeChange(
                    subject_id=sid, from_node=from_n, to_node=to_n,
                ))

        s1_maturities = {m.subject_id: m.overall for m in s1.maturity_estimates}
        s2_maturities = {m.subject_id: m.overall for m in s2.maturity_estimates}

        maturity_changes = []
        for sid in set(s1_maturities.keys()) | set(s2_maturities.keys()):
            fm = s1_maturities.get(sid)
            tm = s2_maturities.get(sid)
            if fm is not None and tm is not None:
                from stock_processing_service.contracts.market_cognition_v1_5 import (
                    MaturityChange,
                )
                maturity_changes.append(MaturityChange(
                    subject_id=sid, from_maturity=fm, to_maturity=tm, delta=tm - fm,
                ))

        return StateDiff(
            from_state=s1.state_id,
            to_state=s2.state_id,
            node_changes=tuple(node_changes),
            maturity_changes=tuple(maturity_changes),
        )

    def simulate(self, start: date, end: date) -> Any:
        """Historical Simulation → SimulationTimeline. (Phase C)"""
        from stock_processing_service.application.pipeline.simulation import (
            HistoricalSimulation,
        )
        sim = HistoricalSimulation(self)
        return sim.simulate(start, end)

    @property
    def state_chain(self) -> tuple[str, ...]:
        """Return ordered state_id chain from history."""
        return tuple(s.state_id for s in self.history)

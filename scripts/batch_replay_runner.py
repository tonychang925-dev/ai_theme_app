#!/usr/bin/env python3
"""Phase White Paper — Batch Replay Runner.

Builds DailyMarketState objects for a date range, runs the full
Phase 1.5 pipeline (Simulation → Validation), and saves results.

Usage:
  # Smoke test (3 days, synthetic data)
  PYTHONPATH=. python3 scripts/batch_replay_runner.py --dry-run

  # Full replay (synthetic test data)
  PYTHONPATH=. python3 scripts/batch_replay_runner.py --start 2025-07-01 --end 2026-07-03

  # Real DB data (when available)
  PYTHONPATH=. python3 scripts/batch_replay_runner.py --start 2025-07-01 --end 2026-07-03 --source db
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ── Lazy imports for components that need PYTHONPATH ──


def _import_world_state_input():
    from stock_processing_service.application.services.market_cognition.world_state_builder_service import (
        WorldStateInput,
    )
    return WorldStateInput


def _import_cycle_node():
    from stock_processing_service.contracts.market_cognition_v1_5 import (
        CycleNode, MarketSubject, TransitionCandidate,
    )
    return CycleNode, MarketSubject, TransitionCandidate


# ──────────────────────────────────────────────
#  StateSource interface
# ──────────────────────────────────────────────


class StateSource(ABC):
    """Pluggable data source for building DailyMarketState objects.

    Implementations:
      - SyntheticStateSource: generates FSM-progressed test data
      - DbStateSource: loads from post_market_recap_snapshot (future)
    """

    @abstractmethod
    def trading_days(self, start: date, end: date) -> list[date]:
        """Return all trading days in range with available data."""
        ...

    @abstractmethod
    def build_state(
        self, trade_date: date, parent_state_id: str | None
    ):
        """Build WorldStateInput for one trading day. Returns None if no data."""
        ...


# ──────────────────────────────────────────────
#  SyntheticStateSource — FSM-driven test data generator
# ──────────────────────────────────────────────


@dataclass
class ThemeProgression:
    """FSM-driven theme lifecycle progression for synthetic data."""
    subject_id: str
    name: str
    nodes: list[str]  # ordered node progression
    stage_days: list[int]
    node_index: int = 0

    def advance(self) -> str | None:
        """Move to next node. Returns None if at end."""
        if self.node_index + 1 < len(self.nodes):
            self.node_index += 1
            return self.nodes[self.node_index]
        return None

    @property
    def current_node(self) -> str:
        return self.nodes[self.node_index]

    @property
    def current_stage_day(self) -> int:
        return self.stage_days[min(self.node_index, len(self.stage_days) - 1)]


# Realistic theme progressions for 3 themes over ~120 trading days
_SYNTHETIC_THEME_CONFIGS = [
    ThemeProgression(
        subject_id="theme:9026027", name="机器人",
        nodes=["FERMENTATION", "ACCELERATION", "CLIMAX", "FIRST_DIVERGENCE",
               "DIVERGENCE_WEAKENING", "DIVERGENCE_REPAIR", "WEAK_TO_STRONG",
               "SECOND_ACCELERATION", "CLIMAX", "FADE"],
        stage_days=[5, 8, 6, 3, 4, 5, 6, 8, 10, 12],
    ),
    ThemeProgression(
        subject_id="theme:9026028", name="通信/CPO",
        nodes=["INITIAL", "FERMENTATION", "ACCELERATION", "CLIMAX",
               "FIRST_DIVERGENCE", "DIVERGENCE_REPAIR", "WEAK_TO_STRONG",
               "CLIMAX", "FIRST_DIVERGENCE", "FADE"],
        stage_days=[3, 6, 7, 5, 4, 6, 7, 9, 5, 10],
    ),
    ThemeProgression(
        subject_id="theme:9026030", name="上游材料",
        nodes=["CHAOS", "INITIAL", "FERMENTATION", "ACCELERATION",
               "FIRST_DIVERGENCE", "DIVERGENCE_WEAKENING", "FADE",
               "ICE_POINT", "REBOUND", "INITIAL"],
        stage_days=[4, 3, 5, 6, 4, 5, 8, 6, 5, 4],
    ),
]

# Node → stage mapping
_NODE_STAGE = {
    "CHAOS": "混沌", "INITIAL": "启动", "FERMENTATION": "发酵",
    "ACCELERATION": "加速", "CLIMAX": "高潮",
    "FIRST_DIVERGENCE": "第一次分歧", "SECOND_DIVERGENCE": "第二次分歧",
    "DIVERGENCE_REPAIR": "分歧修复", "DIVERGENCE_WEAKENING": "分歧减弱",
    "WEAK_TO_STRONG": "弱转强", "SECOND_ACCELERATION": "二次加速",
    "FADE": "退潮", "ICE_POINT": "冰点", "REBOUND": "反弹",
    "SECOND_WAVE": "二波", "CYCLE_END": "周期结束",
}

# Direction per node
_NODE_DIRECTION = {
    "CHAOS": "neutral", "INITIAL": "accelerating", "FERMENTATION": "accelerating",
    "ACCELERATION": "accelerating", "CLIMAX": "accelerating",
    "FIRST_DIVERGENCE": "diverging", "SECOND_DIVERGENCE": "diverging",
    "DIVERGENCE_REPAIR": "repairing", "DIVERGENCE_WEAKENING": "fading",
    "WEAK_TO_STRONG": "accelerating", "SECOND_ACCELERATION": "accelerating",
    "FADE": "fading", "ICE_POINT": "neutral", "REBOUND": "repairing",
    "SECOND_WAVE": "accelerating", "CYCLE_END": "neutral",
}

# Quality label per node
_NODE_QUALITY = {
    "ACCELERATION": "accelerating", "CLIMAX": "peaking",
    "FIRST_DIVERGENCE": "exhausting", "SECOND_DIVERGENCE": "exhausting",
    "DIVERGENCE_REPAIR": "repairing", "FADE": "stalling",
    "ICE_POINT": "stalling", "REBOUND": "repairing",
}

# Default maturity per node
_NODE_MATURITY = {
    "CHAOS": 25, "INITIAL": 35, "FERMENTATION": 45,
    "ACCELERATION": 65, "CLIMAX": 82,
    "FIRST_DIVERGENCE": 72, "SECOND_DIVERGENCE": 68,
    "DIVERGENCE_REPAIR": 55, "DIVERGENCE_WEAKENING": 60,
    "WEAK_TO_STRONG": 65, "SECOND_ACCELERATION": 75,
    "FADE": 40, "ICE_POINT": 20, "REBOUND": 45,
    "SECOND_WAVE": 55, "CYCLE_END": 10,
}

# Default confidence per node
_NODE_CONFIDENCE = {
    "CHAOS": 0.55, "INITIAL": 0.60, "FERMENTATION": 0.65,
    "ACCELERATION": 0.75, "CLIMAX": 0.85,
    "FIRST_DIVERGENCE": 0.78, "SECOND_DIVERGENCE": 0.72,
    "DIVERGENCE_REPAIR": 0.68, "DIVERGENCE_WEAKENING": 0.70,
    "WEAK_TO_STRONG": 0.72, "SECOND_ACCELERATION": 0.80,
    "FADE": 0.65, "ICE_POINT": 0.60, "REBOUND": 0.62,
    "SECOND_WAVE": 0.65, "CYCLE_END": 0.70,
}


class SyntheticStateSource(StateSource):
    """Generate realistic FSM-progressed test data for batch replay."""

    def __init__(self, registry: Any, fsm: Any) -> None:
        self.registry = registry
        self.fsm = fsm
        self._day_counter: dict[str, int] = {}  # track days-in-stage per theme

    def trading_days(self, start: date, end: date) -> list[date]:
        days: list[date] = []
        current = start
        while current <= end:
            if current.weekday() < 5:  # weekday
                days.append(current)
            current += timedelta(days=1)
        return days

    def build_state(
        self, trade_date: date, parent_state_id: str | None
    ):
        """Build one day's WorldStateInput with FSM-progressed themes."""
        WorldStateInput = _import_world_state_input()
        CycleNode, MarketSubject, TransitionCandidate = _import_cycle_node()

        subjects: list[MarketSubject] = []
        cycle_nodes: list[CycleNode] = []
        dq_vectors: dict[str, tuple[float, float, float, float, float]] = {}
        nm_vectors: dict[str, tuple[float, float, float, float, float]] = {}

        day_num = (trade_date - date(2025, 7, 1)).days
        if day_num < 0:
            return None

        for cfg in _SYNTHETIC_THEME_CONFIGS:
            # Advance theme based on trading days elapsed
            node_idx = min(day_num // 6, len(cfg.nodes) - 1)  # ~6 days per stage
            node_name = cfg.nodes[node_idx]

            subjects.append(MarketSubject(
                subject_id=cfg.subject_id, subject_type="theme", name=cfg.name,
            ))

            # Compute transitions for next stage
            next_idx = min(node_idx + 1, len(cfg.nodes) - 1)
            transitions: list[TransitionCandidate] = []
            if node_idx < len(cfg.nodes) - 1:
                # Valid FSM transitions
                next_node = cfg.nodes[next_idx]
                if self.fsm.is_valid_transition(node_name, next_node):
                    transitions.append(TransitionCandidate(next_node, 0.45 + 0.05 * min(node_idx, 10)))
                # Also add random alternatives for realism
                for alt in self.fsm.allowed_next(node_name):
                    if alt != next_node:
                        transitions.append(TransitionCandidate(alt, 0.20))

            stage_day = (day_num % 6) + 1
            node = CycleNode(
                node_id=f"cn:{cfg.subject_id}:{trade_date.isoformat()}",
                subject_id=cfg.subject_id,
                trade_date=trade_date,
                name=node_name,
                stage=_NODE_STAGE.get(node_name, "未知"),
                stage_day=stage_day,
                consecutive_direction=_NODE_DIRECTION.get(node_name, "neutral"),
                maturity=_NODE_MATURITY.get(node_name, 50),
                confidence=_NODE_CONFIDENCE.get(node_name, 0.70),
                transition_candidates=tuple(transitions),
                quality_label=_NODE_QUALITY.get(node_name, ""),
            )
            cycle_nodes.append(node)

            # Divergence vectors — realistic values per node type
            if node_name in ("FIRST_DIVERGENCE", "SECOND_DIVERGENCE"):
                dq_vectors[cfg.subject_id] = (0.5, 0.6, 0.4, 0.4, 0.5)
            elif node_name == "DIVERGENCE_REPAIR":
                dq_vectors[cfg.subject_id] = (0.7, 0.65, 0.7, 0.5, 0.7)
            elif node_name == "DIVERGENCE_WEAKENING":
                dq_vectors[cfg.subject_id] = (0.5, 0.6, 0.4, 0.4, 0.5)
            elif node_name == "CLIMAX":
                dq_vectors[cfg.subject_id] = (0.3, 0.95, 0.2, 0.7, 0.4)
            elif node_name == "FADE":
                dq_vectors[cfg.subject_id] = (0.8, 0.3, 0.8, 0.2, 0.8)
            else:
                dq_vectors[cfg.subject_id] = (0.5, 0.5, 0.5, 0.5, 0.5)

            # Maturity vectors
            mat = _NODE_MATURITY.get(node_name, 50)
            nm_vectors[cfg.subject_id] = (mat, 60.0, 55.0, 50.0, 40.0)

        return WorldStateInput(
            trade_date=trade_date,
            subjects=tuple(subjects),
            cycle_nodes=tuple(cycle_nodes),
            divergence_vectors=dq_vectors,
            maturity_vectors=nm_vectors,
            evidence_refs=(f"ev:{trade_date.isoformat()}",),
            parent_state=parent_state_id,
        )


# ──────────────────────────────────────────────
#  DbStateSource — real DB data
# ──────────────────────────────────────────────

# Map CycleJudgementService final_cycle_state → FSM CYCLE_NODES
_CYCLE_STATE_TO_FSM: dict[str, str] = {
    "start": "INITIAL",
    "acceleration": "ACCELERATION",
    "fermentation": "FERMENTATION",
    "divergence": "FIRST_DIVERGENCE",
    "repair": "DIVERGENCE_REPAIR",
    "fade_watch": "DIVERGENCE_WEAKENING",
    "fade_confirmed": "FADE",
}

# FSM node → stage label
_FSM_STAGE = {
    "INITIAL": "启动", "FERMENTATION": "发酵", "ACCELERATION": "加速",
    "CLIMAX": "高潮", "FIRST_DIVERGENCE": "第一次分歧",
    "SECOND_DIVERGENCE": "第二次分歧", "DIVERGENCE_REPAIR": "分歧修复",
    "DIVERGENCE_WEAKENING": "分歧减弱", "WEAK_TO_STRONG": "弱转强",
    "SECOND_ACCELERATION": "二次加速", "FADE": "退潮",
    "ICE_POINT": "冰点", "REBOUND": "反弹", "CHAOS": "混沌",
    "SECOND_WAVE": "二波", "CYCLE_END": "周期结束",
}

# FSM node → direction
_FSM_DIRECTION: dict[str, str] = {
    "INITIAL": "accelerating", "FERMENTATION": "accelerating",
    "ACCELERATION": "accelerating", "CLIMAX": "accelerating",
    "FIRST_DIVERGENCE": "diverging", "SECOND_DIVERGENCE": "diverging",
    "DIVERGENCE_REPAIR": "repairing", "DIVERGENCE_WEAKENING": "fading",
    "WEAK_TO_STRONG": "accelerating", "SECOND_ACCELERATION": "accelerating",
    "FADE": "fading", "ICE_POINT": "neutral", "REBOUND": "repairing",
    "CHAOS": "neutral", "SECOND_WAVE": "accelerating", "CYCLE_END": "neutral",
}

# FSM node → maturity
_FSM_MATURITY: dict[str, float] = {
    "INITIAL": 35, "FERMENTATION": 45, "ACCELERATION": 65,
    "CLIMAX": 82, "FIRST_DIVERGENCE": 72, "SECOND_DIVERGENCE": 68,
    "DIVERGENCE_REPAIR": 55, "DIVERGENCE_WEAKENING": 60,
    "WEAK_TO_STRONG": 65, "SECOND_ACCELERATION": 75,
    "FADE": 40, "ICE_POINT": 20, "REBOUND": 45,
    "CHAOS": 25, "SECOND_WAVE": 55, "CYCLE_END": 10,
}

# FSM node → quality
_FSM_QUALITY: dict[str, str] = {
    "ACCELERATION": "accelerating", "CLIMAX": "peaking",
    "FIRST_DIVERGENCE": "exhausting", "SECOND_DIVERGENCE": "exhausting",
    "DIVERGENCE_REPAIR": "repairing", "FADE": "stalling",
    "ICE_POINT": "stalling", "REBOUND": "repairing",
}

DB_DSN = "postgresql://localhost:5432/stock_data_test"


class DbStateSource(StateSource):
    """Load DailyMarketState from theme_cycle_judgement_v2 (richer than payload).

    Queries theme_cycle_judgement_v2 directly for final_cycle_state,
    scores, and mainline status per subject per day.
    """

    def __init__(self, registry: Any, fsm: Any) -> None:
        self.registry = registry
        self.fsm = fsm

    def trading_days(self, start: date, end: date) -> list[date]:
        import asyncio
        return asyncio.run(self._trading_days_async(start, end))

    async def _trading_days_async(self, start: date, end: date) -> list[date]:
        import asyncpg
        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            rows = await conn.fetch(
                "SELECT DISTINCT trade_date FROM theme_cycle_judgement_v2 "
                "WHERE trade_date >= $1::date AND trade_date <= $2::date "
                "ORDER BY trade_date ASC",
                start, end,
            )
            return [r["trade_date"] for r in rows]
        finally:
            await conn.close()

    def build_state(
        self, trade_date: date, parent_state_id: str | None
    ):
        import asyncio
        return asyncio.run(self._build_state_async(trade_date, parent_state_id))

    async def _build_state_async(
        self, trade_date: date, parent_state_id: str | None
    ):
        import asyncpg

        WorldStateInput = _import_world_state_input()
        CycleNode, MarketSubject, TransitionCandidate = _import_cycle_node()

        conn = await asyncpg.connect(DB_DSN, user="postgres", password="")
        try:
            rows = await conn.fetch(
                "SELECT subject_key, theme_name, final_cycle_state, "
                "final_mainline_alive, mainline_strength_score, "
                "fade_watch_score, fade_confirmed_score, "
                "divergence_score, repair_score "
                "FROM theme_cycle_judgement_v2 "
                "WHERE trade_date = $1::date",
                trade_date,
            )
            if not rows:
                return None

            subjects: list[Any] = []
            cycle_nodes: list[Any] = []
            dq_vectors: dict[str, tuple[float, float, float, float, float]] = {}
            nm_vectors: dict[str, tuple[float, float, float, float, float]] = {}

            for row in rows:
                subject_key = str(row["subject_key"])
                subject_id = f"theme:{subject_key}"
                theme_name = row["theme_name"] or subject_key
                raw_state = row["final_cycle_state"] or "start"

                # Map CycleJudgement state → FSM node
                fsm_node = _CYCLE_STATE_TO_FSM.get(raw_state, "CHAOS")

                subjects.append(MarketSubject(
                    subject_id=subject_id, subject_type="theme", name=theme_name,
                ))

                # Transition candidates from FSM
                transitions: list[Any] = []
                allowed = self.fsm.allowed_next(fsm_node)
                for i, alt in enumerate(allowed[:3]):
                    prob = 0.45 + 0.10 * (3 - i)
                    transitions.append(TransitionCandidate(alt, min(prob, 0.85)))

                maturity = _FSM_MATURITY.get(fsm_node, 50.0)
                ms_score = float(row["mainline_strength_score"] or 50.0)
                fw_score = float(row["fade_watch_score"] or 0.0)
                fc_score = float(row["fade_confirmed_score"] or 0.0)
                div_score = float(row["divergence_score"] or 0.0)
                rep_score = float(row["repair_score"] or 0.0)

                cycle_nodes.append(CycleNode(
                    node_id=f"cn:{subject_id}:{trade_date.isoformat()}",
                    subject_id=subject_id,
                    trade_date=trade_date,
                    name=fsm_node,
                    stage=_FSM_STAGE.get(fsm_node, "未知"),
                    stage_day=1,
                    consecutive_direction=_FSM_DIRECTION.get(fsm_node, "neutral"),
                    maturity=maturity,
                    confidence=0.70,
                    transition_candidates=tuple(transitions),
                    quality_label=_FSM_QUALITY.get(fsm_node, ""),
                ))

                # Divergence vector — computed from state semantics, not raw scores.
                # The goal is to produce a quality_label that reflects the node.
                if fsm_node == "DIVERGENCE_REPAIR":
                    # Repair = healthy divergence resolution
                    dq_vectors[subject_id] = (0.7, 0.65, 0.7, 0.7, 0.7)
                elif fsm_node == "FIRST_DIVERGENCE":
                    # Divergence = varied; use scores to determine if healthy or not
                    if rep_score > 50:
                        dq_vectors[subject_id] = (0.6, 0.55, 0.6, 0.6, 0.6)
                    else:
                        dq_vectors[subject_id] = (0.4, 0.5, 0.4, 0.4, 0.4)
                elif fsm_node == "DIVERGENCE_WEAKENING":
                    if rep_score > 40:
                        dq_vectors[subject_id] = (0.55, 0.6, 0.55, 0.55, 0.6)
                    else:
                        dq_vectors[subject_id] = (0.4, 0.5, 0.4, 0.4, 0.4)
                elif fsm_node == "FADE":
                    dq_vectors[subject_id] = (0.8, 0.3, 0.8, 0.2, 0.8)
                elif fsm_node == "CLIMAX":
                    dq_vectors[subject_id] = (0.3, 0.95, 0.2, 0.7, 0.4)
                else:
                    dq_vectors[subject_id] = (0.5, 0.5, 0.5, 0.5, 0.5)

                # Maturity vector from scores
                nm_vectors[subject_id] = (
                    maturity, ms_score, rep_score, div_score, fw_score
                )

            return WorldStateInput(
                trade_date=trade_date,
                subjects=tuple(subjects),
                cycle_nodes=tuple(cycle_nodes),
                divergence_vectors=dq_vectors,
                maturity_vectors=nm_vectors,
                evidence_refs=(f"ev:db:{trade_date.isoformat()}",),
                parent_state=parent_state_id,
            )

        finally:
            await conn.close()


# ──────────────────────────────────────────────
#  Batch replay stats
# ──────────────────────────────────────────────


@dataclass
class BatchResult:
    start_date: date
    end_date: date
    total_trading_days: int
    days_built: int
    days_skipped: int
    hypotheses_generated: int
    verdicts_confirmed: int
    verdicts_falsified: int
    simulation_hash: str
    validation_levels_passed: int
    validation_levels_total: int
    elapsed_seconds: float
    errors: list[str] = field(default_factory=list)


# ──────────────────────────────────────────────
#  BatchReplayRunner
# ──────────────────────────────────────────────


class BatchReplayRunner:
    """Orchestrate batch replay: build → persist → simulate → validate → save."""

    def __init__(
        self,
        source: StateSource,
        builder: Any,  # WorldStateBuilderService
        persister: Any,  # WorldStatePersister
        output_dir: Path,
    ) -> None:
        self.source = source
        self.builder = builder
        self.persister = persister
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, start: date, end: date) -> BatchResult:
        t0 = time.monotonic()
        errors: list[str] = []

        trading_days = self.source.trading_days(start, end)
        print(f"Date range: {start} → {end}")
        print(f"Trading days: {len(trading_days)}")

        # ── Phase 1: Build & Persist ──
        print(f"\n--- Phase 1: Building World States ---")
        days_built = 0
        days_skipped = 0
        parent_state_id: str | None = None

        for i, td in enumerate(trading_days):
            # Skip if cached
            if self.persister.exists(td):
                state = self.persister.load(td)
                if state is not None:
                    parent_state_id = state.state_id
                    days_built += 1
                    if (i + 1) % 20 == 0:
                        print(f"  [{i+1}/{len(trading_days)}] {td} (cached)")
                    continue

            # Build from source
            try:
                state_input = self.source.build_state(td, parent_state_id)
            except Exception as e:
                errors.append(f"{td}: build_state failed: {e}")
                days_skipped += 1
                continue

            if state_input is None:
                days_skipped += 1
                continue

            try:
                state = self.builder.build(state_input)
            except Exception as e:
                errors.append(f"{td}: builder.build failed: {e}")
                days_skipped += 1
                continue

            self.persister.save(state)
            parent_state_id = state.state_id
            days_built += 1

            if (i + 1) % 20 == 0:
                print(f"  [{i+1}/{len(trading_days)}] {td} built: {state.state_id[:32]}...")

        print(f"  Built: {days_built}  Skipped: {days_skipped}  Errors: {len(errors)}")

        # ── Phase 2: Load into WorldModel ──
        print(f"\n--- Phase 2: Loading World Model ---")
        states = []
        for td in trading_days:
            state = self.persister.load(td)
            if state is not None:
                states.append(state)
        print(f"  Loaded {len(states)} states")

        # ── Phase 3: Simulation ──
        print(f"\n--- Phase 3: Historical Simulation ---")
        from stock_processing_service.application.pipeline.market_world_model import (
            MarketWorldModel,
        )
        from stock_processing_service.application.pipeline.simulation import (
            HistoricalSimulation,
        )
        from stock_processing_service.application.pipeline.compilers.world_state_transition_compiler import (
            CompilerPolicy,
            WorldStateTransitionCompiler,
        )
        from stock_processing_service.application.pipeline.compilers.node_transition_hypothesis_store import (
            NodeTransitionHypothesisStore,
        )

        compiler_policy = CompilerPolicy(
            str(PROJECT_ROOT / "config" / "market_cognition" / "compiler_policy_v1.yaml")
        )
        fsm_for_compiler = self.builder.fsm
        compiler = WorldStateTransitionCompiler(compiler_policy, fsm_for_compiler)
        store = NodeTransitionHypothesisStore(self.output_dir / "hypothesis_store")

        world = MarketWorldModel(registry=self.builder.registry)
        world.history = tuple(states)
        world.current_state = states[-1] if states else None

        sim = HistoricalSimulation(world, compiler, store)
        timeline = sim.simulate(start, end)
        sim_hash = timeline.compute_hash()

        confirmed = sum(1 for v in timeline.verdicts if v.is_confirmed())
        falsified = sum(1 for v in timeline.verdicts if v.is_falsified())

        print(f"  Timeline: {len(timeline.days)} days")
        print(f"  Hypotheses: {len(timeline.hypotheses)}")
        print(f"  Verdicts: {len(timeline.verdicts)} (C={confirmed} F={falsified})")
        print(f"  Simulation hash: {sim_hash[:24]}...")

        # ── Phase 4: Validation ──
        print(f"\n--- Phase 4: Market World Validation ---")
        from stock_processing_service.application.pipeline.metrics.validation_metrics import (
            MarketWorldValidator,
        )

        validator = MarketWorldValidator()
        dashboard = validator.validate(timeline)

        passed = sum(1 for lv in dashboard.levels if lv.passed)
        total = len(dashboard.levels)
        for lv in dashboard.levels:
            s = "PASS" if lv.passed else "FAIL"
            print(f"  L{lv.level} {lv.name}: [{s}]")

        # ── Phase 5: Save Results ──
        print(f"\n--- Phase 5: Saving Results ---")
        # Save dashboard
        dashboard_path = self.output_dir / "dashboard.json"
        dashboard_path.write_text(dashboard.to_json(), encoding="utf-8")
        print(f"  Dashboard: {dashboard_path}")

        # Save validation report
        report_path = self.output_dir / "validation_report.md"
        report_path.write_text(dashboard.to_validation_report(), encoding="utf-8")
        print(f"  Report: {report_path}")

        # Save simulation metadata
        meta = {
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_trading_days": len(trading_days),
            "days_built": days_built,
            "days_skipped": days_skipped,
            "states_loaded": len(states),
            "hypotheses_generated": len(timeline.hypotheses),
            "verdicts_total": len(timeline.verdicts),
            "verdicts_confirmed": confirmed,
            "verdicts_falsified": falsified,
            "simulation_hash": sim_hash,
            "validation_levels_passed": passed,
            "validation_levels_total": total,
            "all_passed": dashboard.all_passed,
            "first_failed_level": dashboard.first_failed_level,
            "errors": errors,
        }
        meta_path = self.output_dir / "simulation_meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))
        print(f"  Meta: {meta_path}")

        # Save timeline summary
        timeline_summary = {
            "hash": sim_hash,
            "days": [
                {
                    "trade_date": d.trade_date.isoformat(),
                    "n_hypotheses": len(d.hypotheses),
                    "n_verdicts": len(d.verdicts),
                    "hypotheses": [
                        {"id": h.hypothesis_id, "from": h.current_node, "to": h.expected_transition}
                        for h in d.hypotheses
                    ],
                    "verdicts": [
                        {"label": v.label, "expected": v.expected_transition, "actual": v.actual_node}
                        for v in d.verdicts
                    ],
                }
                for d in timeline.days
                if d.hypotheses or d.verdicts
            ],
        }
        timeline_path = self.output_dir / "timeline_summary.json"
        timeline_path.write_text(json.dumps(timeline_summary, ensure_ascii=False, indent=2))
        print(f"  Timeline: {timeline_path}")

        elapsed = time.monotonic() - t0
        print(f"\n{'='*60}")
        print(f"Batch replay complete in {elapsed:.1f}s")
        print(f"  {days_built} states  |  {len(timeline.hypotheses)} hypotheses  |  {passed}/{total} validation layers")
        print(f"{'='*60}")

        return BatchResult(
            start_date=start, end_date=end,
            total_trading_days=len(trading_days),
            days_built=days_built, days_skipped=days_skipped,
            hypotheses_generated=len(timeline.hypotheses),
            verdicts_confirmed=confirmed, verdicts_falsified=falsified,
            simulation_hash=sim_hash,
            validation_levels_passed=passed, validation_levels_total=total,
            elapsed_seconds=elapsed, errors=errors,
        )


# ──────────────────────────────────────────────
#  CLI
# ──────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch replay for Market World Validation White Paper")
    parser.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="3-day smoke test (2026-07-01 to 2026-07-03)")
    parser.add_argument("--source", default="synthetic", choices=["synthetic", "db"],
                        help="State source type (default: synthetic)")
    parser.add_argument("--cache", default="tmp/world_states", help="Cache directory for WorldStatePersister")
    parser.add_argument("--dataset", default="datasets/white_paper", help="Output directory for results")
    args = parser.parse_args()

    sys.path.insert(0, str(PROJECT_ROOT))

    from stock_processing_service.domain.policies.cycle_fsm import CycleFSM
    from stock_processing_service.domain.policies.policy_registry import PolicyRegistry
    from stock_processing_service.application.pipeline.analyzers.divergence_quality import DivergencePolicy
    from stock_processing_service.application.pipeline.estimators.node_maturity import MaturityPolicy
    from stock_processing_service.application.services.market_cognition.world_state_builder_service import (
        WorldStateBuilderService, WorldStateInput,
    )
    from stock_processing_service.application.services.market_cognition.world_state_persister import (
        WorldStatePersister,
    )

    # Bootstrap
    fsm = CycleFSM(str(PROJECT_ROOT / "config" / "market_cognition" / "cycle_fsm_v1.yaml"))
    dp = DivergencePolicy(str(PROJECT_ROOT / "config" / "market_cognition" / "divergence_policy_v1.yaml"))
    mp = MaturityPolicy(str(PROJECT_ROOT / "config" / "market_cognition" / "maturity_policy_v1.yaml"))
    reg = PolicyRegistry()
    for n, v in [("cycle_fsm", "v1"), ("divergence", "v1"), ("maturity", "v1"), ("compiler", "v1")]:
        reg.register(n, v, {}, date(2026, 1, 1))

    builder = WorldStateBuilderService(reg, fsm, dp, mp)
    persister = WorldStatePersister(Path(args.cache))

    # Determine date range
    if args.dry_run:
        start_date = date(2026, 7, 1)
        end_date = date(2026, 7, 3)
        print("=== DRY RUN (3-day smoke test) ===\n")
    elif args.start and args.end:
        start_date = date.fromisoformat(args.start)
        end_date = date.fromisoformat(args.end)
    else:
        parser.error("Must specify --start/--end or --dry-run")

    # Select source
    if args.source == "synthetic":
        source = SyntheticStateSource(reg, fsm)
    else:
        source = DbStateSource(reg, fsm)

    # Run
    runner = BatchReplayRunner(source, builder, persister, Path(args.dataset))
    result = runner.run(start_date, end_date)

    # Exit code
    if result.errors:
        print(f"\nErrors: {len(result.errors)}")
        for e in result.errors[:5]:
            print(f"  - {e}")
    sys.exit(0 if result.days_built > 0 else 1)


if __name__ == "__main__":
    main()

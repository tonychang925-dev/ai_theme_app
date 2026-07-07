"""WorldStateBuilderService — bridge real data to DailyMarketState.

Wires CycleJudgementService output + DivergencePolicy + MaturityPolicy
into a complete DailyMarketState object for the White Paper replay.

Zero modification to existing Phase 1.5 infrastructure.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from stock_processing_service.application.pipeline.analyzers.divergence_quality import (
    DivergencePolicy,
)
from stock_processing_service.application.pipeline.estimators.node_maturity import (
    MaturityPolicy,
)
from stock_processing_service.contracts.market_cognition_v1_5 import (
    CYCLE_NODES,
    CycleNode,
    DailyMarketState,
    DivergenceQuality,
    MarketSubject,
    NodeMaturity,
    PolicySnapshot,
    TransitionCandidate,
)
from stock_processing_service.domain.policies.cycle_fsm import CycleFSM
from stock_processing_service.domain.policies.policy_registry import PolicyRegistry


@dataclass
class WorldStateInput:
    """Collected inputs for building one DailyMarketState."""
    trade_date: date
    subjects: tuple[MarketSubject, ...]
    cycle_nodes: tuple[CycleNode, ...]
    divergence_vectors: dict[str, tuple[float, float, float, float, float]]  # subject_id -> (vc, li, rc, cr, ds)
    maturity_vectors: dict[str, tuple[float, float, float, float, float]]    # subject_id -> (crowding, volume, leader, emotion, time)
    evidence_refs: tuple[str, ...]
    parent_state: str | None
    policy_snapshot: PolicySnapshot | None = None


class WorldStateBuilderService:
    """Build DailyMarketState from real data sources.

    Does NOT own data — accepts pre-computed CycleNodes, vectors, and subjects.
    Uses DivergencePolicy + MaturityPolicy for deterministic label derivation.
    """

    def __init__(
        self,
        registry: PolicyRegistry,
        fsm: CycleFSM,
        divergence_policy: DivergencePolicy,
        maturity_policy: MaturityPolicy,
    ) -> None:
        self.registry = registry
        self.fsm = fsm
        self.divergence_policy = divergence_policy
        self.maturity_policy = maturity_policy

    def build(self, data: WorldStateInput) -> DailyMarketState:
        """Build a complete DailyMarketState from real-world inputs.

        All inputs are pre-validated. CycleNodes must pass FSM validation.
        DivergenceQuality and NodeMaturity are derived from vectors via Policy.
        """
        trade_date = data.trade_date
        policy_snapshot = data.policy_snapshot or self.registry.snapshot()
        tz = timezone.utc

        # ── Validate all cycle nodes against FSM ──
        for node in data.cycle_nodes:
            if node.name not in CYCLE_NODES:
                raise ValueError(f"Invalid cycle node name: {node.name!r} (subject={node.subject_id})")

        # ── Build DivergenceQuality objects from vectors ──
        dq_objects: list[DivergenceQuality] = []
        for subject_id, vec in data.divergence_vectors.items():
            vc, li, rc, cr, ds = vec
            label = self.divergence_policy.derive_label(vc, li, rc, cr, ds)
            quality_id = f"dq:{subject_id}:{trade_date.isoformat()}"
            dq_objects.append(DivergenceQuality(
                quality_id=quality_id,
                subject_id=subject_id,
                trade_date=trade_date,
                volume_contraction=vc,
                leader_intact=li,
                rear_cleared=rc,
                capital_redirected=cr,
                duration_sufficient=ds,
                quality_label=label,
                policy_version=self.divergence_policy.version,
                evidence_refs=data.evidence_refs,
            ))

        # ── Build NodeMaturity objects from vectors ──
        nm_objects: list[NodeMaturity] = []
        for subject_id, vec in data.maturity_vectors.items():
            crowding, volume, leader, emotion, time_val = vec
            overall = self.maturity_policy.compute_overall(
                crowding, volume, leader, emotion, time_val
            )
            # Derive quality_label from overall + a simple velocity heuristic
            quality_label = self.maturity_policy.derive_quality_label(overall)
            maturity_id = f"nm:{subject_id}:{trade_date.isoformat()}"
            nm_objects.append(NodeMaturity(
                maturity_id=maturity_id,
                subject_id=subject_id,
                trade_date=trade_date,
                overall=overall,
                crowding=crowding,
                volume=volume,
                leader=leader,
                emotion=emotion,
                time=time_val,
                quality_label=quality_label,
                policy_version=self.maturity_policy.version,
                estimated_days_to_threshold=None,
                inflection_likelihood=0.0,
                evidence_refs=data.evidence_refs,
            ))

        # ── Build DailyMarketState ──
        # First, compute content_hash (state_id placeholder)
        state = DailyMarketState(
            state_id="",  # placeholder, filled after hash
            trade_date=trade_date,
            version=1,
            parent_state=data.parent_state,
            created_at=datetime.now(tz),
            policy_snapshot=policy_snapshot,
            subjects=data.subjects,
            cycle_nodes=data.cycle_nodes,
            divergence_qualities=tuple(dq_objects),
            maturity_estimates=tuple(nm_objects),
            content_hash="",
            evidence_refs=data.evidence_refs,
        )

        content_hash = state.compute_content_hash()
        state_id = f"st:{trade_date.isoformat()}:{content_hash[:16]}"

        # Return with proper state_id and content_hash
        return DailyMarketState(
            state_id=state_id,
            trade_date=trade_date,
            version=1,
            parent_state=data.parent_state,
            created_at=datetime.now(tz),
            policy_snapshot=policy_snapshot,
            subjects=data.subjects,
            cycle_nodes=data.cycle_nodes,
            divergence_qualities=tuple(dq_objects),
            maturity_estimates=tuple(nm_objects),
            content_hash=content_hash,
            evidence_refs=data.evidence_refs,
        )

    def build_minimal(
        self,
        trade_date: date,
        subjects: tuple[MarketSubject, ...],
        cycle_nodes: tuple[CycleNode, ...],
        parent_state: str | None = None,
    ) -> DailyMarketState:
        """Build a minimal DailyMarketState with default DQ/NM values.

        Used when real divergence/maturity data is not available.
        All zeros + default labels — the Policy derives the fallback correctly.
        """
        empty_dq: dict[str, tuple[float, float, float, float, float]] = {}
        empty_nm: dict[str, tuple[float, float, float, float, float]] = {}
        for node in cycle_nodes:
            if node.subject_id not in empty_dq:
                empty_dq[node.subject_id] = (0.5, 0.5, 0.5, 0.5, 0.5)
            if node.subject_id not in empty_nm:
                empty_nm[node.subject_id] = (node.maturity, 50.0, 50.0, 50.0, 50.0)

        return self.build(WorldStateInput(
            trade_date=trade_date,
            subjects=subjects,
            cycle_nodes=cycle_nodes,
            divergence_vectors=empty_dq,
            maturity_vectors=empty_nm,
            evidence_refs=(),
            parent_state=parent_state,
        ))

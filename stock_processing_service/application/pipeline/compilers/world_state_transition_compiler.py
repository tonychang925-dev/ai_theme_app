"""Phase B1 — WorldStateTransitionCompiler.

Deterministic. Policy-driven. No LLM.

Input:  prev_state + current_state + StateDiff + CycleFSM + CompilerPolicy
Output: Inference → Candidate → Eligibility → FrozenHypothesisSource

First version handles 3 key transitions:
  CLIMAX → FIRST_DIVERGENCE
  DIVERGENCE_WEAKENING → DIVERGENCE_REPAIR
  FIRST_DIVERGENCE → DIVERGENCE_REPAIR / FADE
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from stock_processing_service.contracts.market_cognition import (
    EvidenceRef,
    HypothesisState,
)
from stock_processing_service.contracts.market_cognition_phase_b import (
    INFERENCE_TRIGGER_TYPES,
    CompiledNodeTransitionHypothesis,
    WorldTransitionCandidate,
    WorldTransitionInference,
)
from stock_processing_service.contracts.market_cognition_v1_5 import (
    CYCLE_NODES,
    CycleNode,
    DailyMarketState,
    DivergenceQuality,
    NodeMaturity,
    StateDiff,
)
from stock_processing_service.domain.policies.cycle_fsm import CycleFSM


# ──────────────────────────────────────────────
#  CompilerPolicy
# ──────────────────────────────────────────────


@dataclass
class CompilerTransitionRule:
    name: str
    from_node: str
    to_node: str
    priority: int
    enabled: bool
    min_maturity: float
    min_transition_probability: float
    requires_divergence_signal: bool
    required_divergence_label: str
    expected_observations: tuple[str, ...]
    falsifiers: tuple[str, ...]


class CompilerPolicy:
    """Loaded from compiler_policy_v1.yaml."""

    def __init__(self, policy_path: str | Path) -> None:
        with open(policy_path) as fh:
            self.config: dict[str, Any] = yaml.safe_load(fh)
        self.version: str = self.config["version"]
        self.max_per_day: int = self.config["max_hypotheses_per_day"]
        self.min_per_day: int = self.config.get("min_hypotheses_per_day", 1)
        self.deadline_mode: str = self.config.get("deadline_mode", "next_trade_day")

        self.rules: list[CompilerTransitionRule] = []
        for t in self.config.get("transitions", []):
            if not t.get("enabled", True):
                continue
            self.rules.append(CompilerTransitionRule(
                name=t["name"],
                from_node=t["from_node"],
                to_node=t["to_node"],
                priority=t["priority"],
                enabled=t["enabled"],
                min_maturity=t.get("min_maturity", 0),
                min_transition_probability=t.get("min_transition_probability", 0.3),
                requires_divergence_signal=t.get("requires_divergence_signal", False),
                required_divergence_label=t.get("required_divergence_label", ""),
                expected_observations=tuple(t.get("expected_observations", [])),
                falsifiers=tuple(t.get("falsifiers", [])),
            ))
        self.rules.sort(key=lambda r: r.priority)


# ──────────────────────────────────────────────
#  TradeCalendar
# ──────────────────────────────────────────────


class TradeCalendar:
    """Minimal trade calendar for deadline computation.

    Phase B1: simple next-trade-day logic.
    Future: integrate with full TradeCalendarProducer.
    """

    @staticmethod
    def next_trade_day(trade_date: date) -> date:
        """Return the next trading day after trade_date.

        Simple version: skip Saturday(5) and Sunday(6).
        Full version should integrate holiday calendar.
        """
        next_day = trade_date + timedelta(days=1)
        while next_day.weekday() >= 5:  # skip weekends
            next_day += timedelta(days=1)
        return next_day


# ──────────────────────────────────────────────
#  WorldStateTransitionCompiler
# ──────────────────────────────────────────────


class WorldStateTransitionCompiler:
    """Deterministic compiler: World State → NODE_TRANSITION Hypotheses.

    Four-stage pipeline:
      Stage 1: Inference  — extract raw transition signals from StateDiff
      Stage 2: Candidate  — filter by CompilerPolicy rules
      Stage 3: Eligibility — check against ADR-M8-009 + ADR-M8-011
      Stage 4: Frozen     — wrap as FrozenHypothesisSource
    """

    def __init__(
        self,
        policy: CompilerPolicy,
        fsm: CycleFSM,
        calendar: TradeCalendar | None = None,
    ) -> None:
        self.policy = policy
        self.fsm = fsm
        self.calendar = calendar or TradeCalendar()

    # ── Public API ──

    def compile(
        self,
        current_state: DailyMarketState,
        previous_state: DailyMarketState | None,
        diff: StateDiff | None = None,
    ) -> tuple[CompiledNodeTransitionHypothesis, ...]:
        """Run full 4-stage compilation pipeline.

        Returns: eligible NODE_TRANSITION hypotheses (1-5 per day).
        """
        inferences = self._stage1_infer(current_state, previous_state, diff)
        candidates = self._stage2_filter(inferences, current_state)
        eligible = self._stage3_eligibility(candidates)
        frozen = self._stage4_freeze(eligible)
        return frozen

    # ── Stage 1: Inference ──

    def _stage1_infer(
        self,
        current: DailyMarketState,
        previous: DailyMarketState | None,
        diff: StateDiff | None,
    ) -> tuple[WorldTransitionInference, ...]:
        """Extract raw transition signals from StateDiff and CycleNodes.

        For each CycleNode in current_state, check:
        - Did the node change vs previous state? → node_transition
        - Did maturity cross a threshold? → maturity_threshold
        - Did divergence quality change? → divergence_signal
        """
        inferences: list[WorldTransitionInference] = []

        # Build previous-node lookup
        prev_nodes: dict[str, CycleNode] = {}
        if previous is not None:
            for n in previous.cycle_nodes:
                prev_nodes[n.subject_id] = n

        for node in current.cycle_nodes:
            prev_node = prev_nodes.get(node.subject_id)

            # ── node_transition: node changed ──
            if prev_node is not None and node.name != prev_node.name:
                inferences.append(WorldTransitionInference(
                    inference_id=_inference_id(current.trade_date, node.subject_id, "node_transition"),
                    subject_id=node.subject_id,
                    trade_date=current.trade_date,
                    from_node=prev_node.name,
                    to_node=node.name,
                    trigger_type="node_transition",
                    confidence=node.confidence,
                    urgency=_urgency(node.name),
                    source_diff=diff.to_state if diff else "",
                    source_cycle_node=node.node_id,
                ))

            # ── maturity_threshold: maturity >= 70 ──
            maturity = _find_maturity(current, node.subject_id)
            if maturity is not None and maturity.overall >= 70:
                for tc in node.transition_candidates:
                    if tc.probability >= self.policy.rules[0].min_transition_probability if self.policy.rules else 0.35:
                        inferences.append(WorldTransitionInference(
                            inference_id=_inference_id(current.trade_date, node.subject_id, "maturity_threshold"),
                            subject_id=node.subject_id,
                            trade_date=current.trade_date,
                            from_node=node.name,
                            to_node=tc.target_node,
                            trigger_type="maturity_threshold",
                            confidence=tc.probability,
                            urgency=_urgency(node.name),
                            source_diff=diff.to_state if diff else "",
                            source_cycle_node=node.node_id,
                        ))

            # ── divergence_signal: DQ label changed ──
            dq = _find_divergence_quality(current, node.subject_id)
            prev_dq = _find_divergence_quality(previous, node.subject_id) if previous else None
            if dq is not None and (prev_dq is None or dq.quality_label != prev_dq.quality_label):
                if dq.quality_label in ("healthy", "forced", "panic"):
                    # Determine most likely next node from TransitionCandidates
                    best_tc = _best_transition(node)
                    if best_tc is not None:
                        inferences.append(WorldTransitionInference(
                            inference_id=_inference_id(current.trade_date, node.subject_id, "divergence_signal"),
                            subject_id=node.subject_id,
                            trade_date=current.trade_date,
                            from_node=node.name,
                            to_node=best_tc.target_node,
                            trigger_type="divergence_signal",
                            confidence=min(best_tc.probability + 0.05, 0.95),
                            urgency=_urgency(node.name),
                            source_diff=diff.to_state if diff else "",
                            source_cycle_node=node.node_id,
                        ))

        return tuple(inferences)

    # ── Stage 2: Candidate Filter ──

    def _stage2_filter(
        self,
        inferences: tuple[WorldTransitionInference, ...],
        current: DailyMarketState,
    ) -> tuple[WorldTransitionCandidate, ...]:
        """Filter inferences through CompilerPolicy rules.

        For each inference, find the highest-priority matching rule.
        Only transitions matching an enabled rule become candidates.
        """
        candidates: list[WorldTransitionCandidate] = []

        for inf in inferences:
            for rule in self.policy.rules:
                if not self._rule_matches(rule, inf, current):
                    continue

                # Validate FSM transition legality
                if not self.fsm.is_valid_transition(inf.from_node, rule.to_node):
                    continue

                deadline = self.calendar.next_trade_day(current.trade_date)
                maturity = _find_maturity(current, inf.subject_id)
                prob = inf.confidence
                if maturity is not None and maturity.inflection_likelihood > 0:
                    prob = (prob + maturity.inflection_likelihood) / 2

                candidate = WorldTransitionCandidate(
                    candidate_id=_candidate_id(inf.inference_id, rule.name),
                    inference_id=inf.inference_id,
                    subject_id=inf.subject_id,
                    trade_date=current.trade_date,
                    statement=f"{inf.from_node} → {rule.to_node}",
                    current_node=inf.from_node,
                    expected_transition=rule.to_node,
                    prediction_probability=round(prob, 4),
                    source_quality_score=_compute_source_quality(current, inf.subject_id),
                    expected_observations=rule.expected_observations,
                    falsifiers=rule.falsifiers,
                    deadline=deadline,
                    compiler_policy_version=self.policy.version,
                )
                candidates.append(candidate)
                break  # first matching rule wins (priority-sorted)

        # Sort by priority (implied by rule order) then probability
        candidates.sort(key=lambda c: -c.prediction_probability)

        # Cap at max_per_day
        return tuple(candidates[:self.policy.max_per_day])

    # ── Stage 3: Eligibility Gate ──

    def _stage3_eligibility(
        self,
        candidates: tuple[WorldTransitionCandidate, ...],
    ) -> tuple[WorldTransitionCandidate, ...]:
        """Check each candidate against ADR-M8-009 + ADR-M8-011 Eligibility Gate.

        Requirements:
          - hypothesis_type == NODE_TRANSITION
          - statement non-empty
          - current_node / expected_transition non-empty
          - 0 <= prediction_probability <= 1
          - expected_observations non-empty
          - falsifiers non-empty
          - deadline > trade_date
          - source_quality_score > 0
        """
        eligible: list[WorldTransitionCandidate] = []

        for c in candidates:
            if not c.statement:
                continue
            if not c.current_node or not c.expected_transition:
                continue
            if not (0 <= c.prediction_probability <= 1):
                continue
            if not c.expected_observations or not c.falsifiers:
                continue
            if c.deadline <= c.trade_date:
                continue
            if c.source_quality_score <= 0:
                continue
            eligible.append(c)

        return tuple(eligible)

    # ── Stage 4: Freeze ──

    def _stage4_freeze(
        self,
        candidates: tuple[WorldTransitionCandidate, ...],
    ) -> tuple[CompiledNodeTransitionHypothesis, ...]:
        """Wrap eligible candidates as CompiledNodeTransitionHypothesis.

        The hypothesis_id is deterministic: hash of (trade_date + subject_id + statement).
        This ensures same input always produces same hypothesis_id.
        """
        frozen: list[CompiledNodeTransitionHypothesis] = []

        for c in candidates:
            hid_payload = f"{c.trade_date.isoformat()}:{c.subject_id}:{c.statement}"
            hid = hashlib.sha256(hid_payload.encode()).hexdigest()[:16]

            frozen.append(CompiledNodeTransitionHypothesis(
                hypothesis_type="NODE_TRANSITION",
                current_node=c.current_node,
                expected_transition=c.expected_transition,
                source_candidate_id=c.candidate_id,
                hypothesis_id=f"hyp:{c.trade_date.isoformat()}:{c.subject_id}:{hid}",
            ))

        return tuple(frozen)

    # ── Helpers ──

    def _rule_matches(
        self,
        rule: CompilerTransitionRule,
        inf: WorldTransitionInference,
        current: DailyMarketState,
    ) -> bool:
        """Check if an inference matches a compiler rule."""
        # Node match
        if rule.from_node != inf.from_node:
            return False
        if rule.to_node != inf.to_node:
            return False

        # Maturity threshold
        maturity = _find_maturity(current, inf.subject_id)
        if maturity is not None and maturity.overall < rule.min_maturity:
            return False

        # Probability threshold
        if inf.confidence < rule.min_transition_probability:
            return False

        # Divergence signal requirement
        if rule.requires_divergence_signal:
            dq = _find_divergence_quality(current, inf.subject_id)
            if dq is None:
                return False
            if rule.required_divergence_label and dq.quality_label != rule.required_divergence_label:
                return False

        return True


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────


def _inference_id(trade_date: date, subject_id: str, trigger: str) -> str:
    raw = f"{trade_date.isoformat()}:{subject_id}:{trigger}"
    return f"inf:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _candidate_id(inference_id: str, rule_name: str) -> str:
    raw = f"{inference_id}:{rule_name}"
    return f"cand:{hashlib.sha256(raw.encode()).hexdigest()[:12]}"


def _urgency(node_name: str) -> float:
    """Map node to urgency. CLIMAX > DIVERGENCE > FADE > others."""
    urgency_map = {
        "CLIMAX": 0.90,
        "FADE": 0.80,
        "FIRST_DIVERGENCE": 0.75,
        "SECOND_DIVERGENCE": 0.70,
        "DIVERGENCE_WEAKENING": 0.65,
        "ICE_POINT": 0.60,
        "DIVERGENCE_REPAIR": 0.50,
        "WEAK_TO_STRONG": 0.50,
        "REBOUND": 0.45,
        "ACCELERATION": 0.40,
        "FERMENTATION": 0.30,
        "INITIAL": 0.20,
        "CHAOS": 0.40,
    }
    return urgency_map.get(node_name, 0.30)


def _find_maturity(state: DailyMarketState | None, subject_id: str) -> NodeMaturity | None:
    if state is None:
        return None
    for m in state.maturity_estimates:
        if m.subject_id == subject_id:
            return m
    return None


def _find_divergence_quality(state: DailyMarketState | None, subject_id: str) -> DivergenceQuality | None:
    if state is None:
        return None
    for dq in state.divergence_qualities:
        if dq.subject_id == subject_id:
            return dq
    return None


def _best_transition(node: CycleNode) -> Any | None:
    """Return the TransitionCandidate with the highest probability."""
    if not node.transition_candidates:
        return None
    return max(node.transition_candidates, key=lambda tc: tc.probability)


def _compute_source_quality(state: DailyMarketState, subject_id: str) -> float:
    """Compute source quality from available data completeness.

    Simple heuristic: count how many data dimensions are present for this subject.
    """
    dims = 0
    total = 3  # maturity, divergence, cycle_node
    if _find_maturity(state, subject_id) is not None:
        dims += 1
    if _find_divergence_quality(state, subject_id) is not None:
        dims += 1
    for n in state.cycle_nodes:
        if n.subject_id == subject_id:
            dims += 1
            break
    return round(dims / total, 2)

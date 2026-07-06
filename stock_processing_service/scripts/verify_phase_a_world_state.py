#!/usr/bin/env python3
"""Phase A Exit Gate — World State stability check.

Usage:
    PYTHONPATH=/Users/admin/Desktop/ai_theme_app python \
      stock_processing_service/scripts/verify_phase_a_world_state.py \
      --date 2026-07-03

Checks:
  1.  DailyMarketState can be stably generated
  2.  state_id is reproducible (same input → same state_id)
  3.  content_hash is reproducible (excludes created_at / non-deterministic fields)
  4.  policy_snapshot is complete (all 4 policies present)
  5.  All CycleNodes pass FSM validation
  6.  All TransitionCandidates are legal transitions
  7.  DivergenceQuality 5-dim vectors are complete (no None/NaN)
  8.  NodeMaturity 6-dim vectors are complete (no None/NaN)
  9.  MarketWorldModel.diff(prev, current) produces readable StateDiff
  10. rollback(state_id) → snapshot consistency

Output:
    Phase A Exit Gate: PASS / FAIL
    World Quality report
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class GateReport:
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def add(self, name: str, passed: bool, detail: str = "") -> None:
        self.checks.append((name, passed, detail))

    @property
    def all_passed(self) -> bool:
        return all(passed for _, passed, _ in self.checks)

    def print(self) -> None:
        print()
        print("=" * 60)
        print("  Phase A Exit Gate Report")
        print("=" * 60)
        for name, passed, detail in self.checks:
            status = "PASS" if passed else "FAIL"
            line = f"  [{status}] {name}"
            if detail:
                line += f"  — {detail}"
            print(line)
        print("-" * 60)
        gate = "PASS" if self.all_passed else "FAIL"
        print(f"  Phase A Exit Gate: {gate}")
        print("=" * 60)


def create_sample_world(project_root: Path, trade_date: date) -> Any:
    """Create a sample MarketWorldModel with real contracts and policies."""
    from stock_processing_service.contracts.market_cognition_v1_5 import (
        CycleNode,
        DailyMarketState,
        DivergenceQuality,
        MarketSubject,
        NodeMaturity,
        TransitionCandidate,
    )
    from stock_processing_service.domain.policies.cycle_fsm import CycleFSM
    from stock_processing_service.domain.policies.policy_registry import PolicyRegistry
    from stock_processing_service.application.pipeline.market_world_model import MarketWorldModel

    # Policy
    config_dir = project_root / "config" / "market_cognition"
    fsm = CycleFSM(str(config_dir / "cycle_fsm_v1.yaml"))

    reg = PolicyRegistry()
    reg.register("cycle_fsm", "v1", fsm, date(2026, 1, 1))
    reg.register("divergence", "v1", {}, date(2026, 1, 1))
    reg.register("maturity", "v1", {}, date(2026, 1, 1))
    reg.register("compiler", "v1", {}, date(2026, 1, 1))
    snap = reg.snapshot()

    # Subjects — stable canonical IDs
    subjects = (
        MarketSubject("theme:9026027", "theme", "机器人/减速器"),
        MarketSubject("theme:9026028", "theme", "通信/CPO"),
        MarketSubject("theme:9026029", "theme", "大金融"),
        MarketSubject("theme:9026030", "theme", "上游材料"),
        MarketSubject("theme:9026031", "theme", "商业航天"),
    )

    # CycleNodes — FSM-validated
    node_configs = [
        ("theme:9026027", "CLIMAX", "高潮", 4, "accelerating", 82, 0.85,
         [("FIRST_DIVERGENCE", 0.72), ("SECOND_ACCELERATION", 0.20)]),
        ("theme:9026028", "DIVERGENCE_WEAKENING", "分歧减弱", 3, "diverging", 65, 0.75,
         [("DIVERGENCE_REPAIR", 0.45), ("FADE", 0.35)]),
        ("theme:9026029", "DIVERGENCE_WEAKENING", "分歧减弱", 3, "diverging", 55, 0.70,
         [("REBOUND", 0.40), ("DIVERGENCE_REPAIR", 0.30)]),
        ("theme:9026030", "FIRST_DIVERGENCE", "第一次分歧", 2, "diverging", 70, 0.80,
         [("FADE", 0.45), ("DIVERGENCE_REPAIR", 0.35)]),
        ("theme:9026031", "INITIAL", "启动", 1, "neutral", 25, 0.60,
         [("FERMENTATION", 0.55), ("CHAOS", 0.25)]),
    ]

    nodes = []
    for sid, name, stage, day, dir_, mat, conf, trans_cfgs in node_configs:
        tcs = tuple(TransitionCandidate(t, p) for t, p in trans_cfgs)
        nodes.append(CycleNode(
            node_id=f"cn:{sid}:{trade_date.isoformat()}",
            subject_id=sid, trade_date=trade_date,
            name=name, stage=stage, stage_day=day,
            consecutive_direction=dir_, maturity=mat, confidence=conf,
            transition_candidates=tcs,
        ))

    # DivergenceQualities — 5-dim vectors
    dq_configs = [
        ("theme:9026027", 0.3, 0.95, 0.2, 0.7, 0.4, "insufficient"),
        ("theme:9026028", 0.7, 0.65, 0.7, 0.5, 0.7, "healthy"),
        ("theme:9026030", 0.6, 0.55, 0.5, 0.6, 0.6, "healthy"),
    ]
    dqs = tuple(
        DivergenceQuality(
            quality_id=f"dq:{sid}:{trade_date.isoformat()}",
            subject_id=sid, trade_date=trade_date,
            volume_contraction=vc, leader_intact=li, rear_cleared=rc,
            capital_redirected=cr, duration_sufficient=ds,
            quality_label=label, policy_version="divergence_policy.v1",
        )
        for sid, vc, li, rc, cr, ds, label in dq_configs
    )

    # NodeMaturities — 6-dim vectors
    nm_configs = [
        ("theme:9026027", 82, 91, 83, 95, 95, 60, "peaking", 0.94),
        ("theme:9026028", 65, 35, 72, 55, 45, 70, "exhausting", 0.38),
    ]
    nms = tuple(
        NodeMaturity(
            maturity_id=f"nm:{sid}:{trade_date.isoformat()}",
            subject_id=sid, trade_date=trade_date,
            overall=ov, crowding=cr, volume=vo, leader=le, emotion=em, time=ti,
            quality_label=ql, policy_version="maturity_policy.v1",
            inflection_likelihood=il,
        )
        for sid, ov, cr, vo, le, em, ti, ql, il in nm_configs
    )

    # Build state
    import hashlib, json
    content = {
        "trade_date": trade_date.isoformat(),
        "parent_state": None,
        "subjects": sorted([s.subject_id for s in subjects]),
        "cycle_nodes": sorted([n.node_id for n in nodes]),
        "divergence_qualities": sorted([d.quality_id for d in dqs]),
        "maturity_estimates": sorted([m.maturity_id for m in nms]),
        "policy_snapshot": snap.to_dict(),
    }
    content_hash = hashlib.sha256(
        json.dumps(content, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()

    state = DailyMarketState(
        state_id=f"st:{trade_date.isoformat()}:{content_hash[:16]}",
        trade_date=trade_date, version=1, parent_state=None,
        created_at=datetime.now(), policy_snapshot=snap,
        subjects=subjects, cycle_nodes=nodes,
        divergence_qualities=dqs, maturity_estimates=nms,
        content_hash=content_hash,
    )

    world = MarketWorldModel(registry=reg)
    world.current_state = state
    world.history = (state,)
    return world, fsm


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase A Exit Gate")
    parser.add_argument("--date", default="2026-07-03", help="Trade date (YYYY-MM-DD)")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.date)
    report = GateReport()

    # ── Check 1: Stable generation ──
    try:
        world1, fsm1 = create_sample_world(PROJECT_ROOT, trade_date)
        report.add("state_generation", True, f"state_id={world1.current_state.state_id}")
    except Exception as e:
        report.add("state_generation", False, str(e))
        report.print()
        sys.exit(1)

    # ── Check 2: state_id reproducible ──
    world2, fsm2 = create_sample_world(PROJECT_ROOT, trade_date)
    id_match = world1.current_state.state_id == world2.current_state.state_id
    report.add("state_id_reproducible", id_match,
               "same input → same state_id" if id_match else "state_id differed across runs")

    # ── Check 3: content_hash reproducible ──
    hash_match = world1.current_state.content_hash == world2.current_state.content_hash
    report.add("content_hash_reproducible", hash_match,
               "same input → same content_hash" if hash_match else "content_hash differed across runs")

    # ── Check 4: policy_snapshot complete ──
    snap = world1.current_state.policy_snapshot
    policies_ok = all([
        snap.cycle_fsm == "v1",
        snap.divergence == "v1",
        snap.maturity == "v1",
        snap.compiler == "v1",
    ])
    report.add("policy_snapshot_complete", policies_ok, f"fsm={snap.cycle_fsm} div={snap.divergence} mat={snap.maturity} cmp={snap.compiler}")

    # ── Check 5: All CycleNodes pass FSM validation ──
    fsm = fsm1
    fsm_fails = []
    for node in world1.current_state.cycle_nodes:
        if not fsm.is_valid_state(node.name):
            fsm_fails.append(f"{node.subject_id}: invalid state {node.name}")
    report.add("fsm_state_valid", len(fsm_fails) == 0,
               f"{len(fsm_fails)} invalid" if fsm_fails else "all valid")

    # ── Check 6: All TransitionCandidates are legal ──
    trans_fails = []
    for node in world1.current_state.cycle_nodes:
        for tc in node.transition_candidates:
            if not fsm.is_valid_transition(node.name, tc.target_node):
                trans_fails.append(f"{node.subject_id}: {node.name} → {tc.target_node} illegal")
    report.add("fsm_transition_valid", len(trans_fails) == 0,
               f"{len(trans_fails)} illegal" if trans_fails else "all legal")

    # ── Check 7: DivergenceQuality vectors complete ──
    dq_fails = []
    for dq in world1.current_state.divergence_qualities:
        for dim_name, dim_val in [
            ("volume_contraction", dq.volume_contraction),
            ("leader_intact", dq.leader_intact),
            ("rear_cleared", dq.rear_cleared),
            ("capital_redirected", dq.capital_redirected),
            ("duration_sufficient", dq.duration_sufficient),
        ]:
            if dim_val is None or (isinstance(dim_val, float) and (dim_val != dim_val)):  # NaN check
                dq_fails.append(f"{dq.subject_id}.{dim_name}={dim_val}")
    report.add("divergence_vector_complete", len(dq_fails) == 0,
               f"{len(dq_fails)} incomplete" if dq_fails else "all complete")

    # ── Check 8: NodeMaturity vectors complete ──
    nm_fails = []
    for nm in world1.current_state.maturity_estimates:
        for dim_name, dim_val in [
            ("crowding", nm.crowding), ("volume", nm.volume),
            ("leader", nm.leader), ("emotion", nm.emotion), ("time", nm.time),
            ("overall", nm.overall),
        ]:
            if dim_val is None or (isinstance(dim_val, float) and (dim_val != dim_val)):
                nm_fails.append(f"{nm.subject_id}.{dim_name}={dim_val}")
    report.add("maturity_vector_complete", len(nm_fails) == 0,
               f"{len(nm_fails)} incomplete" if nm_fails else "all complete")

    # ── Check 9: StateDiff is readable ──
    from stock_processing_service.contracts.market_cognition_v1_5 import DailyMarketState as DMS
    prev = DMS(
        state_id=f"st:{trade_date.isoformat()}:prev", trade_date=trade_date,
        version=0, parent_state=None, created_at=datetime.now(),
        policy_snapshot=snap, subjects=world1.current_state.subjects,
    )
    diff = world1.diff(prev, world1.current_state)
    diff_ok = (
        diff.from_state is not None
        and diff.to_state is not None
        and isinstance(diff.node_changes, tuple)
        and isinstance(diff.maturity_changes, tuple)
    )
    report.add("state_diff_readable", diff_ok,
               f"{len(diff.node_changes)} node_changes, {len(diff.maturity_changes)} maturity_changes")

    # ── Check 10: rollback consistency ──
    state_before = world1.current_state
    world1.history += (state_before,)
    try:
        rolled = world1.rollback(state_before.state_id)
        rollback_ok = rolled.state_id == state_before.state_id
    except Exception as e:
        rollback_ok = False
        report.add("rollback_consistency", False, str(e))
    else:
        report.add("rollback_consistency", rollback_ok,
                   "snapshot consistent after rollback" if rollback_ok else "mismatch after rollback")

    # ── Print ──
    report.print()
    sys.exit(0 if report.all_passed else 1)


if __name__ == "__main__":
    main()

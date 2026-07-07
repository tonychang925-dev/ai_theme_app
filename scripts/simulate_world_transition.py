#!/usr/bin/env python3
"""Phase C — Simulation CLI.

Run a historical simulation over a date range and print summary + hypotheses + verdicts.

Usage:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app python3 scripts/simulate_world_transition.py --start 2026-07-01 --end 2026-07-03
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase C — Historical World State Simulation")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--output", "-o", default=None, help="Write JSON summary to file")
    parser.add_argument("--dataset", default="datasets/simulation", help="Dataset root for hypothesis store")
    args = parser.parse_args()

    start_date = date.fromisoformat(args.start)
    end_date = date.fromisoformat(args.end)

    sys.path.insert(0, str(PROJECT_ROOT))

    from stock_processing_service.application.pipeline.compilers.world_state_transition_compiler import (
        CompilerPolicy,
        WorldStateTransitionCompiler,
    )
    from stock_processing_service.application.pipeline.compilers.node_transition_hypothesis_store import (
        NodeTransitionHypothesisStore,
    )
    from stock_processing_service.application.pipeline.simulation import HistoricalSimulation
    from stock_processing_service.domain.policies.cycle_fsm import CycleFSM
    from stock_processing_service.domain.policies.policy_registry import PolicyRegistry
    from stock_processing_service.application.pipeline.market_world_model import MarketWorldModel

    # ── Bootstrap ──
    compiler_policy = CompilerPolicy(
        str(PROJECT_ROOT / "config" / "market_cognition" / "compiler_policy_v1.yaml")
    )
    fsm = CycleFSM(
        str(PROJECT_ROOT / "config" / "market_cognition" / "cycle_fsm_v1.yaml")
    )
    registry = PolicyRegistry()
    for name, ver in [
        ("cycle_fsm", "v1"),
        ("divergence", "v1"),
        ("maturity", "v1"),
        ("compiler", "v1"),
    ]:
        registry.register(name, ver, {}, date(2026, 1, 1))

    world = MarketWorldModel(registry=registry)
    compiler = WorldStateTransitionCompiler(compiler_policy, fsm)
    store = NodeTransitionHypothesisStore(
        PROJECT_ROOT / args.dataset / "node_transitions"
    )

    # ── Run ──
    print(f"Simulating {start_date} → {end_date} ...")
    sim = HistoricalSimulation(world, compiler, store)
    timeline = sim.simulate(start_date, end_date)

    # ── Summary ──
    sim_hash = timeline.compute_hash()
    manifest = store.read_manifest()

    confirmed = sum(1 for v in timeline.verdicts if v.is_confirmed())
    falsified = sum(1 for v in timeline.verdicts if v.is_falsified())
    pending = sum(1 for v in timeline.verdicts if v.is_pending())

    summary = {
        "simulation": {
            "start": args.start,
            "end": args.end,
            "hash": sim_hash,
            "days": len(timeline.days),
            "states": len(timeline.states),
            "hypotheses": len(timeline.hypotheses),
            "verdicts": {
                "total": len(timeline.verdicts),
                "confirmed": confirmed,
                "falsified": falsified,
                "pending": pending,
            },
        },
        "manifest": {
            "count": manifest.count if manifest else 0,
            "dataset_hash": manifest.dataset_hash if manifest else "",
            "manifest_hash": manifest.manifest_hash if manifest else "",
            "last_updated": manifest.last_updated if manifest else "",
        },
    }

    print(f"\n{'='*60}")
    print(f"Simulation Complete")
    print(f"{'='*60}")
    print(f"  Days:        {summary['simulation']['days']}")
    print(f"  States:      {summary['simulation']['states']}")
    print(f"  Hypotheses:  {summary['simulation']['hypotheses']}")
    print(f"  Verdicts:    {summary['simulation']['verdicts']['total']} "
          f"(C={confirmed} F={falsified} P={pending})")
    print(f"  Sim Hash:    {sim_hash[:24]}...")
    if manifest:
        print(f"  Manifest:    {manifest.count} records, dataset={manifest.dataset_hash[:16]}...")
    print(f"{'='*60}")

    # ── Detail ──
    print(f"\nTimeline:")
    for day in timeline.days:
        print(f"  {day.trade_date.isoformat()}")
        for h in day.hypotheses:
            subject = h.hypothesis_id.split(":")[2] if ":" in h.hypothesis_id else "?"
            print(f"    H: {h.current_node} → {h.expected_transition}  [{subject}]")
        for v in day.verdicts:
            print(f"    V: [{v.label:11s}] {v.expected_transition} → actual={v.actual_node:20s}  ({v.subject_id})")

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\nSummary written to {args.output}")


if __name__ == "__main__":
    main()

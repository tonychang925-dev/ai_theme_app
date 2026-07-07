#!/usr/bin/env python3
"""Aggregate batch replay results into dashboard, trends, and summary JSON files.

Usage:
  PYTHONPATH=. python3 scripts/aggregate_simulation_results.py --data datasets/white_paper
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any


def aggregate(data_dir: Path) -> dict[str, Any]:
    """Read batch output and produce aggregated results."""
    dashboard_path = data_dir / "dashboard.json"
    meta_path = data_dir / "simulation_meta.json"
    timeline_path = data_dir / "timeline_summary.json"

    if not dashboard_path.exists():
        print(f"ERROR: {dashboard_path} not found — run batch_replay_runner first", file=sys.stderr)
        sys.exit(1)

    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    timeline = json.loads(timeline_path.read_text(encoding="utf-8")) if timeline_path.exists() else {}

    # ── Summary ──
    levels = dashboard.get("levels", [])
    summary = {
        "generated_at": dashboard.get("generated_at", ""),
        "philosophy": dashboard.get("philosophy", ""),
        "executive_summary": {
            "date_range": f"{meta.get('start_date', '?')} → {meta.get('end_date', '?')}",
            "trading_days": meta.get("total_trading_days", 0),
            "states_built": meta.get("days_built", 0),
            "hypotheses_generated": meta.get("hypotheses_generated", 0),
            "verdicts_total": meta.get("verdicts_total", 0),
            "verdicts_confirmed": meta.get("verdicts_confirmed", 0),
            "verdicts_falsified": meta.get("verdicts_falsified", 0),
            "simulation_hash": meta.get("simulation_hash", "")[:16] + "..." if meta.get("simulation_hash") else "?",
            "validation_all_passed": meta.get("all_passed", False),
            "validation_levels": f"{meta.get('validation_levels_passed', 0)}/{meta.get('validation_levels_total', 0)}",
        },
        "layers": [
            {
                "level": lv["level"],
                "name": lv["name"],
                "question": lv.get("question", ""),
                "passed": lv["passed"],
                "n_metrics": len(lv["metrics"]),
                "metrics_passed": sum(1 for m in lv["metrics"] if m["passed"]),
            }
            for lv in levels
        ],
    }

    # ── Trends (time series from timeline) ──
    trends: dict[str, list[Any]] = {
        "dates": [],
        "hypotheses_per_day": [],
        "verdicts_per_day": [],
        "confirmed_per_day": [],
        "falsified_per_day": [],
    }

    for day_entry in timeline.get("days", []):
        trends["dates"].append(day_entry["trade_date"])
        trends["hypotheses_per_day"].append(len(day_entry.get("hypotheses", [])))
        verdicts = day_entry.get("verdicts", [])
        trends["verdicts_per_day"].append(len(verdicts))
        trends["confirmed_per_day"].append(sum(1 for v in verdicts if v["label"] == "CONFIRMED"))
        trends["falsified_per_day"].append(sum(1 for v in verdicts if v["label"] == "FALSIFIED"))

    # ── Market phase breakdown ──
    node_distribution: dict[str, int] = {}
    for day_entry in timeline.get("days", []):
        for h in day_entry.get("hypotheses", []):
            from_node = h.get("from", "?")
            node_distribution[from_node] = node_distribution.get(from_node, 0) + 1

    # ── Known issues ──
    known_issues = dashboard.get("known_issues", [])
    if not meta.get("verdicts_total", 0):
        known_issues.append("No verdicts generated — insufficient date range for compiler coverage")

    # ── Save ──
    output = {
        "summary": summary,
        "trends": trends,
        "node_distribution": node_distribution,
        "known_issues": known_issues,
        "errors": meta.get("errors", []),
    }

    # summary.json
    (data_dir / "summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # trends.json
    (data_dir / "trends.json").write_text(
        json.dumps(trends, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Aggregated results:")
    print(f"  summary.json: {len(json.dumps(summary))} bytes")
    print(f"  trends.json:  {len(trends['dates'])} data points")
    print(f"  layers: {summary['executive_summary']['validation_levels']}")
    print(f"  hypotheses: {summary['executive_summary']['hypotheses_generated']}")
    print(f"  verdicts: {summary['executive_summary']['verdicts_total']} "
          f"(C={summary['executive_summary']['verdicts_confirmed']} "
          f"F={summary['executive_summary']['verdicts_falsified']})")

    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate batch replay results")
    parser.add_argument("--data", required=True, help="Dataset directory from batch_replay_runner")
    args = parser.parse_args()
    aggregate(Path(args.data))


if __name__ == "__main__":
    main()

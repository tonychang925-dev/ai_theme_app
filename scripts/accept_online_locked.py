#!/usr/bin/env python3
"""Run ACCEPT online steps in one locked network execution.

Purpose:
- Execute ACCEPT Step A(record-decision) and Step C(post-fetch) in the same
  process/network channel to avoid channel downgrade between commands.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sync_pm_status import PMSStatusSyncManager


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--milestone-id", required=True)
    parser.add_argument("--decision", default="ACCEPT")
    parser.add_argument("--notes", default="")
    parser.add_argument("--post-fetch-output", required=True)
    parser.add_argument("--summary-output", required=True)
    args = parser.parse_args()

    mgr = PMSStatusSyncManager()
    summary: dict[str, Any] = {
        "run_id": args.run_id,
        "milestone_id": args.milestone_id,
        "decision": args.decision,
        "record_decision_rc": 1,
        "record_decision_error": None,
        "fetch_rc": 1,
        "fetch_error": None,
        "post_fetch_output": args.post_fetch_output,
    }

    notes = args.notes or f"phase0 autopilot run {args.run_id} accepted"

    # Step A: record decision
    try:
        mgr.record_decision(args.milestone_id, args.decision, notes)
        summary["record_decision_rc"] = 0
    except Exception as exc:
        summary["record_decision_error"] = str(exc)

    # Step C: post-accept fetch
    try:
        tasks = mgr.fetch_tasks_by_milestone(args.milestone_id)
        out = Path(args.post_fetch_output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"tasks": tasks}, ensure_ascii=False, indent=2), encoding="utf-8")
        summary["fetch_rc"] = 0
    except Exception as exc:
        summary["fetch_error"] = str(exc)

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

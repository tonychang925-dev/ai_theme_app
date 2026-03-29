#!/usr/bin/env python3
"""Finalize ACCEPT locally without network access.

This script only updates local run artifacts:
- tmp/runs/<run_id>/state.json
- tmp/runs/<run_id>/pending_sync.json
- tmp/runs/<run_id>/events.log
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def resolve_run_id(cli_run_id: str | None) -> str:
    if cli_run_id:
        return cli_run_id
    current = Path("tmp/current_run_id.txt")
    if not current.exists():
        raise FileNotFoundError("missing tmp/current_run_id.txt and --run-id not provided")
    return current.read_text(encoding="utf-8").strip()


def append_event(events_path: Path, level: str, event: str, detail: str) -> None:
    line = f"{utc_now()}|{level}|P1.phase0|-|{event}|success|{detail}\n"
    with events_path.open("a", encoding="utf-8") as f:
        f.write(line)


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize ACCEPT locally (no network)")
    parser.add_argument("--run-id", help="Run id. If omitted, read tmp/current_run_id.txt")
    parser.add_argument("--milestone-id", required=True, help="Milestone page id")
    parser.add_argument("--decision", default="ACCEPT", help="Decision value")
    parser.add_argument("--notes", default="", help="Decision notes")
    parser.add_argument(
        "--record-decision-rc",
        type=int,
        required=True,
        help="Exit code of sync_pm_status.py --record-decision (0=success, non-zero=failed)",
    )
    args = parser.parse_args()

    run_id = resolve_run_id(args.run_id)
    base = Path("tmp/runs") / run_id
    base.mkdir(parents=True, exist_ok=True)

    state_path = base / "state.json"
    pending_path = base / "pending_sync.json"
    events_path = base / "events.log"

    state = load_json(
        state_path,
        {
            "run_id": run_id,
            "mode": "autopilot",
            "phase": "P1.phase0",
            "current_step": "STEP 5.2",
            "current_task_id": None,
            "attempt": 0,
            "pending_sync": [],
            "gate_status": "waiting_acceptance",
            "updated_at": utc_now(),
        },
    )
    pending = load_json(pending_path, [])
    if not isinstance(pending, list):
        pending = []

    state["current_step"] = "COMPLETED"
    state["gate_status"] = "accepted"

    decision_key = f"{run_id}:record_decision:{args.decision}"
    now = utc_now()

    if args.record_decision_rc == 0:
        pending = [
            x
            for x in pending
            if not (isinstance(x, dict) and x.get("idempotency_key") == decision_key)
        ]
        append_event(events_path, "INFO", "decision_accept_sync_success", "notion_record_decision_ok")
    else:
        seen = {
            x.get("idempotency_key")
            for x in pending
            if isinstance(x, dict) and x.get("idempotency_key")
        }
        if decision_key not in seen:
            pending.append(
                {
                    "operation_type": "record_decision",
                    "target_id": args.milestone_id,
                    "payload_hash": "na",
                    "idempotency_key": decision_key,
                    "created_at": now,
                    "payload": {"decision": args.decision, "notes": args.notes},
                    "reason": "online_sync_failed",
                }
            )
        append_event(events_path, "INFO", "decision_accept_sync_queued", "notion_record_decision_failed")

    state["pending_sync"] = pending
    state["updated_at"] = now

    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    pending_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    append_event(events_path, "INFO", "decision_accept", f"user={args.decision}")

    print(
        json.dumps(
            {
                "run_id": run_id,
                "decision": args.decision,
                "record_decision_rc": args.record_decision_rc,
                "pending_sync_count": len(pending),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


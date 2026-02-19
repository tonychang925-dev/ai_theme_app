#!/usr/bin/env python3
"""Local-only ACCEPT closeout helper (no network, no subprocess online calls).

This script is intentionally restricted to local state updates.
Online commands MUST be executed at top-level by the orchestrator:
- .venv/bin/python sync_pm_status.py --record-decision ...
- .venv/bin/python sync_pm_status.py --fetch-tasks ...
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_run_id(cli_run_id: str | None) -> str:
    if cli_run_id:
        return cli_run_id
    p = Path("tmp/current_run_id.txt")
    if not p.exists():
        raise FileNotFoundError("missing tmp/current_run_id.txt and --run-id not provided")
    return p.read_text(encoding="utf-8").strip()


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def append_event(base: Path, level: str, event: str, detail: str) -> None:
    with (base / "events.log").open("a", encoding="utf-8") as f:
        f.write(f"{utc_now()}|{level}|P1.phase0|-|{event}|success|{detail}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local-only ACCEPT closeout helper")
    parser.add_argument("--run-id", help="Run id. If omitted, read tmp/current_run_id.txt")
    parser.add_argument("--milestone-id", required=True, help="Milestone page id")
    parser.add_argument("--decision", default="ACCEPT", help="Decision value")
    parser.add_argument("--notes", default="", help="Decision notes")
    parser.add_argument(
        "--record-decision-rc",
        type=int,
        required=True,
        help="Exit code from top-level sync_pm_status.py --record-decision",
    )
    parser.add_argument(
        "--fetch-rc",
        type=int,
        help="Optional exit code from top-level sync_pm_status.py --fetch-tasks",
    )
    args = parser.parse_args()

    repo = Path.cwd()
    run_id = resolve_run_id(args.run_id)
    run_base = repo / "tmp" / "runs" / run_id
    run_base.mkdir(parents=True, exist_ok=True)
    note = args.notes or f"phase0 autopilot run {run_id} accepted"
    pending_path = run_base / "pending_sync.json"
    state_path = run_base / "state.json"
    pending = load_json(pending_path, [])
    if not isinstance(pending, list):
        pending = []

    # B: local finalize for record_decision result
    decision_key = f"{run_id}:record_decision:{args.decision}"
    if args.record_decision_rc == 0:
        pending = [
            x
            for x in pending
            if not (isinstance(x, dict) and x.get("idempotency_key") == decision_key)
        ]
        append_event(run_base, "INFO", "decision_accept_sync_success", "notion_record_decision_ok")
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
                    "created_at": utc_now(),
                    "payload": {"decision": args.decision, "notes": note},
                    "reason": "online_sync_failed",
                }
            )
        append_event(run_base, "INFO", "decision_accept_sync_queued", "notion_record_decision_failed")

    # D: local reconcile for fetch_tasks result (if caller provides fetch rc)
    fetch_rc = args.fetch_rc
    if fetch_rc == 0:
        pending = [
            x
            for x in pending
            if not (
                isinstance(x, dict)
                and x.get("operation_type") == "fetch_tasks"
                and x.get("target_id") == args.milestone_id
            )
        ]
        append_event(run_base, "INFO", "pending_sync_replayed", "fetch_tasks")

    state = load_json(state_path, {})
    if isinstance(state, dict):
        state["current_step"] = "COMPLETED"
        state["gate_status"] = "accepted"
        state["pending_sync"] = pending
        state["updated_at"] = utc_now()
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    pending_path.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    append_event(run_base, "INFO", "decision_accept", f"user={args.decision}")
    print(
        json.dumps(
            {
                "run_id": run_id,
                "record_decision_rc": args.record_decision_rc,
                "fetch_rc": fetch_rc,
                "pending_sync_count": len(pending),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_backoff(raw: str) -> List[int]:
    return [int(x.strip()) for x in raw.split(",") if x.strip()]


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def log_event(events_log: Path, event: Dict[str, Any]) -> None:
    events_log.parent.mkdir(parents=True, exist_ok=True)
    with events_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def call_backend(run_dir: Path, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    script = Path(__file__).with_name("task_backend_local.py")
    cmd = [
        "python3",
        str(script),
        "--run-dir",
        str(run_dir),
        "--action",
        action,
        "--payload-json",
        json.dumps(payload, ensure_ascii=False),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads((p.stdout or "{}").strip())
    except json.JSONDecodeError:
        data = {"ok": False, "error": f"backend invalid json: {p.stdout}"}
    return data


def check_policy(cwd: Path, command: str) -> Dict[str, Any]:
    policy_script = Path(__file__).with_name("policy_check.sh")
    if not policy_script.exists():
        return {"decision": "allow", "reason": "policy script not found", "risk_level": "low"}
    p = subprocess.run(
        ["bash", str(policy_script), str(cwd), command],
        capture_output=True, text=True,
    )
    try:
        return json.loads((p.stdout or "{}").strip())
    except json.JSONDecodeError:
        return {"decision": "allow", "reason": "policy script error", "risk_level": "low"}


def run_command(command: str, cwd: Path, max_retries: int, backoff: List[int], events_log: Path, policy_enabled: bool = False) -> Dict[str, Any]:
    if policy_enabled:
        decision = check_policy(cwd, command)
        if decision.get("decision") == "deny":
            event = {
                "event": "policy_deny",
                "command": command,
                "reason": decision.get("reason", "policy deny"),
                "risk_level": decision.get("risk_level", "high"),
                "ts": now_iso(),
            }
            log_event(events_log, event)
            return {
                "ok": False,
                "attempt": 0,
                "returncode": -1,
                "stdout": "",
                "stderr": f"POLICY DENY: {decision.get('reason', 'blocked by policy')}",
                "duration_sec": 0,
                "blocked_by_policy": True,
            }
        if decision.get("decision") == "ask":
            log_event(events_log, {
                "event": "policy_ask",
                "command": command,
                "reason": decision.get("reason", "approval required"),
                "risk_level": decision.get("risk_level", "medium"),
                "ts": now_iso(),
            })
            # autopilot mode: log warning but proceed

    for attempt in range(1, max_retries + 1):
        started = time.time()
        p = subprocess.run(command, cwd=str(cwd), shell=True, capture_output=True, text=True)
        duration = round(time.time() - started, 3)
        event = {
            "event": "command_run",
            "command": command,
            "attempt": attempt,
            "returncode": p.returncode,
            "duration_sec": duration,
            "ts": now_iso(),
        }
        log_event(events_log, event)
        if p.returncode == 0:
            return {
                "ok": True,
                "attempt": attempt,
                "returncode": p.returncode,
                "stdout": p.stdout[-4000:],
                "stderr": p.stderr[-4000:],
                "duration_sec": duration,
            }
        if attempt < max_retries:
            delay = backoff[min(attempt - 1, len(backoff) - 1)] if backoff else 1
            time.sleep(delay)
    return {
        "ok": False,
        "attempt": max_retries,
        "returncode": p.returncode,  # noqa: F821
        "stdout": p.stdout[-4000:],  # noqa: F821
        "stderr": p.stderr[-4000:],  # noqa: F821
    }


def ensure_preflight(args: argparse.Namespace, run_dir: Path, state: Dict[str, Any], events_log: Path) -> None:
    required = [Path(args.contract), Path(args.plan)]
    for p in required:
        if not p.exists():
            raise FileNotFoundError(f"preflight missing: {p}")
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "checkpoints").mkdir(parents=True, exist_ok=True)
    write_json(run_dir / "pending_sync.json", read_json(run_dir / "pending_sync.json", {"items": []}))
    log_event(events_log, {"event": "preflight_ok", "phase": args.phase, "ts": now_iso()})
    state["current_step"] = "STEP 1"
    state["gate_status"] = "running"


def run_steps(args: argparse.Namespace, run_dir: Path, state: Dict[str, Any], events_log: Path) -> Dict[str, Any]:
    plan = read_json(Path(args.plan), {})
    steps = plan.get("steps", [])
    order_rank = {"ut": 1, "it": 2, "e2e": 3, "misc": 4}
    steps = sorted(steps, key=lambda s: order_rank.get(s.get("type", "misc"), 9))
    policy_enabled = getattr(args, "policy_enabled", False)

    results: List[Dict[str, Any]] = []
    for step in steps:
        sid = step.get("id", "S??")
        cmd = step.get("command", "")
        stype = step.get("type", "misc")
        state["current_step"] = "STEP 3"
        state["current_task_id"] = sid
        state["updated_at"] = now_iso()
        write_json(run_dir / "state.json", state)

        log_event(events_log, {"event": "step_start", "step_id": sid, "type": stype, "command": cmd, "ts": now_iso()})
        rc = run_command(cmd, Path(args.workdir), args.max_retries, parse_backoff(args.retry_backoff), events_log, policy_enabled=policy_enabled)
        rc["id"] = sid
        rc["type"] = stype
        rc["command"] = cmd
        results.append(rc)
        log_event(events_log, {"event": "step_end", "step_id": sid, "ok": rc["ok"], "ts": now_iso()})
        if not rc["ok"] and args.fail_fast:
            break

    summary = {
        "phase": args.phase,
        "total": len(results),
        "passed": sum(1 for x in results if x["ok"]),
        "failed": sum(1 for x in results if not x["ok"]),
        "results": results,
        "generated_at": now_iso(),
    }
    write_json(run_dir / "validation_summary.json", summary)
    return summary


def write_phase_report(args: argparse.Namespace, run_dir: Path, summary: Dict[str, Any]) -> Path:
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    report = reports_dir / f"phase-{args.phase}.md"
    lines = [
        f"# Phase Report: {args.phase}",
        "",
        f"- generated_at: {now_iso()}",
        f"- total: {summary['total']}",
        f"- passed: {summary['passed']}",
        f"- failed: {summary['failed']}",
        "",
        "## Command Results",
    ]
    for r in summary["results"]:
        lines.append(f"- `{r['id']}` `{r['type']}` `{r['command']}` -> {'PASS' if r['ok'] else 'FAIL'}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    call_backend(run_dir, "create_phase_report", {"report_file": str(report), "status": "Draft"})
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase-2 autopilot runner (local backend)")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--workdir", default=".")
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--mode", choices=["guarded", "autopilot"], default="autopilot")
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--retry-backoff", default="1,2,4,8,16")
    parser.add_argument("--stop-at", default="step6")
    parser.add_argument("--reports-dir", default="docs/project_control/reports")
    parser.add_argument("--fail-fast", action="store_true", default=True)
    parser.add_argument("--decision", choices=["ACCEPT", "REWORK"], default="REWORK")
    policy_default = os.environ.get("POLICY_ENABLED", "0") == "1"
    parser.add_argument("--policy-enabled", action="store_true", default=policy_default,
                        help="Enable policy checks before each command (env: POLICY_ENABLED=1)")
    args = parser.parse_args()

    run_dir = Path("tmp/runs") / args.run_id
    events_log = run_dir / "events.log"
    state_path = run_dir / "state.json"

    state = read_json(
        state_path,
        {
            "run_id": args.run_id,
            "mode": args.mode,
            "phase": args.phase,
            "current_step": "STEP 0",
            "current_task_id": None,
            "attempt": 1,
            "pending_sync": [],
            "gate_status": "init",
            "updated_at": now_iso(),
        },
    )

    try:
        ensure_preflight(args, run_dir, state, events_log)
    except Exception as e:
        state["gate_status"] = "blocked"
        state["error"] = str(e)
        state["updated_at"] = now_iso()
        write_json(state_path, state)
        log_event(events_log, {"event": "preflight_failed", "error": str(e), "ts": now_iso()})
        return 2

    summary = run_steps(args, run_dir, state, events_log)
    report = write_phase_report(args, run_dir, summary)

    gate_pass = summary["failed"] == 0
    decision = "ACCEPT" if gate_pass else args.decision
    gate = {
        "phase": args.phase,
        "run_id": args.run_id,
        "gate": "Passed" if gate_pass else "Failed",
        "decision": decision,
        "report_file": str(report),
        "updated_at": now_iso(),
    }
    write_json(run_dir / "gate_decision.json", gate)
    call_backend(run_dir, "record_acceptance_decision", {"decision": decision, "notes": "autopilot decision"})

    state["current_step"] = "STEP 6"
    state["gate_status"] = gate["gate"].lower()
    state["updated_at"] = now_iso()
    write_json(state_path, state)
    log_event(events_log, {"event": "run_completed", "gate": gate["gate"], "decision": decision, "ts": now_iso()})

    print(json.dumps(gate, ensure_ascii=False))
    return 0 if gate_pass else 3


if __name__ == "__main__":
    raise SystemExit(main())

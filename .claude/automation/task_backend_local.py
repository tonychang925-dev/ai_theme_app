#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def append_event(events_log: Path, event: Dict[str, Any]) -> None:
    ensure_parent(events_log)
    with events_log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def response(ok: bool, action: str, backend: str, data: Any = None, error: str | None = None) -> Dict[str, Any]:
    return {
        "ok": ok,
        "backend": backend,
        "action": action,
        "timestamp": now_iso(),
        "data": data if data is not None else {},
        "error": error,
    }


def handle_action(action: str, payload: Dict[str, Any], run_dir: Path) -> Dict[str, Any]:
    backend = "local"
    tasks_path = run_dir / "tasks_snapshot.json"
    state_path = run_dir / "state.json"
    events_log = run_dir / "events.log"
    pending_path = run_dir / "pending_sync.json"
    reports_path = run_dir / "reports.json"

    tasks = read_json(tasks_path, {"tasks": []})
    state = read_json(state_path, {})
    reports = read_json(reports_path, {"reports": []})
    pending = read_json(pending_path, {"items": []})

    if action == "fetch_tasks":
        return response(True, action, backend, tasks)

    if action == "update_task_status":
        task_id = payload.get("task_id")
        status = payload.get("status")
        if not task_id or not status:
            return response(False, action, backend, error="task_id/status required")
        found = False
        for task in tasks.get("tasks", []):
            if task.get("task_id") == task_id:
                task["status"] = status
                task["updated_at"] = now_iso()
                found = True
                break
        if not found:
            tasks.setdefault("tasks", []).append(
                {"task_id": task_id, "status": status, "updated_at": now_iso()}
            )
        write_json(tasks_path, tasks)
        append_event(events_log, {"event": "update_task_status", "task_id": task_id, "status": status, "ts": now_iso()})
        return response(True, action, backend, {"task_id": task_id, "status": status})

    if action == "append_test_evidence":
        task_id = payload.get("task_id")
        evidence = payload.get("evidence", {})
        if not task_id:
            return response(False, action, backend, error="task_id required")
        for task in tasks.get("tasks", []):
            if task.get("task_id") == task_id:
                task.setdefault("evidence", []).append(evidence)
                task["updated_at"] = now_iso()
                write_json(tasks_path, tasks)
                append_event(events_log, {"event": "append_test_evidence", "task_id": task_id, "ts": now_iso()})
                return response(True, action, backend, {"task_id": task_id})
        pending.setdefault("items", []).append({"action": action, "payload": payload, "ts": now_iso()})
        write_json(pending_path, pending)
        return response(True, action, backend, {"queued": True, "reason": "task not found"})

    if action == "update_milestone_progress":
        state["milestone_progress"] = payload.get("progress", "updated")
        state["updated_at"] = now_iso()
        write_json(state_path, state)
        append_event(events_log, {"event": "update_milestone_progress", "value": state["milestone_progress"], "ts": now_iso()})
        return response(True, action, backend, {"milestone_progress": state["milestone_progress"]})

    if action == "create_phase_report":
        report_file = payload.get("report_file")
        if not report_file:
            return response(False, action, backend, error="report_file required")
        reports.setdefault("reports", []).append(
            {"report_file": report_file, "status": payload.get("status", "Draft"), "created_at": now_iso()}
        )
        write_json(reports_path, reports)
        append_event(events_log, {"event": "create_phase_report", "report_file": report_file, "ts": now_iso()})
        return response(True, action, backend, {"report_file": report_file})

    if action == "record_acceptance_decision":
        state["acceptance_decision"] = {
            "decision": payload.get("decision", "REWORK"),
            "notes": payload.get("notes", ""),
            "at": now_iso(),
        }
        write_json(state_path, state)
        append_event(events_log, {"event": "record_acceptance_decision", "decision": state["acceptance_decision"]["decision"], "ts": now_iso()})
        return response(True, action, backend, state["acceptance_decision"])

    return response(False, action, backend, error=f"unsupported action: {action}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local task backend adapter")
    parser.add_argument("--run-dir", required=True, help="tmp/runs/<run_id> directory")
    parser.add_argument("--action", required=True, help="backend action")
    parser.add_argument("--payload-json", default="{}", help="JSON payload")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = json.loads(args.payload_json)
    out = handle_action(args.action, payload, run_dir)
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Autopilot preflight aggregator for dev-orchestrator.

Default mode (MUST): local-only aggregation.
- Does NOT invoke sync_pm_status.py internally.
- Reads top-level probe artifacts and writes machine-readable preflight.json.

Optional compatibility mode:
- `--online-probe` can be used to run legacy internal probes, but should be
  avoided in dev-orchestrator because it breaks the "single online entrypoint"
  rule.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_run_id(given: str | None) -> str:
    if given:
        return given
    run_id_file = Path("tmp/current_run_id.txt")
    if run_id_file.exists():
        rid = run_id_file.read_text(encoding="utf-8").strip()
        if rid:
            return rid
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _looks_fetch_failed(output: str) -> bool:
    low = output.lower()
    markers = [
        "获取活跃任务失败",
        "查询任务时发生错误",
        "nodename nor servname",
        "temporary failure in name resolution",
        "connection reset",
        "timed out",
        "timeout",
        "❌",
    ]
    return any(m in low or m in output for m in markers)


def _looks_transient_network_error(output: str) -> bool:
    low = output.lower()
    markers = [
        "nodename nor servname",
        "temporary failure in name resolution",
        "connection reset",
        "timed out",
        "timeout",
        "network is unreachable",
    ]
    return any(m in low for m in markers)


def _extract_json_from_output(output: str) -> dict[str, Any]:
    start = output.find("{")
    if start < 0:
        return {"ok": False, "error": f"unable to parse json from output: {output[:200]}"}
    raw = output[start:]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"invalid json output: {raw[:200]}"}


def _load_text(path: Path | None) -> str:
    if not path:
        return ""
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_verify_result(verify_json_path: Path | None, verify_log_path: Path | None) -> dict[str, Any]:
    if verify_json_path and verify_json_path.exists():
        try:
            return json.loads(verify_json_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"ok": False, "error": f"invalid verify_json: {exc}"}
    return _extract_json_from_output(_load_text(verify_log_path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run autopilot preflight checks.")
    parser.add_argument("--phase", required=True, help="Phase tag, e.g. P1.phase0")
    parser.add_argument("--run-id", help="Run id. If omitted, auto-resolve from tmp/current_run_id.txt or timestamp.")
    parser.add_argument("--task-prefix", help="Task prefix for connectivity probe. Defaults to --phase.")
    parser.add_argument("--status", default="Todo,Doing,In review", help="Status filter for fetch probe.")
    parser.add_argument("--python-bin", default=".venv/bin/python", help="Python executable for sync_pm_status.py")
    parser.add_argument("--output", help="Output preflight json path.")
    parser.add_argument("--tasks-output", help="Output path for fetched tasks snapshot.")
    parser.add_argument("--verify-json", help="JSON file from top-level --verify-token probe")
    parser.add_argument("--verify-log", help="stdout/stderr log file from top-level --verify-token probe")
    parser.add_argument("--fetch-log", help="stdout/stderr log file from top-level --fetch-tasks probe")
    parser.add_argument("--fetch-rc", type=int, help="Exit code of top-level --fetch-tasks probe")
    parser.add_argument("--verify-rc", type=int, help="Exit code of top-level --verify-token probe")
    parser.add_argument(
        "--online-probe",
        action="store_true",
        help="Compatibility mode: run internal sync_pm_status probes (not recommended).",
    )
    parser.add_argument(
        "--allow-offline",
        action="store_true",
        help="Allow network fetch failure (recorded) and still mark gate_ready=true.",
    )
    args = parser.parse_args()

    run_id = _resolve_run_id(args.run_id)
    out_dir = Path(f"tmp/runs/{run_id}")
    out_dir.mkdir(parents=True, exist_ok=True)
    tasks_output = Path(args.tasks_output or out_dir / "preflight_tasks.json")
    preflight_output = Path(args.output or out_dir / "preflight.json")
    task_prefix = args.task_prefix or args.phase

    verify_out = ""
    fetch_out = ""
    fetch_rc = args.fetch_rc if args.fetch_rc is not None else 1
    verify_rc = args.verify_rc if args.verify_rc is not None else 1

    if args.online_probe:
        # Compatibility mode only. Keep old behavior available but explicit.
        import subprocess  # local import to make local-only mode dependency-free

        def _run(cmd: list[str]) -> tuple[int, str]:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            out = (proc.stdout or "") + (proc.stderr or "")
            return proc.returncode, out.strip()

        verify_cmd = [args.python_bin, "sync_pm_status.py", "--verify-token"]
        verify_rc, verify_out = _run(verify_cmd)
        token_result = _extract_json_from_output(verify_out)

        fetch_cmd = [
            args.python_bin,
            "sync_pm_status.py",
            "--fetch-tasks",
            "--task-prefix",
            task_prefix,
            "--status",
            args.status,
            "--output",
            str(tasks_output),
        ]
        fetch_rc, fetch_out = _run(fetch_cmd)
    else:
        token_result = _load_verify_result(
            Path(args.verify_json) if args.verify_json else None,
            Path(args.verify_log) if args.verify_log else None,
        )
        verify_out = _load_text(Path(args.verify_log) if args.verify_log else None)
        fetch_out = _load_text(Path(args.fetch_log) if args.fetch_log else None)

        if args.fetch_rc is None:
            # In local mode, fetch_rc can be inferred from fetch output markers if not provided.
            fetch_rc = 0 if (tasks_output.exists() and not _looks_fetch_failed(fetch_out)) else 1
        if args.verify_rc is None:
            verify_rc = 0 if token_result.get("ok") else 1

    token_ok = bool(verify_rc == 0 and token_result.get("ok"))

    tasks_count = 0
    if fetch_rc == 0 and tasks_output.exists():
        try:
            tasks_count = len(json.loads(tasks_output.read_text(encoding="utf-8")).get("tasks", []))
        except Exception:
            tasks_count = 0

    fetch_failed_by_output = _looks_fetch_failed(fetch_out)
    network_ok = (fetch_rc == 0) and (not fetch_failed_by_output)
    # 容错：若 verify-token 因瞬时网络/DNS问题失败，但 fetch-tasks 已成功，
    # 说明 token 与连通性在执行路径上可用，允许继续。
    token_error = str(token_result.get("error") or "")
    invalid_token = "API token is invalid" in token_error
    effective_token_ok = token_ok or (network_ok and not invalid_token)

    transient_network_error = _looks_transient_network_error(fetch_out) or _looks_transient_network_error(token_error)
    require_network_escalation_once = transient_network_error and (not args.allow_offline) and (not invalid_token)
    gate_ready = effective_token_ok and (network_ok or args.allow_offline)
    blocking_issues: list[str] = []
    if not effective_token_ok:
        blocking_issues.append("token_verify_failed")
    if not network_ok and not args.allow_offline:
        blocking_issues.append("network_fetch_failed")
    if require_network_escalation_once:
        blocking_issues.append("request_network_escalation_once")

    preflight = {
        "run_id": run_id,
        "phase": args.phase,
        "mode": "autopilot",
        "generated_at": _now_iso(),
        "checks": {
            "token_verify": {
                "ok": effective_token_ok,
                "token_fingerprint": token_result.get("token_fingerprint"),
                "user_type": token_result.get("user_type"),
                "name": token_result.get("name"),
                "error": token_result.get("error"),
                "note": None if token_ok else ("fallback_by_fetch_success" if effective_token_ok else None),
            },
            "network_fetch_tasks": {
                "ok": network_ok,
                "task_prefix": task_prefix,
                "status_filter": args.status,
                "tasks_count": tasks_count,
                "output": str(tasks_output),
                "error": None if network_ok else fetch_out[:500],
                "failed_by_output": fetch_failed_by_output,
            },
        },
        "gate_ready": gate_ready,
        "transient_network_error": transient_network_error,
        "require_network_escalation_once": require_network_escalation_once,
        "next_action": "request_network_escalation_once" if require_network_escalation_once else "continue",
        "blocking_issues": blocking_issues,
        "allow_offline": args.allow_offline,
        "mode_note": "online_probe" if args.online_probe else "local_aggregate",
    }
    preflight_output.write_text(json.dumps(preflight, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"output": str(preflight_output), "gate_ready": gate_ready}, ensure_ascii=False))
    return 0 if gate_ready else 1


if __name__ == "__main__":
    sys.exit(main())

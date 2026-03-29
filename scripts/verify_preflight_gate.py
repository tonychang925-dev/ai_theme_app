#!/usr/bin/env python3
"""Hard gate for autopilot preflight.

This gate enforces:
1) preflight gate_ready must be true;
2) if preflight requests one-time network escalation, run must be channel-locked;
3) escalation probe evidence must exist before STEP 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preflight-json", required=True)
    parser.add_argument("--state-json", required=True)
    parser.add_argument("--events-log", required=True)
    args = parser.parse_args()

    errors: list[str] = []
    preflight = load_json(Path(args.preflight_json))
    state = load_json(Path(args.state_json))
    events_path = Path(args.events_log)
    events_text = events_path.read_text(encoding="utf-8", errors="ignore") if events_path.exists() else ""

    if not bool(preflight.get("gate_ready")):
        errors.append("preflight gate_ready=false; must not enter STEP 2")

    need_escalation = bool(preflight.get("require_network_escalation_once"))
    if need_escalation:
        channel = str(state.get("network_channel") or "")
        if channel != "escalated_locked":
            errors.append(
                "preflight required escalation but state.network_channel is not escalated_locked"
            )
        if "preflight_escalation_probe" not in events_text:
            errors.append("missing preflight_escalation_probe event evidence in events.log")

    if errors:
        print("❌ preflight hard gate failed")
        for err in errors:
            print(f"- {err}")
        return 1

    print("✅ preflight hard gate passed")
    print(f"- gate_ready: {preflight.get('gate_ready')}")
    print(f"- require_network_escalation_once: {need_escalation}")
    print(f"- network_channel: {state.get('network_channel')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

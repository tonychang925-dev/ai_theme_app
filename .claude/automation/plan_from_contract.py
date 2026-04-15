#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List


HEADING_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$")


def extract_required_commands(md_text: str) -> List[str]:
    lines = md_text.splitlines()
    in_section = False
    commands: List[str] = []
    for raw in lines:
        line = raw.rstrip()
        m = HEADING_RE.match(line)
        if m:
            heading = m.group(1).strip().lower()
            if heading.startswith("4. required commands") or heading == "required commands":
                in_section = True
                continue
            if in_section:
                break
        if not in_section:
            continue
        striped = line.strip()
        if striped.startswith("- "):
            cmd = striped[2:].strip()
            if cmd:
                commands.append(cmd)
    return commands


def classify(cmd: str) -> str:
    c = cmd.lower()
    if "pytest" in c and ("integration" in c or "it" in c):
        return "it"
    if "pytest" in c:
        return "ut"
    if "e2e" in c or "playwright" in c or "cypress" in c:
        return "e2e"
    return "misc"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build execution plan from PHASE_CONTRACT markdown")
    parser.add_argument("--contract", required=True)
    parser.add_argument("--phase", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    contract = Path(args.contract)
    output = Path(args.output)
    md = contract.read_text(encoding="utf-8")
    cmds = extract_required_commands(md)

    steps = []
    for i, cmd in enumerate(cmds, start=1):
        steps.append(
            {
                "id": f"S{i:02d}",
                "type": classify(cmd),
                "command": cmd,
                "required": True,
            }
        )

    plan = {
        "phase": args.phase,
        "contract": str(contract),
        "steps": steps,
        "rules": {
            "order": ["ut", "it", "e2e", "misc"],
            "fail_fast": True,
            "retryable": True,
        },
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

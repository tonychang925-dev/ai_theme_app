#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path


RISKY_PREFIXES = (
    "theme_data_complete/",
    "tmp/",
    ".claude-dev/",
)

SAFE_DOC_PREFIXES = (
    "docs/project_control/",
    "docs/architecture/",
)


@dataclass
class ChangeItem:
    status: str
    path: str
    risk_level: str
    reason: str


def _git_status_short() -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.rstrip("\n") for line in proc.stdout.splitlines() if line.strip()]


def _classify(status_line: str) -> ChangeItem:
    status = status_line[:2].strip() or "??"
    path = status_line[3:].strip()
    if " -> " in path:
        path = path.split(" -> ", 1)[1].strip()

    if path.endswith((".md", ".json")) and path.startswith("tmp/"):
        return ChangeItem(status=status, path=path, risk_level="low", reason="local_control_artifact")
    if path.startswith(RISKY_PREFIXES):
        return ChangeItem(status=status, path=path, risk_level="high", reason="runtime_or_generated_artifact")
    if path.startswith(SAFE_DOC_PREFIXES):
        return ChangeItem(status=status, path=path, risk_level="low", reason="documentation_change")
    if path.startswith("stock_processing_service/") or path.startswith("database_service/") or path.startswith("frontend_bff/"):
        return ChangeItem(status=status, path=path, risk_level="medium", reason="core_service_change")
    return ChangeItem(status=status, path=path, risk_level="medium", reason="uncategorized")


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 D1 workspace guard report")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return non-zero when high-risk changes exist",
    )
    parser.add_argument(
        "--output",
        default="tmp/p3_d1_workspace_guard_report.json",
        help="report output path",
    )
    args = parser.parse_args()

    lines = _git_status_short()
    changes = [_classify(line) for line in lines]

    high = [c for c in changes if c.risk_level == "high"]
    medium = [c for c in changes if c.risk_level == "medium"]
    low = [c for c in changes if c.risk_level == "low"]

    report = {
        "phase": "P3",
        "task": "P3.phase0-T01",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": {
            "total_changes": len(changes),
            "high_risk": len(high),
            "medium_risk": len(medium),
            "low_risk": len(low),
            "strict_block": len(high) > 0,
        },
        "changes": [asdict(c) for c in changes],
        "risky_prefixes": list(RISKY_PREFIXES),
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[P3-D1] total={len(changes)} high={len(high)} medium={len(medium)} low={len(low)}")
    print(f"[P3-D1] report={output_path}")

    if args.strict and high:
        print("[P3-D1] strict mode blocked: high-risk changes present", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

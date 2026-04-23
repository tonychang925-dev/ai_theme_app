#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "tmp" / "p3_pointer_atomicity_report.json"


def _validate_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 snapshot current pointer atomicity checker")
    parser.add_argument("--trade-date", required=True, type=_validate_date, help="trade date (YYYY-MM-DD)")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="json report path")
    parser.add_argument("--strict", action="store_true", help="reserve strict gate mode")
    args = parser.parse_args()

    report = {
        "task": "P3.phase1-T08",
        "trade_date": args.trade_date,
        "status": "skeleton_ready",
        "checks": [
            "pointer_key_exists",
            "pointer_version_points_to_existing_snapshot",
            "rollback_target_available",
        ],
        "strict_mode": args.strict,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[pointer] trade_date={args.trade_date} status=skeleton_ready")
    print(f"[pointer] report={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


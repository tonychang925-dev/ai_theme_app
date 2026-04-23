#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTER = ROOT / "docs" / "project_control" / "FEATURE_FLAG_REGISTER_P3.md"
DEFAULT_OUTPUT = ROOT / "tmp" / "p3_flag_register_report.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 feature flag register checker")
    parser.add_argument("--register-path", default=str(DEFAULT_REGISTER), help="flag register markdown path")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="json report path")
    parser.add_argument("--strict", action="store_true", help="exit non-zero when register missing")
    args = parser.parse_args()

    register_path = Path(args.register_path)
    exists = register_path.exists()
    report = {
        "task": "P3.phase1-T11",
        "register_path": str(register_path),
        "exists": exists,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[flag-register] exists={exists} path={register_path}")
    print(f"[flag-register] report={output}")
    if args.strict and not exists:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


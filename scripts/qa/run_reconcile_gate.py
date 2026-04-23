#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "tmp" / "reconcile"


def _validate_date(value: str) -> str:
    date.fromisoformat(value)
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 reconcile gate runner")
    parser.add_argument("--trade-date", required=True, type=_validate_date, help="trade date (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="output directory")
    parser.add_argument("--strict", action="store_true", help="reserve strict gate mode")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    summary_path = output_dir / f"summary_{args.trade_date}.json"
    diff_path = output_dir / f"diff_samples_{args.trade_date}.jsonl"

    summary = {
        "task": "P3.phase1-T10",
        "trade_date": args.trade_date,
        "status": "skeleton_ready",
        "metrics": {
            "total_rows_old": 0,
            "total_rows_new": 0,
            "diff_ratio": 0.0,
        },
        "strict_mode": args.strict,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    diff_path.write_text("", encoding="utf-8")

    print(f"[reconcile] trade_date={args.trade_date} status=skeleton_ready")
    print(f"[reconcile] summary={summary_path}")
    print(f"[reconcile] diff_samples={diff_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


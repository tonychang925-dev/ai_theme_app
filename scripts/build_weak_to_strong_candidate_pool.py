#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weak-to-strong candidate pool.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument("--next-trade-date", default="", help="Optional next trade date in YYYY-MM-DD")
    parser.add_argument("--max-candidates", type=int, default=10, help="Max candidates to persist (hard cap 10)")
    parser.add_argument("--output", default="", help="Optional output JSON file")
    parser.add_argument("--skip-legacy-entrypoint-gate", action="store_true", help="Skip legacy cycle entrypoint gate (for temporary diagnostics only)")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict:
    trade_date = datetime.strptime(args.trade_date, "%Y-%m-%d").date()
    next_trade_date = (
        datetime.strptime(args.next_trade_date, "%Y-%m-%d").date() if args.next_trade_date else None
    )

    builder = WeakToStrongCandidateBuilder()
    try:
        result = await builder.build(
            trade_date,
            next_trade_date=next_trade_date,
            max_candidates=max(int(args.max_candidates), 1),
        )
    finally:
        await builder.close()

    payload = {
        "trade_date": result.trade_date.isoformat(),
        "next_trade_date": result.next_trade_date.isoformat(),
        "total_scanned": result.total_scanned,
        "total_inserted": result.total_inserted,
        "sample": [
            {
                "stock_id": c["stock_id"],
                "stock_name": c["stock_name"],
                "pool_entry_type": c.get("pool_entry_type", ""),
                "candidate_score": c["candidate_score"],
                "weak_type": c["weak_type"],
                "subject_key": c.get("subject_key", ""),
                "theme_name": c.get("theme_name", ""),
            }
            for c in result.candidates[:20]
        ],
    }
    return payload


def main() -> int:
    args = parse_args()
    if not args.skip_legacy_entrypoint_gate:
        gate_cmd = [
            sys.executable,
            str(PROJECT_ROOT / "stock_service" / "scripts" / "check_legacy_cycle_entrypoints.py"),
        ]
        subprocess.run(gate_cmd, cwd=str(PROJECT_ROOT), check=True)
    else:
        print("[SKIP] legacy_cycle_entrypoint_gate (--skip-legacy-entrypoint-gate enabled)")
    payload = asyncio.run(_run(args))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

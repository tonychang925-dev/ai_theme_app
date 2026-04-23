#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.services.weak_to_strong_auction_service import WeakToStrongAuctionService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run weak-to-strong auction confirmation.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument("--output", default="", help="Optional output JSON path")
    parser.add_argument("--replay-candidate-id", type=int, default=0, help="Optional replay by candidate_id")
    parser.add_argument("--skip-legacy-entrypoint-gate", action="store_true", help="Skip legacy cycle entrypoint gate (for temporary diagnostics only)")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict:
    trade_date = datetime.strptime(args.trade_date, "%Y-%m-%d").date()
    service = WeakToStrongAuctionService()
    try:
        result = await service.confirm(trade_date)
        payload = {
            "trade_date": result.trade_date.isoformat(),
            "total_candidates": result.total_candidates,
            "persisted_count": result.persisted_count,
            "level_count": result.level_count,
        }
        if args.replay_candidate_id > 0:
            payload["replay"] = await service.get_replay_by_candidate_id(args.replay_candidate_id)
        return payload
    finally:
        await service.close()


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

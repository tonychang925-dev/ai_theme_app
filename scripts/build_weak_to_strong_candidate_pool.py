#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weak-to-strong candidate pool.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument("--next-trade-date", default="", help="Optional next trade date in YYYY-MM-DD")
    parser.add_argument("--max-candidates", type=int, default=120, help="Max candidates to persist")
    parser.add_argument("--output", default="", help="Optional output JSON file")
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> dict:
    trade_date = datetime.strptime(args.trade_date, "%Y-%m-%d").date()
    next_trade_date = (
        datetime.strptime(args.next_trade_date, "%Y-%m-%d").date() if args.next_trade_date else None
    )

    builder = EnhancedCandidateBuilder()
    try:
        result = await builder.build_enhanced(
            trade_date,
            max_formal=max(int(args.max_candidates), 1),
            max_observe=max(int(args.max_candidates) // 2, 5),
        )
        # 注意：build_enhanced返回的result有不同的结构
        # 我们需要适配现有的输出格式
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
                "candidate_type": c["candidate_type"],
                "candidate_score": c["candidate_score"],
                "weak_type": c["weak_type"],
            }
            for c in result.candidates[:20]
        ],
    }
    return payload


def main() -> int:
    args = parse_args()
    payload = asyncio.run(_run(args))
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.services.theme_cycle_judgement_service import ThemeCycleJudgementService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="构建指定交易日 theme_cycle_judgement_v2（含证据层）")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--top-k", type=int, default=20, help="输出前K条预览")
    return parser


async def main_async() -> int:
    args = build_parser().parse_args()
    trade_date = datetime.strptime(args.trade_date, "%Y-%m-%d").date()

    # 说明：该服务名为 legacy，但当前仍是仓内唯一稳定的“证据层+v2裁决”构建入口。
    # 这里显式允许，仅用于盘后主链前置构建，不做旧表回写。
    service = ThemeCycleJudgementService(allow_legacy=True)
    try:
        judgements = await service.judge_all_themes_for_date(trade_date)
    finally:
        await service.close()

    print(f"[OK] trade_date={args.trade_date}")
    print(f"[OK] v2_rows={len(judgements)}")
    for item in judgements[: max(0, args.top_k)]:
        print(
            f"[ROW] subject_key={item.get('subject_key')} "
            f"cycle={item.get('final_cycle_state')} "
            f"alive={item.get('final_mainline_alive')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))

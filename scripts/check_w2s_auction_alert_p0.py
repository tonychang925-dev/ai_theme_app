"""P1-I-1 P0 验证: W2S 竞价弱转强确认告警。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_w2s_auction_alert_p0.py --candidate-date 2026-05-25 [--dry-run]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.w2s_alert_service import W2SAlertService
from stock_processing_service.sinks.w2s_alert_redis_pusher import W2SAlertRedisPusher

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    import argparse
    p = argparse.ArgumentParser(description="P1-I-1 W2S Auction Alert P0")
    p.add_argument("--candidate-date", default="2026-05-25", help="D1候选日期 YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    service = W2SAlertService(DSN)
    result = await service.build_alerts(args.candidate_date)

    print(f"Candidates: {result.total_candidates}")
    print(f"Level A: {result.level_a_count}  B: {result.level_b_count}  C: {result.level_c_count}  X: {result.level_x_count}")
    print(f"Alerts (A+B): {len(result.alerts)}  Observes (C): {len(result.observes)}")

    for a in result.alerts[:5]:
        print(f"\n  [{a.confirm_level}] {a.stock_id} {a.stock_name} score={a.confirm_score}")
        print(f"  type={a.candidate_type} weak={a.weak_type} theme={a.theme_name}")
        print(f"  open={a.auction_open_pct}% carry={a.carry_ratio} stability={a.price_path_stability_score}")
        print(f"  evidence={a.evidence_rules[:5]} reject={a.reject_reason_code} source={a.source}")

    if args.dry_run:
        print(f"\n[dry-run] 未推送 Redis ({len(result.alerts)} alerts + {len(result.observes)} observes)")
    else:
        pusher = W2SAlertRedisPusher()
        total_pushed = 0
        if result.alerts:
            total_pushed += await pusher.push_alerts(result.alerts)
        if result.observes:
            total_pushed += await pusher.push_alerts(result.observes)
        print(f"\n✅ Pushed {total_pushed} to stream:w2s:alerts ({len(result.alerts)} alerts + {len(result.observes)} observes)")
        await pusher.close()

    await service.close()
    print(f"\n{'✅' if result.total_candidates > 0 else '⚠️ '} P1-I-1a P0 done")


if __name__ == "__main__":
    asyncio.run(main())

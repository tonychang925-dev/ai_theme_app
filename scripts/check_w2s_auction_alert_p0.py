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
    print(f"Level A: {result.level_a_count}  B: {result.level_b_count}  C: {result.level_c_count}")
    print(f"Alerts (A+B): {len(result.alerts)}")

    for a in result.alerts[:10]:
        print(f"\n  {a.stock_id} {a.stock_name} [{a.confirm_level}] score={a.confirm_score}")
        print(f"  type={a.candidate_type} weak={a.weak_type} theme={a.theme_name}")
        print(f"  open={a.auction_open_pct}% carry={a.carry_ratio} stability={a.price_path_stability_score} last_min={a.last_minute_ratio}")
        print(f"  shapes={a.shape_features}")

    if args.dry_run:
        print("\n[dry-run] 未推送 Redis")
    elif result.alerts:
        pusher = W2SAlertRedisPusher()
        pushed = await pusher.push_alerts(result.alerts)
        print(f"\n✅ Pushed {pushed}/{len(result.alerts)} to stream:w2s:alerts")
        await pusher.close()
    else:
        print("\n⚠️  无 A/B 级告警（竞价数据可能缺失）")

    await service.close()
    print(f"\n{'✅' if result.alerts else '⚠️ '} P1-I-1 P0 done")


if __name__ == "__main__":
    asyncio.run(main())

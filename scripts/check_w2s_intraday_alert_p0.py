"""P1-I-4 P0 验证: 盘中弱转强买点观察告警。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_w2s_intraday_alert_p0.py --trade-date 2026-05-26 [--dry-run] [--limit 10]
"""
from __future__ import annotations

import asyncio, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.w2s_intraday_alert_service import W2SIntradayAlertService
from stock_processing_service.sinks.w2s_alert_redis_pusher import W2SAlertRedisPusher

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    import argparse
    p = argparse.ArgumentParser(description="P1-I-4 W2S Intraday Alert P0")
    p.add_argument("--trade-date", default="2026-05-26")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    svc = W2SIntradayAlertService(DSN)
    result = await svc.build_alerts(args.trade_date)

    print(f"Candidates: {result.total_candidates}  With state: {result.checked_with_state}")
    print(f"A: {result.level_a}  B: {result.level_b}  C: {result.level_c}  Total alerts: {len(result.alerts)}")

    for a in result.alerts[:10]:
        print(f"\n  [{a.alert_level}] {a.stock_id} {a.stock_name} score={a.intraday_score}")
        print(f"    D2={a.confirm_level}/{a.confirm_score} type={a.candidate_type}")
        print(f"    vwap={a.vwap} above_5m={a.above_vwap_ratio_5m} rel={a.relative_strength_vs_index} turn={a.relative_strength_turn_positive}")
        print(f"    break_plat={a.break_platform_30m} plat_hi={a.platform_high_30m} amt_accel={a.amount_acceleration}")
        print(f"    support={a.support_state} pos={a.position_label} patterns={a.pattern_labels[:3]}")
        print(f"    evidence={a.evidence_rules}")

    if args.dry_run:
        print(f"\n[dry-run] 未推送 ({len(result.alerts)} alerts)")
    elif result.alerts:
        pusher = W2SAlertRedisPusher()
        pushed = await pusher.push_intraday_alerts(result.alerts)
        print(f"\n✅ Pushed {pushed}/{len(result.alerts)} to stream:w2s:alerts")
        await pusher.close()
    else:
        print("\n⚠️  无盘中弱转强观察告警")

    await svc.close()
    print(f"\n{'✅' if result.total_candidates > 0 else '⚠️'} P1-I-4 P0 done")


if __name__ == "__main__":
    asyncio.run(main())

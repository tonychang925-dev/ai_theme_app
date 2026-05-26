"""P1-I-2 P0 验证: 弱转强支撑承接观察告警。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_w2s_support_alert_p0.py --candidate-date 2026-05-25 [--dry-run]
"""
from __future__ import annotations

import asyncio, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.w2s_support_alert_service import W2SSupportAlertService
from stock_processing_service.sinks.w2s_alert_redis_pusher import W2SAlertRedisPusher

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    import argparse
    p = argparse.ArgumentParser(description="P1-I-2 W2S Support Alert P0")
    p.add_argument("--candidate-date", default="2026-05-22")
    p.add_argument("--confirm-date", default=None)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    confirm_date = args.confirm_date or args.candidate_date
    svc = W2SSupportAlertService(DSN)
    result = await svc.build_alerts(args.candidate_date, confirm_date)

    print(f"Candidates: {result.total_candidates}  Confirmed: {result.confirmed_count}  With quotes: {result.with_quotes}")
    print(f"Alerts: {len(result.alerts)}")

    by_type = {}
    for a in result.alerts:
        by_type.setdefault(a.alert_type, []).append(a)

    for atype, alerts in by_type.items():
        print(f"\n── {atype} ({len(alerts)}) ──")
        for a in alerts[:5]:
            print(f"  [{a.confirm_level}] {a.stock_id} {a.stock_name}")
            print(f"    support={a.support_type}@{a.support_level} current={a.current} state={a.support_state} distance={a.distance_pct}%")
            print(f"    severity={a.severity} conf={a.confidence} pos={a.position_label} patterns={a.pattern_labels[:3]}")

    if args.dry_run:
        print(f"\n[dry-run] 未推送")
    elif result.alerts:
        pusher = W2SAlertRedisPusher()
        pushed = await pusher.push_support_alerts(result.alerts)
        print(f"\n✅ Pushed {pushed}/{len(result.alerts)} to stream:w2s:alerts")
        await pusher.close()
    else:
        print("\n⚠️  无支撑承接观察告警")

    await svc.close()
    print(f"\n{'✅' if result.total_candidates > 0 else '⚠️'} P1-I-2 P0 done")


if __name__ == "__main__":
    asyncio.run(main())

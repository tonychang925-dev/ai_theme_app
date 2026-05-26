"""P1-G P0 验证: KlineBreakDetector → KlineAlertRedisPusher 最小闭环.

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_kline_break_detector_p0.py [--limit 10] [--dry-run]
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.kline_break_detector import (
    KlineBreakDetector, DetectionResult, SupportAlert,
)
from stock_processing_service.sinks.kline_alert_redis_pusher import KlineAlertRedisPusher

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    import argparse
    p = argparse.ArgumentParser(description="P1-G Kline Break Detector P0")
    p.add_argument("--limit", type=int, default=0, help="限制检测股票数")
    p.add_argument("--dry-run", action="store_true", help="只检测不入库/不推送")
    args = p.parse_args()

    detector = KlineBreakDetector(DSN, dedup_seconds=0)  # P0: 关闭冷却以展示全部
    pusher = KlineAlertRedisPusher() if not args.dry_run else None

    # 加载数据
    supports = await detector.load_strong_watch_supports()
    print(f"Loaded {len(supports)} strong_watch stocks with support levels")
    for s in supports[:5]:
        print(f"  {s['stock_id']} {s['stock_name']}: {s['support_type']}={s['support_level']} strength={s['support_strength']}")

    if args.limit:
        supports = supports[:args.limit]
        print(f"Limited to {len(supports)} stocks")

    stock_ids = [s["stock_id"] for s in supports]
    quotes = await detector.load_latest_quotes(stock_ids)
    print(f"Loaded quotes for {len(quotes)}/{len(stock_ids)} stocks")

    # 检测
    result = await detector.detect()
    print(f"\nDetection: checked={result.checked} alerts={len(result.alerts)} cached={result.in_state_cache} elapsed={result.elapsed_ms}ms")

    # 按 severity 分组展示
    by_sev = {}
    for a in result.alerts:
        by_sev.setdefault(a.severity, []).append(a)

    for sev in ["critical", "error", "warning", "info"]:
        alerts = by_sev.get(sev, [])
        if alerts:
            print(f"\n── {sev.upper()} ({len(alerts)}) ──")
            for a in alerts[:10]:
                print(f"  {a.stock_id} {a.stock_name}: {a.alert_type.value}")
                print(f"    support={a.support_type}@{a.support_level} current={a.current} distance={a.distance_pct}%")

    # 推送
    if pusher and result.alerts:
        pushed = await pusher.push_alerts(result.alerts)
        print(f"\nPushed {pushed}/{len(result.alerts)} alerts to Redis")
    elif args.dry_run:
        print("\n[dry-run] Would push alerts:")
        for a in result.alerts[:5]:
            print(json.dumps({
                "stock_id": a.stock_id, "stock_name": a.stock_name,
                "alert_type": a.alert_type.value, "severity": a.severity,
                "current": a.current, "support_level": a.support_level,
                "distance_pct": a.distance_pct,
            }, ensure_ascii=False, indent=2))

    await detector.close()
    if pusher:
        await pusher.close()

    print(f"\n{'✅' if result.alerts else '⚠️  no alerts'} P1-G P0 done — {len(result.alerts)} alerts, {result.checked} checked")


if __name__ == "__main__":
    asyncio.run(main())

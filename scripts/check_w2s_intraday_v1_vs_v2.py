"""P1-I-4b BT-3b: v1 vs v2 experimental scorer 对比回测。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_w2s_intraday_v1_vs_v2.py
"""
from __future__ import annotations

import asyncio, json, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    from stock_processing_service.domain.services.w2s_intraday_alert_service import W2SIntradayAlertService
    from stock_processing_service.domain.services.w2s_intraday_alert_service_v2 import W2SIntradayAlertServiceV2
    from stock_processing_service.domain.services.w2s_intraday_backtest import W2SIntradayBacktest

    print("=== P1-I-4b: v1 vs v2 对比回测 ===\n")

    for td in ("2026-05-25", "2026-05-26"):
        print(f"── {td} ──")

        # v1 via live service
        v1_svc = W2SIntradayAlertService(DSN)
        try:
            v1_result = await v1_svc.build_alerts(td)
            v1_sigs = [a for a in v1_result.alerts]
            print(f"  v1: A={v1_result.level_a} B={v1_result.level_b} C={v1_result.level_c} total={len(v1_sigs)}")
        except Exception as e:
            print(f"  v1: ERROR {e}")
            v1_sigs = []
        finally:
            await v1_svc.close()

        # v2 via experimental scorer
        v2_svc = W2SIntradayAlertServiceV2(DSN)
        try:
            v2_result = await v2_svc.build_alerts(td)
            v2_sigs = v2_result.alerts
            lc = v2_result.level_counts
            print(f"  v2: turn_strong={lc.get('turn_strong',0)} early_turn={lc.get('early_turn',0)} observe={lc.get('observe',0)} total={len(v2_sigs)}")
        except Exception as e:
            print(f"  v2: ERROR {e}")
            v2_sigs = []
        finally:
            await v2_svc.close()

        # v1 backtest for forward returns
        bt = W2SIntradayBacktest(DSN)
        bt_result = await bt.run(td, limit_stocks=50)
        bt_by_stock: dict[str, list] = defaultdict(list)
        for s in bt_result.signals:
            bt_by_stock[(s.stock_id, s.minute_ts[:19])].append(s)
        await bt.close()

        # Check v2 signals against backtest
        if v2_sigs:
            rets_30 = []
            levels = defaultdict(list)
            for a in v2_sigs:
                bt_matches = bt_by_stock.get((a.stock_id, a.minute_ts[:19] if hasattr(a, 'minute_ts') else ""))
                ret = None
                if bt_matches:
                    ret = bt_matches[0].ret_30m
                if ret is not None:
                    rets_30.append(ret)
                    levels[a.v2_level].append(ret)

            avg_all = sum(rets_30) / len(rets_30) if rets_30 else 0
            print(f"  v2 avg_ret_30m={avg_all:.2f}% (n={len(rets_30)})")
            for lvl in ("turn_strong", "early_turn", "observe"):
                lvl_rets = levels.get(lvl, [])
                if lvl_rets:
                    avg = sum(lvl_rets) / len(lvl_rets)
                    print(f"    {lvl}: avg_ret_30m={avg:.2f}% (n={len(lvl_rets)})")

        # v1 backtest comparison
        if v1_sigs:
            rets_30_v1 = []
            level_rets_v1 = defaultdict(list)
            for a in v1_sigs:
                bt_matches = bt_by_stock.get((a.stock_id, ""))
                ret = None
                if bt_matches:
                    ret = bt_matches[0].ret_30m
                if ret is not None:
                    rets_30_v1.append(ret)
                    level_rets_v1[a.alert_level].append(ret)

            avg_v1 = sum(rets_30_v1) / len(rets_30_v1) if rets_30_v1 else 0
            print(f"  v1 avg_ret_30m={avg_v1:.2f}% (n={len(rets_30_v1)})")
            for lvl in ("A", "B", "C"):
                lvl_rets = level_rets_v1.get(lvl, [])
                if lvl_rets:
                    print(f"    {lvl}: avg_ret_30m={sum(lvl_rets)/len(lvl_rets):.2f}% (n={len(lvl_rets)})")

        print()

    print("✅ P1-I-4b v1 vs v2 comparison done")


if __name__ == "__main__":
    asyncio.run(main())

"""P1-I-4d: v2.1 影子运行 + v1/v2/v2.1 并行记录。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_w2s_intraday_shadow_log_p0.py --trade-date 2026-05-26 [--dry-run]
"""
from __future__ import annotations

import asyncio, json, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.w2s_intraday_backtest import W2SIntradayBacktest
from stock_processing_service.domain.services.w2s_intraday_alert_service_v2 import W2SIntradayAlertServiceV2
from stock_processing_service.domain.services.intraday_minute_state_builder import calc_vwap

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


async def main():
    import argparse
    p = argparse.ArgumentParser(description="P1-I-4d Shadow Log P0")
    p.add_argument("--trade-date", default="2026-05-26")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    bt = W2SIntradayBacktest(DSN)
    result = await bt.run(args.trade_date, limit_stocks=50 if args.limit == 0 else args.limit)
    if not result.signals:
        print(f"No signals for {args.trade_date}")
        await bt.close()
        return

    stock_ids = list({s.stock_id for s in result.signals})
    series_map = await bt.load_minute_series(args.trade_date, stock_ids)

    rows_to_log = []
    v21_dist = defaultdict(int)

    for sig in result.signals:
        series = series_map.get(sig.stock_id, [])
        sig_ts = sig.minute_ts[:19]
        idx = next((i for i, r in enumerate(series) if str(r.get("minute_ts", ""))[:19] == sig_ts), -1)
        if idx < 0:
            continue

        row_data = series[idx]
        current = float(row_data.get("current") or 0)
        amt_d = float(row_data.get("amount_delta") or 0)
        vol_d = float(row_data.get("vol_delta") or 0)
        vw, _, _, _ = calc_vwap(amt_d, vol_d, current)

        state = {
            "vwap": vw or sig.vwap,
            "relative_strength_vs_index": sig.relative_strength,
            "platform_high_30m": 0, "platform_low_30m": 0,
            "break_platform_30m": sig.break_platform,
            "amount_delta": amt_d, "current": current,
        }

        history = []
        for r in series[max(0, idx - 10):idx + 1]:
            c = float(r.get("current") or 0)
            vv = float(r.get("vwap") or c)
            history.append({
                "minute_ts": str(r.get("minute_ts", "")),
                "above_vwap": c > vv,
                "relative_strength_vs_index": float(r.get("relative_strength_vs_index") or 0),
                "close": float(r.get("close") or c),
                "amount_delta": float(r.get("amount_delta") or 0),
            })

        # v1 score (backtest engine)
        v1_score = sig.intraday_score
        v1_level = sig.alert_level

        # v2 score
        v2_s, v2_l, v2_bd, _ = W2SIntradayAlertServiceV2.score_v2(state, history, "B", current, 0)

        # v2.1 score
        v21_s, v21_l, v21_bd, _ = W2SIntradayAlertServiceV2.score_v2_1(state, history, "B", current, 0)

        v21_dist[v21_l] += 1

        rows_to_log.append({
            "trade_date": args.trade_date,
            "minute_ts": sig.minute_ts,
            "candidate_id": 0,  # fallback: no D1 candidate
            "stock_id": sig.stock_id,
            "stock_name": sig.stock_name,
            "theme_name": "",
            "candidate_type": "",
            "weak_type": "",
            "v1_score": v1_score, "v1_level": v1_level,
            "v2_score": v2_s, "v2_level": v2_l,
            "v21_score": v21_s, "v21_level": v21_l,
            "current": current,
            "vwap": vw or sig.vwap,
            "distance_to_vwap_pct": v21_bd.get("distance_to_vwap_pct", 0),
            "relative_strength_vs_index": sig.relative_strength,
            "relative_strength_cross_zero": v21_bd.get("relative_strength_cross_zero", False),
            "relative_strength_slope_5m": v21_bd.get("relative_strength_slope_5m", 0),
            "above_vwap_ratio_5m": v21_bd.get("above_vwap_ratio_5m", 0),
            "above_vwap_cross_up": v21_bd.get("above_vwap_cross_up", False),
            "amount_acceleration": v21_bd.get("amount_acceleration", False),
            "price_momentum_3m": v21_bd.get("price_momentum_3m", 0),
            "signal_price_position_30m": v21_bd.get("price_position_30m", 0.5),
            "break_platform_30m": sig.break_platform,
            "chase_risk_penalty": v21_bd.get("chase_risk_penalty", 0),
            "false_break_penalty": v21_bd.get("false_break_penalty", 0),
            "ret_5m": sig.ret_5m,
            "ret_10m": sig.ret_10m,
            "ret_30m": sig.ret_30m,
            "ret_60m": sig.ret_60m,
            "max_drawdown_after_signal": 0,
            "payload": json.dumps({"v1_bd": {}, "v2_bd": v2_bd, "v21_bd": v21_bd}, ensure_ascii=False),
        })

    # 输出分布
    print(f"Trade date: {args.trade_date}")
    print(f"Total signals: {len(rows_to_log)}")
    v1_dist = defaultdict(int)
    v2_dist = defaultdict(int)
    for r in rows_to_log:
        v1_dist[r["v1_level"]] += 1
        v2_dist[r["v2_level"]] += 1
    print(f"  v1: A={v1_dist.get('A',0)} B={v1_dist.get('B',0)} C={v1_dist.get('C',0)}")
    print(f"  v2: turn_strong={v2_dist.get('turn_strong',0)} early_turn={v2_dist.get('early_turn',0)} observe={v2_dist.get('observe',0)}")
    print(f"  v2.1: turn_strong={v21_dist.get('turn_strong',0)} early_turn={v21_dist.get('early_turn',0)} observe={v21_dist.get('observe',0)}")

    if args.dry_run:
        print(f"\n[dry-run] {len(rows_to_log)} rows would be logged")
    else:
        # Write to DB
        import asyncpg
        from datetime import date as dt_date
        pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3)
        written = 0
        for r in rows_to_log[:5000]:
            try:
                td = dt_date.fromisoformat(str(r["trade_date"])[:10])
                from datetime import datetime as dt_dt
                mts = dt_dt.fromisoformat(str(r["minute_ts"]).replace(" ", "T"))
                await pool.execute(
                    """INSERT INTO w2s_intraday_alert_log
                       (trade_date, minute_ts, candidate_id, stock_id, stock_name,
                        v1_score, v1_level, v2_score, v2_level, v21_score, v21_level,
                        current, vwap, distance_to_vwap_pct, relative_strength_vs_index,
                        relative_strength_cross_zero, relative_strength_slope_5m,
                        above_vwap_ratio_5m, above_vwap_cross_up, amount_acceleration,
                        price_momentum_3m, signal_price_position_30m, break_platform_30m,
                        chase_risk_penalty, false_break_penalty,
                        ret_5m, ret_10m, ret_30m, ret_60m, payload)
                       VALUES ($1,$2,$3,$4,$5,
                               $6,$7,$8,$9,$10,$11,
                               $12,$13,$14,$15,
                               $16,$17,$18,$19,$20,$21,$22,$23,
                               $24,$25,$26,$27,$28,$29,$30::jsonb)""",
                    td, mts, r["candidate_id"], r["stock_id"], r["stock_name"],
                    str(r["v1_score"]), r["v1_level"], str(r["v2_score"]), r["v2_level"], str(r["v21_score"]), r["v21_level"],
                    str(r["current"]), str(r["vwap"]), str(r["distance_to_vwap_pct"]), str(r["relative_strength_vs_index"]),
                    r["relative_strength_cross_zero"], str(r["relative_strength_slope_5m"]),
                    str(r["above_vwap_ratio_5m"]), r["above_vwap_cross_up"], r["amount_acceleration"],
                    str(r["price_momentum_3m"]), str(r["signal_price_position_30m"]), r["break_platform_30m"],
                    str(r["chase_risk_penalty"]), str(r["false_break_penalty"]),
                    str(r["ret_5m"] or 0), str(r["ret_10m"] or 0), str(r["ret_30m"] or 0), str(r["ret_60m"] or 0),
                    r["payload"],
                )
                written += 1
            except Exception as exc:
                print(f"  Write failed: {exc}")
                break
        await pool.close()
        print(f"\n✅ Wrote {written} rows to w2s_intraday_alert_log")

    await bt.close()
    print(f"\n✅ P1-I-4d shadow log done")


if __name__ == "__main__":
    asyncio.run(main())

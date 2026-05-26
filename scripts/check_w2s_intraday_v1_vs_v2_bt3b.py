"""BT-3b: v1 vs v2 多日对比回测。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/check_w2s_intraday_v1_vs_v2_bt3b.py
"""
from __future__ import annotations

import asyncio, json, sys
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from stock_processing_service.domain.services.w2s_intraday_backtest import W2SIntradayBacktest, BacktestSignal
from stock_processing_service.domain.services.w2s_intraday_alert_service_v2 import W2SIntradayAlertServiceV2
from stock_processing_service.domain.services.intraday_minute_state_builder import calc_vwap

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


def bucket(value: float, cuts: list[float]) -> str:
    for c in cuts:
        if value < c:
            return f"<{c}"
    return f">={cuts[-1]}"


async def main():
    bt = W2SIntradayBacktest(DSN)

    # 只在有分钟数据的交易日运行
    trade_dates = ["2026-05-25", "2026-05-26"]

    all_v1_sigs: list[BacktestSignal] = []
    all_v2_results: list[dict] = []

    for td in trade_dates:
        result = await bt.run(td, limit_stocks=50)
        if not result.signals:
            print(f"{td}: no backtest signals, skipping")
            continue

        # Load series for v2 scoring
        stock_ids = list({s.stock_id for s in result.signals})
        series_map = await bt.load_minute_series(td, stock_ids)

        for sig in result.signals:
            sig._trade_date = td
            all_v1_sigs.append(sig)

            # Apply v2 scoring
            series = series_map.get(sig.stock_id, [])
            # Find the minute index matching this signal
            sig_ts = sig.minute_ts[:19]
            sig_idx = next((i for i, r in enumerate(series) if str(r.get("minute_ts", ""))[:19] == sig_ts), -1)
            if sig_idx < 0:
                continue

            row = series[sig_idx]
            current = float(row.get("current") or 0)
            # Recompute VWAP
            amt_d = float(row.get("amount_delta") or 0)
            vol_d = float(row.get("vol_delta") or 0)
            vwap_val, _, _, _ = calc_vwap(amt_d, vol_d, current)

            state = {
                "vwap": vwap_val or sig.vwap,
                "above_vwap": current > (vwap_val or sig.vwap),
                "relative_strength_vs_index": sig.relative_strength,
                "platform_high_30m": 0,
                "platform_low_30m": 0,
                "break_platform_30m": sig.break_platform,
                "amount_delta": amt_d,
                "current": current,
            }

            # History sorted (most recent first)
            history = []
            for r in series[max(0, sig_idx-10):sig_idx+1]:
                c = float(r.get("current") or 0)
                v = float(r.get("vwap") or c)
                history.append({
                    "minute_ts": str(r.get("minute_ts", "")),
                    "above_vwap": c > v,
                    "relative_strength_vs_index": float(r.get("relative_strength_vs_index") or 0),
                    "close": float(r.get("close") or c),
                    "amount_delta": float(r.get("amount_delta") or 0),
                })

            score, level, bd, ev = W2SIntradayAlertServiceV2.score_v2(state, history, "B", current, 0)

            all_v2_results.append({
                "stock_id": sig.stock_id,
                "stock_name": sig.stock_name,
                "trade_date": td,
                "minute_ts": sig.minute_ts,
                "v1_level": sig.alert_level,
                "v1_score": sig.intraday_score,
                "v2_level": level,
                "v2_score": score,
                "current": sig.current,
                "vwap": vwap_val or sig.vwap,
                "ret_5m": sig.ret_5m,
                "ret_30m": sig.ret_30m,
                "break_platform": sig.break_platform,
                "above_vwap_ratio": sig.above_vwap_ratio,
                "relative_strength": sig.relative_strength,
                **bd,  # all diagnostic fields
            })

    await bt.close()

    # ── 总体对比 ──
    print(f"=== BT-3b: v1 vs v2 ({len(trade_dates)} days, {len(all_v1_sigs)} v1 signals) ===\n")

    print("--- Signal counts ---")
    v1_dist = defaultdict(int)
    v2_dist = defaultdict(int)
    for s in all_v1_sigs:
        v1_dist[s.alert_level] += 1
    for r in all_v2_results:
        v2_dist[r["v2_level"]] += 1
    print(f"  v1: A={v1_dist['A']} B={v1_dist['B']} C={v1_dist['C']}")
    print(f"  v2: turn_strong={v2_dist['turn_strong']} early_turn={v2_dist['early_turn']} observe={v2_dist['observe']}")

    # ── 收益对比 ──
    def avg_ret(items, key="ret_30m"):
        vals = [r[key] for r in items if isinstance(r, dict) and r.get(key) is not None]
        return sum(vals)/len(vals) if vals else 0.0, len(vals)

    for label, items, level_key in [
        ("v1 A", [s for s in all_v1_sigs if s.alert_level == "A"], "alert_level"),
        ("v1 B", [s for s in all_v1_sigs if s.alert_level == "B"], "alert_level"),
        ("v1 C", [s for s in all_v1_sigs if s.alert_level == "C"], "alert_level"),
        ("v2 turn_strong", [r for r in all_v2_results if r["v2_level"] == "turn_strong"], "v2_level"),
        ("v2 early_turn", [r for r in all_v2_results if r["v2_level"] == "early_turn"], "v2_level"),
        ("v2 observe", [r for r in all_v2_results if r["v2_level"] == "observe"], "v2_level"),
    ]:
        if isinstance(items[0] if items else None, BacktestSignal):
            r5 = [s.ret_5m for s in items if s.ret_5m is not None]
            r30 = [s.ret_30m for s in items if s.ret_30m is not None]
        else:
            r5 = [r["ret_5m"] for r in items if r["ret_5m"] is not None]
            r30 = [r["ret_30m"] for r in items if r["ret_30m"] is not None]
        if r5 and r30:
            print(f"  {label}: n={len(items)} avg_ret_5m={sum(r5)/len(r5):.2f}% avg_ret_30m={sum(r30)/len(r30):.2f}% {f'win_5m={sum(1 for r in r5 if r>0)/len(r5):.1%}' if r5 else ''}")

    # ── 追高程度对比 ──
    v1_dists = [s.above_vwap_ratio for s in all_v1_sigs]
    v2_dists_vwap = [r.get("distance_to_vwap_pct", 0) for r in all_v2_results if r.get("distance_to_vwap_pct")]
    v2_positions = [r.get("price_position_30m", 0) for r in all_v2_results if r.get("price_position_30m")]

    print(f"\n--- Chase risk comparison ---")
    v1_chase = sum(1 for s in all_v1_sigs if s.above_vwap_ratio >= 0.9)
    if v2_dists_vwap:
        print(f"  v1 above_vwap>=0.9: {v1_chase}/{len(all_v1_sigs)} ({v1_chase/max(len(all_v1_sigs),1)*100:.1f}%)")
        print(f"  v2 avg distance_to_vwap: {sum(v2_dists_vwap)/len(v2_dists_vwap):.2f}%")
        print(f"  v2 distance_to_vwap>3%: {sum(1 for d in v2_dists_vwap if d>3)}/{len(v2_dists_vwap)}")
    if v2_positions:
        print(f"  v2 avg price_position_30m: {sum(v2_positions)/len(v2_positions):.3f}")
        print(f"  v2 price_pos>0.85: {sum(1 for p in v2_positions if p>0.85)}/{len(v2_positions)}")

    # ── 交叉对比 ──
    print(f"\n--- Cross comparison ---")
    v2_early = [r for r in all_v2_results if r["v2_level"] == "early_turn"]
    v1_c = [s for s in all_v1_sigs if s.alert_level == "C"]
    if v2_early:
        r30_early = [r["ret_30m"] for r in v2_early if r["ret_30m"] is not None]
        print(f"  v2 early_turn avg_ret_30m={sum(r30_early)/len(r30_early):.2f}% (n={len(v2_early)})")
    if v1_c:
        r30_c = [s.ret_30m for s in v1_c if s.ret_30m is not None]
        print(f"  v1 C avg_ret_30m={sum(r30_c)/len(r30_c):.2f}% (n={len(v1_c)})")

    # ── v2 turn_strong 追高诊断 ──
    v2_ts = [r for r in all_v2_results if r["v2_level"] == "turn_strong"]
    if v2_ts:
        ts_dist = [r.get("distance_to_vwap_pct", 0) for r in v2_ts]
        ts_ret = [r["ret_30m"] for r in v2_ts if r["ret_30m"] is not None]
        print(f"\n  v2 turn_strong: n={len(v2_ts)} avg_dist_vwap={sum(ts_dist)/len(ts_dist):.2f}% avg_ret_30m={sum(ts_ret)/len(ts_ret):.2f}%")

    # ── 因子诊断 ──
    print(f"\n--- Factor diagnostics (v2) ---")
    for factor in ["above_vwap_cross_up", "relative_strength_cross_zero", "amount_acceleration"]:
        true_items = [r for r in all_v2_results if r.get(factor)]
        false_items = [r for r in all_v2_results if not r.get(factor)]
        r30_t = [r["ret_30m"] for r in true_items if r["ret_30m"] is not None]
        r30_f = [r["ret_30m"] for r in false_items if r["ret_30m"] is not None]
        if r30_t and r30_f:
            print(f"  {factor}=true: avg_30m={sum(r30_t)/len(r30_t):.2f}% (n={len(r30_t)})")
            print(f"  {factor}=false: avg_30m={sum(r30_f)/len(r30_f):.2f}% (n={len(r30_f)})")

    # ── 结论 ──
    print(f"\n=== Conclusions ===")
    v2_chase_pct = sum(1 for r in all_v2_results if r.get("distance_to_vwap_pct", 0) > 3) / max(len(all_v2_results), 1) * 100
    v2_early_r30 = [r["ret_30m"] for r in all_v2_results if r.get("v2_level") == "early_turn" and r.get("ret_30m") is not None]
    v1_c_r30 = [s.ret_30m for s in all_v1_sigs if s.alert_level == "C" and s.ret_30m is not None]
    v2_avg_r30 = sum(e)/len(e) if (e := [r["ret_30m"] for r in all_v2_results if r.get("ret_30m") is not None]) else 0

    print(f"  1. Chase risk reduction: v2 dist>3% = {v2_chase_pct:.1f}%")
    print(f"  2. v2 early_turn vs v1 C: {sum(v2_early_r30)/len(v2_early_r30):.2f}% vs {sum(v1_c_r30)/len(v1_c_r30):.2f}%")
    print(f"  3. v2 overall avg_ret_30m: {v2_avg_r30:.2f}%")

    print(f"\n✅ BT-3b complete")


if __name__ == "__main__":
    asyncio.run(main())

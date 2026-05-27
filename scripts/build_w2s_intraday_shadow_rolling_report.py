"""P1-I-4i: v2.2 连续交易日滚动汇总报告。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/build_w2s_intraday_shadow_rolling_report.py [--days 5] [--end-date 2026-05-26]
"""
from __future__ import annotations

import asyncio, json, sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asyncpg

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"
OUT_DIR = ROOT / "tmp" / "shadow_reports"


def avg(items):
    vals = [float(r) for r in items if r is not None]
    return sum(vals) / len(vals) if vals else 0.0

def win_rate(items):
    vals = [float(r) for r in items if r is not None]
    return sum(1 for v in vals if v > 0) / len(vals) if vals else 0


async def main():
    import argparse
    p = argparse.ArgumentParser(description="P1-I-4i Rolling Report")
    p.add_argument("--days", type=int, default=5)
    p.add_argument("--end-date", default="2026-05-26")
    args = p.parse_args()

    end = date.fromisoformat(args.end_date)
    start = end - timedelta(days=args.days - 1)

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3)

    # Find available dates
    rows = await pool.fetch(
        "SELECT DISTINCT trade_date FROM w2s_intraday_alert_log WHERE trade_date >= $1 AND trade_date <= $2 ORDER BY trade_date",
        start, end)
    available_dates = [r["trade_date"] for r in rows]

    if not available_dates:
        print(f"No data between {start} and {end}")
        await pool.close()
        return

    actual_start = available_dates[0]
    actual_end = available_dates[-1]
    print(f"Rolling report: {actual_start} → {actual_end} ({len(available_dates)} trading days)\n")

    # Load all data
    all_data = []
    for td in available_dates:
        day_rows = await pool.fetch(
            "SELECT * FROM w2s_intraday_alert_log WHERE trade_date = $1", td)
        all_data.extend([dict(r) for r in day_rows])

    n = len(all_data)
    if n == 0:
        print("No data")
        await pool.close()
        return

    # ── Daily breakdown ──
    by_date = defaultdict(list)
    for r in all_data:
        by_date[str(r["trade_date"])].append(r)

    print("=== 每日概览 ===")
    for td in sorted(by_date.keys()):
        items = by_date[td]
        v22_et = sum(1 for r in items if r.get("v22_level") == "early_turn")
        v22_ts = sum(1 for r in items if r.get("v22_level") == "turn_strong")
        rets_30 = [float(r["ret_30m"]) for r in items if r.get("ret_30m") is not None]
        et_rets = [float(r["ret_30m"]) for r in items if r.get("ret_30m") is not None and r.get("v22_level") == "early_turn"]
        print(f"  {td}: n={len(items)} v2.2_et={v22_et} v2.2_ts={v22_ts} "
              f"avg_30m={avg(rets_30):.2f}% et_30m={avg(et_rets):.2f}%")

    # ── Aggregate stats ──
    v22_et_items = [r for r in all_data if r.get("v22_level") == "early_turn"]
    v22_observe = [r for r in all_data if r.get("v22_level") == "observe"]
    v1a_blocked = [r for r in all_data if r.get("v1_level") == "A" and r.get("v22_level") == "observe"]
    v1b_blocked = [r for r in all_data if r.get("v1_level") == "B" and r.get("v22_level") == "observe"]
    missed = [r for r in all_data if r.get("v22_level") == "observe"
              and r.get("ret_30m") is not None and float(r["ret_30m"]) > 2.0]

    print(f"\n=== v2.2 汇总 ({len(available_dates)} days, {n} signals) ===")
    print(f"  early_turn: {len(v22_et_items)} ({len(v22_et_items)/n*100:.1f}%)")
    print(f"  turn_strong: {sum(1 for r in all_data if r.get('v22_level')=='turn_strong')}")

    for label, items in [
        ("early_turn", v22_et_items),
        ("observe", v22_observe),
        ("ALL", all_data),
    ]:
        rets_30 = [float(r["ret_30m"]) for r in items if r.get("ret_30m") is not None]
        rets_5 = [float(r["ret_5m"]) for r in items if r.get("ret_5m") is not None]
        if rets_30:
            print(f"  {label}: avg_5m={avg(rets_5):.2f}% avg_30m={avg(rets_30):.2f}% "
                  f"win_30m={win_rate(rets_30):.1%} max_dd={min(rets_30):.2f}%")

    # ── Factor performance ──
    print(f"\n--- 因子贡献 ({len(available_dates)} days) ---")
    for factor in ["relative_strength_cross_zero", "above_vwap_cross_up",
                   "amount_acceleration", "break_platform_30m"]:
        true_items = [r for r in all_data if r.get(factor)]
        false_items = [r for r in all_data if not r.get(factor)]
        t_ret = [float(r["ret_30m"]) for r in true_items if r.get("ret_30m") is not None]
        f_ret = [float(r["ret_30m"]) for r in false_items if r.get("ret_30m") is not None]
        if t_ret and f_ret:
            diff = avg(t_ret) - avg(f_ret)
            print(f"  {factor}: true(n={len(t_ret)})={avg(t_ret):.2f}% vs false={avg(f_ret):.2f}% diff={diff:+.2f}% {'✅' if diff>0 else '❌'}")

    # ── Blocking + missed ──
    print(f"\n--- 拦截与漏报 ---")
    blocked_rets = [float(r["ret_30m"]) for r in v1a_blocked + v1b_blocked if r.get("ret_30m") is not None]
    missed_rets = [float(r["ret_30m"]) for r in missed if r.get("ret_30m") is not None]
    print(f"  v1 A 被拦截: {len(v1a_blocked)} 条, avg_30m={avg([float(r['ret_30m']) for r in v1a_blocked if r.get('ret_30m') is not None]):.2f}%")
    print(f"  v1 B 被拦截: {len(v1b_blocked)} 条, avg_30m={avg([float(r['ret_30m']) for r in v1b_blocked if r.get('ret_30m') is not None]):.2f}%")
    print(f"  漏报 (ret_30m>2%): {len(missed)} 条, avg_30m={avg(missed_rets):.2f}%")

    # ── Conclusions ──
    # ── 市场环境汇总 ──
    from stock_processing_service.domain.services.w2s_market_context_service import W2SMarketContextService
    ctx_svc = W2SMarketContextService(DSN)
    print(f"\n--- 市场环境 ---")
    for td in sorted(by_date.keys()):
        ctx = await ctx_svc.build_context(td)
        print(f"  {td}: market={ctx.market_regime}({ctx.market_score}) idx={ctx.index_pct_chg:.2f}% | subject={ctx.subject_regime} risk={'⚠️' if ctx.context_risk else '✅'}")
    await ctx_svc.close()

    print(f"\n--- 结论 ---")
    et_avg = avg([float(r["ret_30m"]) for r in v22_et_items if r.get("ret_30m") is not None])
    all_avg = avg([float(r["ret_30m"]) for r in all_data if r.get("ret_30m") is not None])
    if et_avg > all_avg:
        print(f"  ✅ v2.2 early_turn 优于全量均值 ({et_avg:.2f}% > {all_avg:.2f}%)")
    else:
        print(f"  ⚠️ v2.2 early_turn 弱于全量均值 ({et_avg:.2f}% < {all_avg:.2f}%)")
    print(f"  建议: {'继续观察' if len(available_dates) < 5 else '可考虑微调 early_turn 阈值' if len(available_dates) >= 10 else '观察至少 5 个交易日'}")

    # JSON output
    report = {
        "period": f"{actual_start} → {actual_end}",
        "trading_days": len(available_dates),
        "total_signals": n,
        "v2_2": {
            "early_turn_count": len(v22_et_items),
            "turn_strong_count": sum(1 for r in all_data if r.get("v22_level") == "turn_strong"),
            "early_turn_avg_30m": round(et_avg, 4),
            "all_avg_30m": round(all_avg, 4),
        },
        "blocking": {
            "v1a_blocked": len(v1a_blocked),
            "v1b_blocked": len(v1b_blocked),
        },
        "missed_strong": len(missed),
        "conclusion": "continue_observe" if len(available_dates) < 5 else "consider_calibration" if len(available_dates) >= 10 else "observe_5_days",
    }

    out_path = OUT_DIR / f"rolling_shadow_report_{actual_start}_{actual_end}.json"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n{out_path}")

    await pool.close()
    print("✅ P1-I-4i rolling report done")


if __name__ == "__main__":
    asyncio.run(main())

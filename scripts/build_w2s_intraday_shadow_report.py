"""P1-I-4e: 盘中弱转强影子信号日终复盘报告。

用法:
  PYTHONPATH=/Users/admin/Desktop/ai_theme_app \
  python scripts/build_w2s_intraday_shadow_report.py --trade-date 2026-05-26 [--out-dir tmp/shadow_reports]

v3.0-A: 新增 w2s_field() helper — 优先从 payload JSONB 读取 W2SSignal 兼容字段，
        缺字段时回退到旧 log 表列。后续 v3.0-A+ w2s_signal_fusion_log 就绪后可直接切换。
"""
from __future__ import annotations

import asyncio, json, sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asyncpg

from stock_processing_service.domain.services.intraday_minute_state_builder import calc_vwap

DSN = "postgresql://postgres:postgres@localhost:5432/stock_data_test"


def pct(val, n=1):
    return f"{val*100:.{n}f}%"


def w2s_field(row: dict[str, Any], field: str, default: Any = None) -> Any:
    """v3.0-A: 优先从 payload JSONB 读取 W2SSignal 兼容字段，缺字段回退旧列。"""
    payload = row.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            payload = None
    if isinstance(payload, dict):
        mapping = {
            "current": "current", "vwap": "vwap",
            "relative_strength_vs_index": "relative_strength",
            "relative_strength_cross_zero": "relative_strength_cross_zero",
            "above_vwap_cross_up": "above_vwap",
            "amount_acceleration": "amount_acceleration",
            "break_platform_30m": "break_platform_30m",
            "support_state": "support_state",
            "alert_level": "alert_level",
        }
        mapped = mapping.get(field, field)
        if mapped in payload:
            return payload[mapped]
        fs = payload.get("factor_snapshot")
        if isinstance(fs, dict) and field in fs:
            return fs[field]
    return row.get(field, default)


async def main():
    import argparse
    p = argparse.ArgumentParser(description="P1-I-4e Shadow Report")
    p.add_argument("--trade-date", required=True)
    p.add_argument("--out-dir", default=str(ROOT / "tmp" / "shadow_reports"))
    args = p.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=3)
    td = date.fromisoformat(args.trade_date)

    rows = await pool.fetch(
        "SELECT * FROM w2s_intraday_alert_log WHERE trade_date = $1", td)
    if not rows:
        print(f"No shadow log data for {args.trade_date}")
        await pool.close()
        return

    data = [dict(r) for r in rows]
    n = len(data)
    print(f"Loaded {n} shadow signals for {args.trade_date}")

    # ── Helper ──
    def avg_ret(items, key="ret_30m"):
        vals = [float(r[key]) for r in items if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else 0.0, len(vals)

    def win_rate(items, key="ret_30m"):
        vals = [float(r[key]) for r in items if r.get(key) is not None]
        return sum(1 for v in vals if v > 0) / len(vals) if vals else 0

    def count_level(items, level_key):
        dist = defaultdict(int)
        for r in items:
            dist[r.get(level_key, "?")] += 1
        return dict(dist)

    # ── 1. 信号总览 ──
    v1_dist = count_level(data, "v1_level")
    v2_dist = count_level(data, "v2_level")
    v21_dist = count_level(data, "v21_level")

    # ── 2. 收益表现 ──
    v1_ret = {lvl: avg_ret([r for r in data if r.get("v1_level") == lvl]) for lvl in ("A", "B", "C")}
    v2_ret = {lvl: avg_ret([r for r in data if r.get("v2_level") == lvl]) for lvl in ("turn_strong", "early_turn", "observe")}
    v21_ret = {lvl: avg_ret([r for r in data if r.get("v21_level") == lvl]) for lvl in ("turn_strong", "early_turn", "observe")}

    # ── v2.2 评分 (on-the-fly) ──
    from stock_processing_service.domain.services.w2s_intraday_alert_service_v2 import W2SIntradayAlertServiceV2
    for r in data:
        state = {
            "vwap": float(r.get("vwap") or 0),
            "relative_strength_vs_index": float(r.get("relative_strength_vs_index") or 0),
            "platform_high_30m": 0, "platform_low_30m": 0,
            "break_platform_30m": r.get("break_platform_30m", False),
            "amount_delta": 0, "current": float(r.get("current") or 0),
        }
        hist = [{
            "minute_ts": str(r.get("minute_ts", "")),
            "above_vwap": bool(r.get("above_vwap_cross_up", False)),
            "relative_strength_vs_index": float(r.get("relative_strength_vs_index") or 0),
            "close": float(r.get("current") or 0),
            "amount_delta": 0,
        }] * 3  # minimal history
        s22, l22, _, _ = W2SIntradayAlertServiceV2.score_v2_2(
            state, hist, "B", float(r.get("current") or 0), 0)
        r["v22_score"] = s22
        r["v22_level"] = l22

    v22_dist = count_level(data, "v22_level")

    # ── 3. 拦截效果 (按 v1 级别拆分) ──
    blocked_a = [r for r in data if r.get("v1_level") == "A" and r.get("v21_level") == "observe"]
    blocked_b = [r for r in data if r.get("v1_level") == "B" and r.get("v21_level") == "observe"]
    blocked_c = [r for r in data if r.get("v1_level") == "C" and r.get("v21_level") == "observe"]
    blocked = blocked_a + blocked_b
    blocked_ret, blocked_n = avg_ret(blocked)
    blocked_wr = win_rate(blocked)
    v1a_blocked = blocked_a

    # v2.2 recall analysis
    v22_recalled_a = [r for r in blocked_a if r.get("v22_level") in ("early_turn", "turn_strong")]
    v22_recalled_b = [r for r in blocked_b if r.get("v22_level") in ("early_turn", "turn_strong")]
    v22_recalled_c = [r for r in blocked_c if r.get("v22_level") in ("early_turn", "turn_strong")]

    # ── 4. 漏报检查 ──
    # v2.1 observe 但 ret_30m > 2% (显著走强)
    missed_strong = [r for r in data if r.get("v21_level") == "observe" and r.get("ret_30m") is not None and float(r["ret_30m"]) > 2.0]
    # v2.1 observe 但 ret_30m > 1%
    missed_moderate = [r for r in data if r.get("v21_level") == "observe" and r.get("ret_30m") is not None and float(r["ret_30m"]) > 1.0]

    # ── 5. 因子表现 ──
    factor_results = {}
    for factor in ["relative_strength_cross_zero", "above_vwap_cross_up",
                   "amount_acceleration", "break_platform_30m"]:
        true_items = [r for r in data if r.get(factor)]
        false_items = [r for r in data if not r.get(factor)]
        factor_results[factor] = {
            "true_n": len(true_items),
            "true_avg_30m": avg_ret(true_items)[0],
            "false_avg_30m": avg_ret(false_items)[0],
            "diff": round(avg_ret(true_items)[0] - avg_ret(false_items)[0], 4),
        }

    # ── 6. distance_to_vwap bucket ──
    dist_buckets = defaultdict(list)
    for r in data:
        d = float(r.get("distance_to_vwap_pct") or 0)
        if d <= 1: bucket = "0-1%"
        elif d <= 1.5: bucket = "1-1.5%"
        elif d <= 2: bucket = "1.5-2%"
        elif d <= 3: bucket = "2-3%"
        else: bucket = ">3%"
        dist_buckets[bucket].append(r)

    # ── 7. 结论 ──
    conclusions = []
    # v2.1 是否过严
    v21_early_n = v21_dist.get("early_turn", 0)
    v21_ts_n = v21_dist.get("turn_strong", 0)
    if v21_ts_n == 0 and v21_early_n < n * 0.05:
        conclusions.append("v2.1 当前门禁可能偏严 (early_turn+turn_strong < 5%)，建议观察 5+ 交易日后判断是否放宽 early_turn 阈值")
    elif v21_ts_n == 0:
        conclusions.append("v2.1 turn_strong=0，门禁严格。建议保持观察，不急于放开")

    # v1 是否过激进
    v1_ab_n = v1_dist.get("A", 0) + v1_dist.get("B", 0)
    v1_ab_ret, _ = avg_ret([r for r in data if r.get("v1_level") in ("A", "B")])
    v1_c_ret, _ = avg_ret([r for r in data if r.get("v1_level") == "C"])
    if v1_ab_ret < v1_c_ret:
        conclusions.append(f"v1 A/B avg_30m={v1_ab_ret:.2f}% < C={v1_c_ret:.2f}%，v1 追高倾向确认，v2.1 拦截合理")
    else:
        conclusions.append(f"v1 A/B 表现优于 C，但需更多样本验证")

    # 拦截效果
    if blocked_n > 0:
        conclusions.append(f"v2.1 拦截了 {blocked_n} 条 v1 A/B 信号，被拦截信号 avg_30m={blocked_ret:.2f}%，拦截{'有效' if blocked_ret < 0 else '无显著效果'}")

    # 漏报
    conclusions.append(f"v2.1 observe 中 {len(missed_strong)} 条 ret_30m>2% (潜在漏报)，{len(missed_moderate)} 条 ret_30m>1%")

    # ── 8. 结论 (v2.2 主视角) ──
    v22_dist = count_level(data, "v22_level")
    v22_early_n = v22_dist.get("early_turn", 0)
    v22_ts_n = v22_dist.get("turn_strong", 0)
    v22_early_items = [r for r in data if r.get("v22_level") == "early_turn"]
    v22_early_r, _ = avg_ret(v22_early_items)
    v22_observe_items = [r for r in data if r.get("v22_level") == "observe"]
    v22_observe_r, _ = avg_ret(v22_observe_items)

    # ── 市场环境 ──
    from stock_processing_service.domain.services.w2s_market_context_service import W2SMarketContextService
    ctx_svc = W2SMarketContextService(DSN)
    market_ctx = await ctx_svc.build_context(args.trade_date)
    await ctx_svc.close()

    conclusions = []
    if v22_early_n > 0:
        conclusions.append(f"v2.2 early_turn={v22_early_n} 条 ({v22_early_n/n*100:.1f}%), avg_30m={v22_early_r:.2f}% — {'优于' if v22_early_r > v22_observe_r else '弱于'}全量均值")
    else:
        conclusions.append("v2.2 early_turn=0 — 今日无早期转强信号")
    if v22_early_n < n * 0.15:
        conclusions.append(f"v2.2 early_turn 占比 {v22_early_n/n*100:.1f}% — 门禁正常，不偏严")
    elif v22_early_n < n * 0.05:
        conclusions.append(f"v2.2 early_turn 占比 {v22_early_n/n*100:.1f}% — 门禁可能偏严，建议继续观察")
    if market_ctx.context_risk:
        conclusions.append(f"⚠️ 市场环境风险: {market_ctx.market_regime}/{market_ctx.subject_regime}，今日信号可信度降低")
    conclusions.append("v2.2 为默认影子观察模型，全部信号为观察级，不输出买入建议")

    # ── 9. 输出 ──
    report = {
        "trade_date": args.trade_date,
        "total_signals": n,
        "signal_distribution": {"v1": v1_dist, "v2": v2_dist, "v2_1": v21_dist},
        "returns_by_level": {
            "v1": {lvl: {"avg_30m": round(r[0], 4), "n": r[1]} for lvl, r in v1_ret.items() if r[1] > 0},
            "v2": {lvl: {"avg_30m": round(r[0], 4), "n": r[1]} for lvl, r in v2_ret.items() if r[1] > 0},
            "v2_1": {lvl: {"avg_30m": round(r[0], 4), "n": r[1]} for lvl, r in v21_ret.items() if r[1] > 0},
        },
        "blocking": {
            "v1_ab_blocked_by_v21": blocked_n,
            "blocked_avg_30m": round(blocked_ret, 4),
            "blocked_win_rate": round(blocked_wr, 4),
            "v1a_blocked": len(v1a_blocked),
        },
        "missed_signals": {
            "strong_missed": len(missed_strong),
            "moderate_missed": len(missed_moderate),
            "strong_samples": [{"stock_id": r["stock_id"], "stock_name": r["stock_name"], "ret_30m": float(r["ret_30m"])}
                               for r in missed_strong[:10]],
        },
        "factor_contribution": factor_results,
        "distance_to_vwap_buckets": {b: {"n": len(items), "avg_30m": round(avg_ret(items)[0], 4)}
                                      for b, items in dist_buckets.items()},
        "conclusions": conclusions,
    }

    # Console
    print(f"\n=== 弱转强影子信号日终复盘: {args.trade_date} ===\n")
    print(f"总信号: {n}")
    print(f"市场环境: {market_ctx.market_regime}({market_ctx.market_score}) idx={market_ctx.index_pct_chg:.2f}% | "
          f"题材: {market_ctx.subject_regime}({market_ctx.subject_strength_score})")
    print(f"环境置信度: {market_ctx.context_confidence} | 风险: {'⚠️' if market_ctx.context_risk else '✅'}")
    print(f"v1:  A={v1_dist.get('A',0)} B={v1_dist.get('B',0)} C={v1_dist.get('C',0)}")
    print(f"v2:  turn_strong={v2_dist.get('turn_strong',0)} early_turn={v2_dist.get('early_turn',0)} observe={v2_dist.get('observe',0)}")
    print(f"v2.1: turn_strong={v21_dist.get('turn_strong',0)} early_turn={v21_dist.get('early_turn',0)} observe={v21_dist.get('observe',0)}")
    print(f"v2.2: turn_strong={v22_dist.get('turn_strong',0)} early_turn={v22_dist.get('early_turn',0)} observe={v22_dist.get('observe',0)}")

    print(f"\n--- 收益表现 ---")
    for ver, rets in [("v1", v1_ret), ("v2", v2_ret), ("v2.1", v21_ret)]:
        for lvl, (avg_r, cnt) in rets.items():
            if cnt > 0:
                print(f"  {ver} {lvl}: avg_30m={avg_r:.2f}% win={win_rate([r for r in data if r.get(f'{ver}_level')==lvl]):.1%} (n={cnt})")

    print(f"\n--- 拦截效果 ---")
    print(f"  v1 A/B 被 v2.1 拦截: {blocked_n} 条, avg_30m={blocked_ret:.2f}%, win_rate={blocked_wr:.1%}")
    if v1a_blocked:
        v1a_r, _ = avg_ret(v1a_blocked)
        print(f"  其中 v1 A 级被拦: {len(v1a_blocked)} 条, avg_30m={v1a_r:.2f}%")

    print(f"\n--- 漏报检查 ---")
    print(f"  v2.1 observe 中 ret_30m>2%: {len(missed_strong)} 条")
    print(f"  v2.1 observe 中 ret_30m>1%: {len(missed_moderate)} 条")

    print(f"\n--- 因子贡献 ---")
    for factor, fr in factor_results.items():
        print(f"  {factor}: true(n={fr['true_n']})={fr['true_avg_30m']:.2f}% vs false(n={n-fr['true_n']})={fr['false_avg_30m']:.2f}% diff={fr['diff']:.2f}%")

    # v2.2 return stats
    v22_ret = {}
    for lvl in ("turn_strong", "early_turn", "observe"):
        items = [r for r in data if r.get("v22_level") == lvl]
        v22_ret[lvl] = avg_ret(items)

    print(f"\n--- v2.2 收益 ---")
    for lvl, (avg_r, cnt) in v22_ret.items():
        if cnt > 0:
            print(f"  v2.2 {lvl}: avg_30m={avg_r:.2f}% (n={cnt})")

    print(f"\n--- 拦截拆分 (v1 → v2.1) ---")
    for label, items in [("v1 A→v2.1 observe", blocked_a), ("v1 B→v2.1 observe", blocked_b), ("v1 C→v2.1 observe", blocked_c)]:
        a, n = avg_ret(items)
        if n > 0:
            print(f"  {label}: avg_30m={a:.2f}% (n={n})")

    print(f"\n--- v2.2 召回 (v2.1 observe → v2.2 early_turn) ---")
    for label, items in [("v1 A recalled", v22_recalled_a), ("v1 B recalled", v22_recalled_b), ("v1 C recalled", v22_recalled_c)]:
        a, n = avg_ret(items)
        print(f"  {label}: avg_30m={a:.2f}% (n={n})" if n > 0 else f"  {label}: n=0")

    # v2.2 conclusions
    v22_early_n = len([r for r in data if r.get("v22_level") == "early_turn"])
    v22_early_r, _ = avg_ret([r for r in data if r.get("v22_level") == "early_turn"])
    if v22_early_n > 0 and v22_early_n < n * 0.3:
        conclusions.append(f"v2.2 early_turn={v22_early_n} 条 ({v22_early_n/n*100:.1f}%), avg_30m={v22_early_r:.2f}%, 召回比例合理")
    if v22_recalled_a:
        recalled_a_ret, _ = avg_ret(v22_recalled_a)
        conclusions.append(f"v2.2 召回 v1 A 被拦 {len(v22_recalled_a)} 条, avg_30m={recalled_a_ret:.2f}% {'→ 谨慎' if recalled_a_ret < -0.5 else '→ 部分有效'}")

    print(f"\n--- 版本对照 ---")
    print(f"  {'版本':<8} {'强信号':>6} {'观察':>6} {'弱/其他':>8}  avg_30m(观察)")
    for ver_name, dist, ret_key in [
        ("v1", v1_dist, "v1_level"),
        ("v2", v2_dist, "v2_level"),
        ("v2.1", v21_dist, "v21_level"),
        ("v2.2", v22_dist, "v22_level"),
    ]:
        strong = dist.get("A", dist.get("turn_strong", 0))
        obs = dist.get("B", dist.get("early_turn", 0))
        weak = dist.get("C", dist.get("observe", 0))
        obs_ret = v22_ret.get("early_turn", (0,0))[0] if ver_name == "v2.2" else 0
        print(f"  {ver_name:<8} {strong:>6} {obs:>6} {weak:>8}  {'—' if ver_name != 'v2.2' else f'{v22_early_r:.2f}%'}")

    print(f"\n--- 结论 (v2.2 默认影子模型) ---")
    for i, c in enumerate(conclusions, 1):
        print(f"  {i}. {c}")

    # JSON
    json_path = out_dir / f"shadow_report_{args.trade_date}.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nJSON: {json_path}")

    # Markdown
    md_lines = [
        f"# 弱转强影子信号日终复盘 — {args.trade_date}",
        "",
        f"**总信号**: {n}",
        "",
        "## 信号分布",
        "",
        f"| 版本 | 强信号 | 观察 | 弱/其他 |",
        f"|------|--------|------|---------|",
        f"| v1 | A={v1_dist.get('A',0)} B={v1_dist.get('B',0)} | — | C={v1_dist.get('C',0)} |",
        f"| v2 | turn_strong={v2_dist.get('turn_strong',0)} | early_turn={v2_dist.get('early_turn',0)} | observe={v2_dist.get('observe',0)} |",
        f"| v2.1 | turn_strong={v21_dist.get('turn_strong',0)} | early_turn={v21_dist.get('early_turn',0)} | observe={v21_dist.get('observe',0)} |",
        "",
        "## 收益表现",
        "",
    ]
    for ver, rets in [("v1", v1_ret), ("v2", v2_ret), ("v2.1", v21_ret)]:
        for lvl, (avg_r, cnt) in rets.items():
            if cnt > 0:
                wr = win_rate([r for r in data if r.get(f"{ver}_level") == lvl])
                md_lines.append(f"- **{ver} {lvl}**: avg_30m={avg_r:.2f}%, win={wr:.1%} (n={cnt})")

    md_lines += [
        "",
        "## 拦截效果",
        f"- v1 A/B 被 v2.1 拦截: {blocked_n} 条, avg_30m={blocked_ret:.2f}%",
        "",
        "## 漏报检查",
        f"- v2.1 observe 中 ret_30m>2%: {len(missed_strong)} 条",
        f"- v2.1 observe 中 ret_30m>1%: {len(missed_moderate)} 条",
        "",
        "## 因子贡献",
    ]
    for factor, fr in factor_results.items():
        md_lines.append(f"- **{factor}**: true(n={fr['true_n']})={fr['true_avg_30m']:.2f}% vs false={fr['false_avg_30m']:.2f}% diff={fr['diff']:.2f}%")

    md_lines += ["", "## 结论"]
    for i, c in enumerate(conclusions, 1):
        md_lines.append(f"{i}. {c}")

    md_path = out_dir / f"shadow_report_{args.trade_date}.md"
    md_path.write_text("\n".join(md_lines))
    print(f"Markdown: {md_path}")

    await pool.close()
    print(f"\n✅ P1-I-4e shadow report done")


if __name__ == "__main__":
    asyncio.run(main())

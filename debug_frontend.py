#!/usr/bin/env python3
"""
调试前端数据显示问题
"""
import asyncio
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from datetime import date

async def test():
    # 模拟API内部逻辑
    from frontend_bff.app import _fetch_w2s_candidates, _fetch_w2s_signals, _build_w2s_result_row

    # 测试阶段1: 2026-04-07的候选池 (next_trade_date = 2026-04-08?)
    print("=== 阶段1测试: 获取2026-04-08的候选 (next_trade_date) ===")
    candidates = await _fetch_w2s_candidates(date(2026, 4, 8), limit=100)
    print(f"候选数量: {len(candidates)}")
    for c in candidates[:5]:
        print(f"  id={c.get('id')}, stock_id={c.get('stock_id')}, candidate_score={c.get('candidate_score')}")

    # 测试阶段2: 2026-04-08的信号
    print("\n=== 阶段2测试: 获取2026-04-08的信号 ===")
    signals = await _fetch_w2s_signals(date(2026, 4, 8))
    print(f"信号数量: {len(signals)}")
    for cand_id, sig in signals.items():
        print(f"  candidate_id={cand_id}, signal_level={sig.get('signal_level')}, confirmation_score={sig.get('confirmation_score')}")

    # 构建结果
    print("\n=== 构建结果 (阶段2模式) ===")
    candidate_map = {int(c.get("id") or 0): c for c in candidates if int(c.get("id") or 0) > 0}
    sorted_signals = sorted(
        signals.items(),
        key=lambda kv: float((kv[1] or {}).get("confirmation_score") or 0.0),
        reverse=True,
    )
    results = []
    for candidate_id, signal in sorted_signals:
        candidate = candidate_map.get(int(candidate_id))
        if candidate is None:
            continue
        results.append(_build_w2s_result_row(candidate, signal, len(results) + 1))

    print(f"构建的结果数量: {len(results)}")
    for i, r in enumerate(results[:5]):
        print(f"  {i}: stock_id={r.get('stock_id')}, composite_score={r.get('composite_score')}, signal_level={r.get('weak_to_strong', {}).get('signal_level')}")

    # 检查神剑股份
    print("\n=== 检查神剑股份 ===")
    shenjian = None
    for r in results:
        if '002361' in r.get('stock_id', ''):
            shenjian = r
            break

    if shenjian:
        print(f"找到神剑股份: {shenjian.get('stock_id')}")
        print(f"  composite_score: {shenjian.get('composite_score')}")
        print(f"  signal_level: {shenjian.get('weak_to_strong', {}).get('signal_level')}")
        print(f"  decision: {shenjian.get('weak_to_strong', {}).get('decision')}")
        print(f"  confirmation_score: {shenjian.get('weak_to_strong', {}).get('confirmation_score')}")
    else:
        print("未找到神剑股份")
        # 检查候选映射
        for cand_id, cand in candidate_map.items():
            if '002361' in cand.get('stock_id', ''):
                print(f"  候选映射中存在但信号中无对应: candidate_id={cand_id}, stock_id={cand.get('stock_id')}")
                # 检查信号是否有此candidate_id
                if cand_id in signals:
                    print(f"    信号也存在: {signals[cand_id]}")
                else:
                    print(f"    信号中无此candidate_id")

if __name__ == "__main__":
    asyncio.run(test())
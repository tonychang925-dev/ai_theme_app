#!/usr/bin/env python3
"""
测试_fetch_w2s_candidates函数
"""
import asyncio
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from datetime import date
from frontend_bff.app import _fetch_w2s_candidates, _fetch_w2s_signals

async def test():
    print("测试_fetch_w2s_candidates...")
    # 测试2026-04-07 (trade_date)
    candidates = await _fetch_w2s_candidates(date(2026, 4, 7), limit=100)
    print(f"查询2026-04-07返回 {len(candidates)} 个候选")
    for c in candidates[:5]:
        print(f"  stock_id={c.get('stock_id')}, trade_date={c.get('trade_date')}, next_trade_date={c.get('next_trade_date')}, score={c.get('candidate_score')}")

    # 检查神剑股份
    shenjian = None
    for c in candidates:
        if '002361' in c.get('stock_id', ''):
            shenjian = c
            break

    if shenjian:
        print(f"\n找到神剑股份: stock_id={shenjian.get('stock_id')}")
        print(f"  trade_date={shenjian.get('trade_date')}, next_trade_date={shenjian.get('next_trade_date')}")
        print(f"  candidate_score={shenjian.get('candidate_score')}")
    else:
        print("\n未找到神剑股份")

    # 测试2026-04-08 (next_trade_date)
    print("\n\n测试2026-04-08 (next_trade_date)...")
    candidates2 = await _fetch_w2s_candidates(date(2026, 4, 8), limit=100)
    print(f"查询2026-04-08返回 {len(candidates2)} 个候选")
    for c in candidates2[:5]:
        print(f"  stock_id={c.get('stock_id')}, trade_date={c.get('trade_date')}, next_trade_date={c.get('next_trade_date')}")

    # 测试信号
    print("\n\n测试_fetch_w2s_signals...")
    signals = await _fetch_w2s_signals(date(2026, 4, 8))
    print(f"2026-04-08有 {len(signals)} 个信号")
    for cand_id, sig in list(signals.items())[:5]:
        print(f"  candidate_id={cand_id}, signal_level={sig.get('signal_level')}, confirmation_score={sig.get('confirmation_score')}")

if __name__ == "__main__":
    asyncio.run(test())
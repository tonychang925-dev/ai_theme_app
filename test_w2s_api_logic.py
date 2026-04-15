#!/usr/bin/env python3
"""
测试弱转强API逻辑
"""
import asyncio
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from datetime import date
from frontend_bff.app import _execute_weak_to_strong_two_stage
from frontend_bff.app import ScreenerExecutePayload

async def test():
    print("测试弱转强两阶段逻辑...")

    # 模拟payload
    payload = ScreenerExecutePayload(
        strategy_id="weak_to_strong",
        trade_date="2026-04-07",
        limit=20,
        auto_tune_min_score=True,
        target_min_count=30,
        target_max_count=120,
        enable_llm_review=False,
        llm_top_k=20,
        run_stage1=False,  # 只运行stage2，因为候选池已存在
        run_stage2=True
    )

    try:
        result = await _execute_weak_to_strong_two_stage(payload, date(2026, 4, 7))
        print(f"状态: {result.get('status')}")
        print(f"总结果数: {result.get('total_count')}")
        print(f"results长度: {len(result.get('results', []))}")

        diagnostics = result.get('diagnostics', {})
        print(f"candidate_pool_count: {diagnostics.get('candidate_pool_count')}")
        print(f"stage1: {diagnostics.get('stage1')}")
        print(f"stage2: {diagnostics.get('stage2')}")

        # 查找神剑股份
        shenjian = None
        for r in result.get('results', []):
            if '002361' in r.get('stock_id', ''):
                shenjian = r
                break

        if shenjian:
            print(f"\n找到神剑股份:")
            print(f"  stock_id: {shenjian.get('stock_id')}")
            print(f"  composite_score: {shenjian.get('composite_score')}")
            print(f"  weak_to_strong: {shenjian.get('weak_to_strong')}")
        else:
            print("\n未找到神剑股份")
            # 打印前几个结果
            print(f"前5个结果:")
            for i, r in enumerate(result.get('results', [])[:5]):
                print(f"  {i}: {r.get('stock_id')} - {r.get('composite_score')}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test())
#!/usr/bin/env python3
"""最终测试神剑股份是否入选"""

import asyncio
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def test():
    builder = EnhancedCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        # 清理旧数据
        pool = await builder._ensure_pool()
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM weak_to_strong_candidate_pool WHERE trade_date = $1", test_date)

        # 运行增强构建器
        result = await builder.build_enhanced(test_date, max_formal=35, max_observe=15)

        # 查找神剑股份
        shenjian_found = False
        for cand in result.candidates:
            if cand.get("stock_id") == "002361.SZ" or (cand.get("stock_id") == "002361"):
                shenjian_found = True
                print("✅ 神剑股份成功进入候选池!")
                print(f"  准入类型: {cand.get('pool_entry_type')}")
                print(f"  候选评分: {cand.get('candidate_score')}")
                print(f"  周期状态: {cand.get('cycle_state')}")
                print(f"  退潮确认: {cand.get('fade_confirmed')}")
                break

        if not shenjian_found:
            print("❌ 神剑股份未进入候选池")
            print(f"候选总数: {len(result.candidates)}")
            # 打印前几个候选
            for i, cand in enumerate(result.candidates[:5], 1):
                print(f"{i}. {cand.get('stock_id')} {cand.get('stock_name')} - {cand.get('pool_entry_type')}")

        return shenjian_found
    finally:
        await builder.close()

if __name__ == "__main__":
    success = asyncio.run(test())
    sys.exit(0 if success else 1)
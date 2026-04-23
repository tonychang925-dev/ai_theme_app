#!/usr/bin/env python3
"""快速测试神剑股份是否出现在扫描列表中（LEGACY，建议改用 analyze_stock_w2s.py）。"""

import asyncio
import sys
import os
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def test():
    print("[LEGACY] 建议改用: .venv/bin/python scripts/analyze_stock_w2s.py --stock-code 002361 --trade-date 2026-04-07")
    builder = EnhancedCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        # 调用重写的方法
        rows = await builder._fetch_candidate_inputs(test_date)
        print(f"扫描到 {len(rows)} 条记录")

        # 查找神剑股份
        shenjian_rows = [r for r in rows if r.get("stock_id") == "002361.SZ" or (r.get("stock_code") == "002361" and r.get("stock_id", "").endswith(".SZ"))]

        if shenjian_rows:
            print("✅ 神剑股份出现在扫描列表中!")
            for r in shenjian_rows:
                print(f"  股票ID: {r.get('stock_id')}")
                print(f"  主题键: {r.get('subject_key')}")
                print(f"  主题名: {r.get('theme_name')}")
                print(f"  主线存活: {r.get('final_mainline_alive')}")
                print(f"  周期阶段: {r.get('cycle_state')}")
                print(f"  退潮确认: {r.get('fade_confirmed')}")
                print(f"  排名: {r.get('rank_order')}")
                print(f"  涨跌幅: {r.get('pct_chg')}")
                print(f"  是否涨停: {r.get('limit_up')}")
                print(f"  是否龙头: {r.get('is_leader')}")
        else:
            print("❌ 神剑股份未出现在扫描列表中")
            # 打印前几个股票看看
            print("\n前10个股票:")
            for i, r in enumerate(rows[:10], 1):
                print(
                    f"  {i}. {r.get('stock_id')} {r.get('stock_name')} - "
                    f"主题: {r.get('theme_name')}, 主线存活: {r.get('final_mainline_alive')}"
                )
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test())

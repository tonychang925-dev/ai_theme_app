#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def main():
    if len(sys.argv) > 1:
        test_date = date.fromisoformat(sys.argv[1])
    else:
        test_date = date(2026, 4, 7)

    builder = EnhancedCandidateBuilder()
    try:
        print(f"开始构建 {test_date} 的弱转强候选池...")
        result = await builder.build(test_date)
        print(f"扫描 {result.total_scanned} 只股票，插入 {result.total_inserted} 只候选")

        # 查找神剑股份 (002361)
        found = False
        for candidate in result.candidates:
            if candidate.get("stock_id") == "002361" or candidate.get("stock_id") == "002361.SZ":
                found = True
                print(f"✅ 神剑股份入选候选池!")
                print(f"   股票: {candidate.get('stock_name')} ({candidate.get('stock_id')})")
                print(f"   主题: {candidate.get('subject_key')} ({candidate.get('theme_name')})")
                print(f"   周期状态: {candidate.get('primary_cycle_stage')}, 退潮: {candidate.get('is_fade')}")
                print(f"   准入类型: {candidate.get('pool_entry_type', 'unknown')}")
                print(f"   支撑位类型: {candidate.get('support_type')}, 支撑强度: {candidate.get('support_score')}")
                break
        if not found:
            print(f"❌ 神剑股份未入选候选池")
            # 打印前几个候选
            print("前5个候选:")
            for i, candidate in enumerate(result.candidates[:5], 1):
                print(f"{i}. {candidate.get('stock_id')} {candidate.get('stock_name')} - {candidate.get('theme_name')} - {candidate.get('primary_cycle_stage')}")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())
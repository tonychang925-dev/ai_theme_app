#!/usr/bin/env python3
import asyncio
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def test():
    builder = EnhancedCandidateBuilder()
    try:
        # Test April 3
        trade_date = date(2026, 4, 3)
        print(f"测试增强版构建器 - {trade_date}")

        # Use enhanced mode
        result = await builder.build_enhanced(trade_date, max_formal=10, max_observe=5)
        print(f"扫描: {result.total_scanned}, 插入: {result.total_inserted}")

        # Look for Shenjian
        found = False
        for candidate in result.candidates:
            stock_id = candidate.get("stock_id")
            if stock_id == "002361" or stock_id == "002361.SZ":
                found = True
                print(f"✅ 神剑股份入选候选池!")
                print(f"  pool_entry_type: {candidate.get('pool_entry_type')}")
                print(f"  support_strength: {candidate.get('support_strength')}")
                print(f"  candidate_score: {candidate.get('candidate_score')}")
                break

        if not found:
            print("❌ 神剑股份未入选候选池")

            # Show first few candidates if any
            if result.candidates:
                print("前几个候选:")
                for i, c in enumerate(result.candidates[:3], 1):
                    print(f"{i}. {c.get('stock_id')} - {c.get('support_strength')} - {c.get('candidate_score')}")

    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test())
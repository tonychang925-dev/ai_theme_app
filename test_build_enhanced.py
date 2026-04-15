#!/usr/bin/env python3
import asyncio
import sys
sys.path.insert(0, '.')
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def test():
    builder = EnhancedCandidateBuilder()
    try:
        # Test pool creation
        pool = await builder._ensure_pool()
        print("✅ Database pool created")

        # Test fetch candidate inputs but limited to Shenjian by modifying SQL temporarily
        # Let's just call build_enhanced with small limits
        trade_date = date(2026, 4, 7)
        print(f"Building enhanced candidates for {trade_date}...")
        result = await builder.build_enhanced(trade_date, max_formal=0, max_observe=5)
        print(f"Total scanned: {result.total_scanned}")
        print(f"Total inserted: {result.total_inserted}")

        found = False
        for candidate in result.candidates:
            stock_id = candidate.get("stock_id")
            if stock_id == "002361" or stock_id == "002361.SZ":
                found = True
                print(f"✅ Shenjian found in candidates!")
                print(f"  pool_entry_type: {candidate.get('pool_entry_type')}")
                print(f"  candidate_score: {candidate.get('candidate_score')}")
                break

        if not found:
            print("❌ Shenjian not in candidates")
            # Print first few candidates
            for i, candidate in enumerate(result.candidates[:5]):
                print(f"{i}. {candidate.get('stock_id')} {candidate.get('stock_name')} - {candidate.get('pool_entry_type')} - score:{candidate.get('candidate_score')}")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(test())
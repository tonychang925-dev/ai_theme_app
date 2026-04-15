#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def main():
    test_date = date(2026, 4, 7)
    builder = EnhancedCandidateBuilder()
    try:
        print(f"Fetching candidate base rows for {test_date}...")
        rows = await builder._fetch_candidate_base_rows(test_date)
        print(f"Total rows: {len(rows)}")
        for row in rows:
            stock_id = row.get("stock_id")
            if stock_id == "002361" or stock_id == "002361.SZ":
                print(f"Found Shenjian row:")
                for key, value in row.items():
                    print(f"  {key}: {value}")
                break
        else:
            print("Shenjian not found in base rows")
            # Print first few rows to see structure
            for i, row in enumerate(rows[:5]):
                print(f"Row {i}: stock_id={row.get('stock_id')}, rank_order={row.get('rank_order')}, limit_up={row.get('limit_up')}, is_leader={row.get('is_leader')}")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())
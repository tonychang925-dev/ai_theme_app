#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def main():
    test_date = date(2026, 4, 7)
    builder = EnhancedCandidateBuilder()
    try:
        print(f"Fetching candidate inputs for {test_date}...")
        rows = await builder._fetch_candidate_inputs(test_date)
        print(f"Total rows: {len(rows)}")
        for row in rows:
            if row['stock_id'] == '002361' or row['stock_id'] == '002361.SZ':
                print("Found Shenjian in rows:")
                for key, val in row.items():
                    print(f"  {key}: {val}")
                break
        else:
            print("Shenjian NOT in rows")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())
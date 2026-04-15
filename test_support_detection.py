#!/usr/bin/env python3
import asyncio
import asyncpg
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test():
    builder = WeakToStrongCandidateBuilder()

    # Test Shenjian on April 3 and April 7
    test_cases = [
        (date(2026, 4, 3), -8.9647, None),  # pct_chg, prev_day_pct (unknown)
        (date(2026, 4, 7), -3.1100, -8.9647),  # prev_day_pct is April 3
    ]

    for trade_date, pct_chg, prev_day_pct in test_cases:
        print(f'\n=== {trade_date} ===')
        print(f'pct_chg: {pct_chg}, prev_day_pct: {prev_day_pct}')

        # Mock prev_day_limit_up as False
        prev_day_limit_up = False

        # Call _classify_weak_type
        weak_type, weak_intensity = builder._classify_weak_type(pct_chg, prev_day_pct or 0, prev_day_limit_up)
        print(f'weak_type: {weak_type}, weak_intensity: {weak_intensity}')

        # Call _support_type_from_row
        support_type = builder._support_type_from_row(pct_chg, prev_day_pct or 0)
        print(f'support_type: {support_type}')

        # Call _support_strength
        support_strength = builder._support_strength(pct_chg, prev_day_pct or 0, support_type)
        print(f'support_strength: {support_strength}')

    await builder.close()

if __name__ == "__main__":
    asyncio.run(test())
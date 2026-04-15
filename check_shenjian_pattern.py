#!/usr/bin/env python3
"""
检查神剑股份的涨停模式
"""
import asyncio
import asyncpg
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService

async def check_pattern():
    stock_id = "002361"
    test_dates = [date(2026, 4, 3), date(2026, 4, 7)]

    strong_service = StrongStockAnalysisService()

    for trade_date in test_dates:
        print(f"\n=== 检查 {trade_date} ===")
        limit_up_pattern = await strong_service._analyze_limit_up_pattern(
            stock_id, trade_date, trading_days=7
        )

        print(f"涨停模式: {limit_up_pattern}")
        print(f"  是否有涨停模式: {limit_up_pattern['has_limit_up_pattern']}")
        print(f"  涨停次数: {limit_up_pattern['limit_up_count']}")
        print(f"  最长连续涨停: {limit_up_pattern['max_consecutive_days']}")
        print(f"  模式类型: {limit_up_pattern['pattern_type']}")

    await strong_service.close()

if __name__ == "__main__":
    asyncio.run(check_pattern())
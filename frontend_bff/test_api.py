#!/usr/bin/env python3
import asyncio
import sys
import os
from datetime import date
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 模拟payload
from frontend_bff.schemas import ScreenerExecutePayload

async def test_two_stage():
    from frontend_bff.app import _execute_weak_to_strong_two_stage
    payload = ScreenerExecutePayload(
        strategy_id="weak_to_strong",
        trade_date="2026-04-08",
        run_stage1=False,
        run_stage2=True,
        limit=20,
        min_score=0.0,
        auto_tune_min_score=False,
        target_min_count=1,
        target_max_count=20,
        enable_llm_review=False,
        llm_top_k=5,
    )
    result = await _execute_weak_to_strong_two_stage(payload, date(2026, 4, 8))
    print(f"结果: status={result['status']}, total_count={result['total_count']}")
    print(f"诊断信息: {result['diagnostics']}")

if __name__ == "__main__":
    asyncio.run(test_two_stage())

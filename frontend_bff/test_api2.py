#!/usr/bin/env python3
import asyncio
import sys
import os
from datetime import date
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_two_stage():
    # 模拟payload对象
    payload = SimpleNamespace()
    payload.strategy_id = "weak_to_strong"
    payload.trade_date = "2026-04-08"
    payload.run_stage1 = False
    payload.run_stage2 = True
    payload.limit = 20
    payload.min_score = 0.0
    payload.auto_tune_min_score = False
    payload.target_min_count = 1
    payload.target_max_count = 20
    payload.enable_llm_review = False
    payload.llm_top_k = 5
    
    # 导入函数
    from frontend_bff.app import _execute_weak_to_strong_two_stage
    result = await _execute_weak_to_strong_two_stage(payload, date(2026, 4, 8))
    print(f"结果: status={result['status']}, total_count={result['total_count']}")
    print(f"诊断信息: {result['diagnostics']}")

if __name__ == "__main__":
    asyncio.run(test_two_stage())

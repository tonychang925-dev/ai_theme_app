#!/usr/bin/env python3
"""
测试_fetch_candidate_inputs方法
"""
import asyncio
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from datetime import date

async def test():
    print("测试_fetch_candidate_inputs")
    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 7)
        rows = await builder._fetch_candidate_inputs(trade_date)
        print(f"返回行数: {len(rows)}")
        # 查找神剑股份
        for i, row in enumerate(rows[:10]):
            stock_id = row.get('stock_id', '')
            if '002361' in stock_id:
                print(f"找到神剑股份 at index {i}")
                print(f"  stock_id: {stock_id}")
                print(f"  subject_key: {row.get('subject_key')}")
                print(f"  pct_chg: {row.get('pct_chg')}")
                break
        else:
            print("未在前10行中找到神剑股份，继续搜索...")
            for i, row in enumerate(rows):
                stock_id = row.get('stock_id', '')
                if '002361' in stock_id:
                    print(f"找到神剑股份 at index {i}")
                    print(f"  stock_id: {stock_id}")
                    print(f"  subject_key: {row.get('subject_key')}")
                    break
            else:
                print("在所有行中均未找到神剑股份")
                # 打印前5行信息
                for i, row in enumerate(rows[:5]):
                    print(f"行{i}: stock_id={row.get('stock_id')}, subject_key={row.get('subject_key')}")
    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

asyncio.run(test())
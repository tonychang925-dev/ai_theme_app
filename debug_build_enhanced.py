#!/usr/bin/env python3
"""
调试build_enhanced方法
"""
import asyncio
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from datetime import date

async def test():
    print("调试build_enhanced方法")
    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 7)
        print(f"交易日: {trade_date}")

        # 直接调用build_enhanced
        result = await builder.build_enhanced(trade_date, max_formal=80, max_observe=40)

        print(f"总扫描数: {result.total_scanned}")
        print(f"总插入数: {result.total_inserted}")
        print(f"候选数量: {len(result.candidates)}")

        # 检查神剑股份
        shenjian_found = False
        for candidate in result.candidates:
            stock_id = candidate.get('stock_id', '')
            if '002361' in stock_id:
                shenjian_found = True
                print(f"找到神剑股份: {candidate}")
                break

        if not shenjian_found:
            print("未在候选列表中找到神剑股份")
            # 打印前10个候选
            print("\n前10个候选:")
            for i, candidate in enumerate(result.candidates[:10]):
                print(f"{i}: stock_id={candidate.get('stock_id')}, score={candidate.get('candidate_score')}, entry_type={candidate.get('pool_entry_type')}")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

asyncio.run(test())
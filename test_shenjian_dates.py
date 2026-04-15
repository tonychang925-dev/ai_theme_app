#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_builder(builder_class, builder_name, trade_date, use_enhanced=False):
    """测试特定构建器在特定日期的表现"""
    print(f'\n=== {builder_name} - {trade_date} ===')

    if builder_class == EnhancedCandidateBuilder:
        builder = EnhancedCandidateBuilder()
        if use_enhanced:
            result = await builder.build_enhanced(trade_date, max_formal=10, max_observe=5)
        else:
            result = await builder.build(trade_date, enhanced=use_enhanced)
    else:
        builder = WeakToStrongCandidateBuilder()
        result = await builder.build(trade_date)

    print(f'扫描: {result.total_scanned}, 插入: {result.total_inserted}')

    # 查找神剑股份
    found = False
    for candidate in result.candidates:
        stock_id = candidate.get("stock_id")
        if stock_id == "002361" or stock_id == "002361.SZ":
            found = True
            print(f'✅ 神剑股份入选候选池!')
            print(f'   stock_id: {candidate.get("stock_id")}')
            print(f'   pool_entry_type: {candidate.get("pool_entry_type", "unknown")}')
            print(f'   candidate_score: {candidate.get("candidate_score")}')
            print(f'   support_type: {candidate.get("support_type")}')
            print(f'   support_strength: {candidate.get("support_strength")}')
            break

    if not found:
        print(f'❌ 神剑股份未入选候选池')

    await builder.close()
    return found

async def main():
    # 测试两个关键日期
    dates = [date(2026, 4, 3), date(2026, 4, 7)]

    print('测试神剑股份(002361)在不同日期的弱转强候选表现')
    print('=' * 80)

    for test_date in dates:
        # 1. 测试原始构建器
        await test_builder(WeakToStrongCandidateBuilder, "原始构建器", test_date)

        # 2. 测试增强构建器（原始模式）
        await test_builder(EnhancedCandidateBuilder, "增强构建器(原始模式)", test_date, use_enhanced=False)

        # 3. 测试增强构建器（增强模式）
        await test_builder(EnhancedCandidateBuilder, "增强构建器(增强模式)", test_date, use_enhanced=True)

if __name__ == "__main__":
    asyncio.run(main())
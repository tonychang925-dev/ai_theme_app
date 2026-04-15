#!/usr/bin/env python3
"""
测试entry_type分类问题
"""
import asyncio
import sys
sys.path.insert(0, '/Users/admin/Desktop/ai_theme_app')

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from datetime import date

async def test():
    print("测试entry_type分类问题")
    builder = EnhancedCandidateBuilder()
    try:
        trade_date = date(2026, 4, 7)
        # 获取候选输入
        rows = await builder._fetch_candidate_inputs(trade_date)
        print(f"获取到 {len(rows)} 行候选输入")

        # 查找神剑股份
        shenjian_row = None
        for row in rows:
            stock_id = str(row.get('stock_id', ''))
            if '002361' in stock_id:
                shenjian_row = row
                break

        if not shenjian_row:
            print("未找到神剑股份")
            return

        print(f"找到神剑股份: {shenjian_row.get('stock_id')}")

        # 获取周期特征
        subject_key = str(shenjian_row.get('subject_key', ''))
        cycle_features = await builder.fetch_cycle_features(trade_date, subject_key)
        print(f"周期特征: cycle_state={cycle_features.cycle_state}, fade_confirmed={cycle_features.fade_confirmed}")

        # 构建增强候选
        next_day = await builder.resolve_next_trade_date(trade_date)
        candidate = builder._to_enhanced_candidate(shenjian_row, trade_date, next_day, cycle_features)
        if candidate is None:
            print("候选构建失败")
            return

        print(f"候选构建成功")
        print(f"候选字典keys: {list(candidate.keys())}")
        print(f"pool_entry_type: '{candidate.get('pool_entry_type')}'")
        print(f"repr pool_entry_type: {repr(candidate.get('pool_entry_type'))}")
        print(f"type pool_entry_type: {type(candidate.get('pool_entry_type'))}")

        # 测试分类逻辑
        entry_type = candidate.get("pool_entry_type", "reject")
        print(f"entry_type from get: '{entry_type}'")
        print(f"entry_type == 'formal': {entry_type == 'formal'}")
        print(f"entry_type == 'observe_only': {entry_type == 'observe_only'}")

        # 检查determine_pool_entry_type的返回值
        strong_bg_score = candidate.get('enhanced_features', {}).get('strong_background_score', 0)
        repair_score = candidate.get('enhanced_features', {}).get('repair_window_score', 0)
        mainline_alive = candidate.get('enhanced_features', {}).get('mainline_alive', False)
        fade_confirmed = candidate.get('enhanced_features', {}).get('fade_confirmed', False)

        print(f"strong_bg_score: {strong_bg_score}")
        print(f"repair_score: {repair_score}")
        print(f"mainline_alive: {mainline_alive}")
        print(f"fade_confirmed: {fade_confirmed}")

        # 直接调用determine_pool_entry_type
        entry_type_direct = builder.determine_pool_entry_type(
            strong_bg_score, repair_score, mainline_alive, fade_confirmed
        )
        print(f"determine_pool_entry_type直接返回值: '{entry_type_direct}'")

    except Exception as e:
        print(f"错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

asyncio.run(test())
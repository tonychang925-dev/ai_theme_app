#!/usr/bin/env python3
"""
测试神剑股份是否出现在输入数据中
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_shenjian_input():
    """测试神剑股份输入数据"""
    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        print(f"测试神剑股份在 {test_date} 的输入数据...")
        print("=" * 70)

        # 获取输入数据
        rows = await builder._fetch_candidate_inputs(test_date)

        print(f"获取到 {len(rows)} 条股票输入数据")

        # 查找神剑股份
        shenjian_rows = []
        for row in rows:
            stock_code = str(row.get("stock_code", ""))
            stock_id = str(row.get("stock_id", ""))
            if "002361" in stock_code or "002361" in stock_id:
                shenjian_rows.append(row)

        if shenjian_rows:
            print(f"✅ 找到 {len(shenjian_rows)} 条神剑股份记录")
            for i, row in enumerate(shenjian_rows):
                print(f"\n神剑股份记录 {i+1}:")
                print(f"  stock_id: {row.get('stock_id')}")
                print(f"  stock_code: {row.get('stock_code')}")
                print(f"  stock_name: {row.get('stock_name')}")
                print(f"  subject_key: {row.get('subject_key')}")
                print(f"  theme_name: {row.get('theme_name')}")
                print(f"  is_main_theme: {row.get('is_main_theme')}")
                print(f"  is_fade: {row.get('is_fade')}")
                print(f"  primary_cycle_stage: {row.get('primary_cycle_stage')}")
                print(f"  action_bias: {row.get('action_bias')}")
                print(f"  is_leader: {row.get('is_leader')}")
                print(f"  limit_up: {row.get('limit_up')}")
                print(f"  pct_chg: {row.get('pct_chg')}")
                print(f"  rank_order: {row.get('rank_order')}")
                print(f"  recent_limit_up_count: {row.get('recent_limit_up_count')}")
                print(f"  prev_day_pct_chg: {row.get('prev_day_pct_chg')}")
                print(f"  prev_day_limit_up: {row.get('prev_day_limit_up')}")

                # 检查候选构建
                stock_id = builder._normalize_stock_id(str(row.get("stock_id") or ""), str(row.get("stock_code") or ""))
                print(f"\n  规范化stock_id: {stock_id}")

                # 检查_async_to_candidate
                candidate = await builder._async_to_candidate(row, test_date, test_date)
                if candidate:
                    print(f"  ✅ 构建候选成功! 分数: {candidate.get('candidate_score')}")
                else:
                    print(f"  ❌ 构建候选失败 (返回None)")
        else:
            print("❌ 未找到神剑股份记录")
            print("\n前10条股票数据:")
            for i, row in enumerate(rows[:10]):
                print(f"{i+1}. {row.get('stock_id')} {row.get('stock_name')} - "
                      f"主题: {row.get('subject_key')}, "
                      f"is_main_theme: {row.get('is_main_theme')}, "
                      f"is_fade: {row.get('is_fade')}")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def main():
    await test_shenjian_input()

if __name__ == "__main__":
    asyncio.run(main())
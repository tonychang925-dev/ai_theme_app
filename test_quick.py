#!/usr/bin/env python3
"""
快速测试神剑股份候选构建
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def quick_test():
    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        print("1. 获取输入数据...")
        rows = await builder._fetch_candidate_inputs(test_date)
        print(f"   返回 {len(rows)} 条记录")

        # 查找神剑股份
        shenjian_row = None
        for i, row in enumerate(rows):
            stock_id = str(row.get('stock_id', ''))
            stock_code = str(row.get('stock_code', ''))
            if '002361' in stock_id or '002361' in stock_code:
                shenjian_row = row
                print(f"   找到神剑股份 (索引 {i})")
                break

        if not shenjian_row:
            print("   ❌ 未找到神剑股份")
            print("   前5条记录:")
            for i, row in enumerate(rows[:5]):
                print(f"     {i+1}. {row.get('stock_id')} {row.get('stock_name')} - pct_chg: {row.get('pct_chg')}")
            return False

        print(f"\n2. 神剑股份数据:")
        print(f"   stock_id: {shenjian_row.get('stock_id')}")
        print(f"   stock_name: {shenjian_row.get('stock_name')}")
        print(f"   pct_chg: {shenjian_row.get('pct_chg')}")
        print(f"   prev_day_pct_chg: {shenjian_row.get('prev_day_pct_chg')}")
        print(f"   recent_limit_up_count: {shenjian_row.get('recent_limit_up_count')}")
        print(f"   is_leader: {shenjian_row.get('is_leader')}")
        print(f"   limit_up: {shenjian_row.get('limit_up')}")
        print(f"   rank_order: {shenjian_row.get('rank_order')}")
        print(f"   is_main_theme: {shenjian_row.get('is_main_theme')}")
        print(f"   is_fade: {shenjian_row.get('is_fade')}")
        print(f"   primary_cycle_stage: {shenjian_row.get('primary_cycle_stage')}")
        print(f"   action_bias: {shenjian_row.get('action_bias')}")

        print("\n3. 测试候选构建...")
        candidate = await builder._async_to_candidate(shenjian_row, test_date, test_date)

        if candidate:
            print(f"   ✅ 候选构建成功!")
            print(f"   candidate_score: {candidate.get('candidate_score')}")
            print(f"   support_strength: {candidate.get('support_strength')}")
            print(f"   support_type: {candidate.get('support_type')}")
            print(f"   weak_type: {candidate.get('weak_type')}")
            print(f"   repair_window: {candidate.get('repair_window')}")
            return True
        else:
            print("   ❌ 候选构建失败 (返回None)")

            # 手动检查门槛
            print("\n   手动检查硬门槛:")
            pct_chg = float(shenjian_row.get('pct_chg') or 0.0)
            prev_day_pct = float(shenjian_row.get('prev_day_pct_chg') or 0.0)
            is_leader = bool(shenjian_row.get('is_leader') or False)
            limit_up = bool(shenjian_row.get('limit_up') or False)
            rank_order = int(shenjian_row.get('rank_order') or 999)
            recent_limit_up_count = int(shenjian_row.get('recent_limit_up_count') or 0)

            # 强势背景
            strong_background = (
                is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3
            )
            print(f"   1. 强势背景: {strong_background}")
            print(f"      is_leader={is_leader}, limit_up={limit_up}")
            print(f"      recent_limit_up_count={recent_limit_up_count} >=2: {recent_limit_up_count >= 2}")
            print(f"      rank_order={rank_order} <=3: {rank_order <= 3}")

            # 修复窗口
            stage = str(shenjian_row.get('primary_cycle_stage') or '')
            action_bias = str(shenjian_row.get('action_bias') or '')
            is_divergence = bool(shenjian_row.get('is_divergence') or False)
            is_rebound = bool(shenjian_row.get('is_rebound') or False)
            is_fermentation = bool(shenjian_row.get('is_fermentation') or False)

            repair_window = (
                ('弱转强' in action_bias) or
                stage in {'divergence', 'rebound', 'fermentation', '分歧', '回流', '发酵', '启动'} or
                is_divergence or is_rebound or is_fermentation or
                (recent_limit_up_count >= 2 and pct_chg < 0)
            )
            print(f"   2. 修复窗口: {repair_window}")
            print(f"      action_bias='{action_bias}', stage='{stage}'")
            print(f"      recent_limit_up_count={recent_limit_up_count}, pct_chg={pct_chg}")
            print(f"      recent_limit_up_count >= 2 and pct_chg < 0: {recent_limit_up_count >= 2 and pct_chg < 0}")

            # 支撑强度
            print(f"   3. 支撑强度: 需要单独测试analyze_strict_support")
            try:
                support_result = await builder.analyze_strict_support("002361", pct_chg, test_date)
                print(f"      has_support: {support_result['has_support']}")
                print(f"      support_strength: {support_result.get('support_strength', 0.0) * 100:.1f}/100")
                print(f"      >=30: {support_result.get('support_strength', 0.0) * 100 >= 30}")
            except Exception as e:
                print(f"      支撑检测错误: {e}")

            return False

    except Exception as e:
        print(f"❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await builder.close()

async def main():
    success = await quick_test()
    if success:
        print("\n🎉 神剑股份候选构建测试成功")
        return 0
    else:
        print("\n⚠️ 神剑股份候选构建测试失败")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
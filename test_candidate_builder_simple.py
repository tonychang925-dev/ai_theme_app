#!/usr/bin/env python3
"""
简单测试候选构建器 - 逐步验证功能
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_step_by_step():
    print("🧪 候选构建器逐步测试")
    print("=" * 60)

    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        # 步骤1: 测试连接池初始化
        print("1️⃣ 测试连接池初始化...")
        try:
            pool = await builder._ensure_pool()
            print("   ✅ 连接池初始化成功")
        except Exception as e:
            print(f"   ❌ 连接池初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        # 步骤2: 测试_fetch_candidate_inputs
        print("\n2️⃣ 测试_fetch_candidate_inputs...")
        try:
            rows = await builder._fetch_candidate_inputs(test_date)
            print(f"   ✅ 查询成功，返回 {len(rows)} 条记录")

            # 查找神剑股份
            shenjian_found = False
            for i, row in enumerate(rows):
                stock_id = str(row.get('stock_id', ''))
                stock_code = str(row.get('stock_code', ''))
                if '002361' in stock_id or '002361' in stock_code:
                    shenjian_found = True
                    print(f"\n   🔍 找到神剑股份 (索引 {i}):")
                    print(f"      stock_id: {stock_id}")
                    print(f"      stock_name: {row.get('stock_name')}")
                    print(f"      pct_chg: {row.get('pct_chg')}")
                    print(f"      is_main_theme: {row.get('is_main_theme')}")
                    print(f"      is_fade: {row.get('is_fade')}")
                    print(f"      recent_limit_up_count: {row.get('recent_limit_up_count')}")
                    break

            if not shenjian_found:
                print(f"   ⚠️ 未找到神剑股份，显示前5条记录:")
                for i, row in enumerate(rows[:5]):
                    print(f"      {i+1}. {row.get('stock_id')} {row.get('stock_name')} - "
                          f"pct_chg: {row.get('pct_chg')}, "
                          f"is_fade: {row.get('is_fade')}")

        except Exception as e:
            print(f"   ❌ _fetch_candidate_inputs失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        # 步骤3: 测试神剑股份的候选构建
        print("\n3️⃣ 测试神剑股份候选构建...")
        try:
            # 再次查找神剑股份
            rows = await builder._fetch_candidate_inputs(test_date)
            shenjian_row = None
            for row in rows:
                if '002361' in str(row.get('stock_id', '')) or '002361' in str(row.get('stock_code', '')):
                    shenjian_row = row
                    break

            if shenjian_row:
                print(f"   ✅ 找到神剑股份数据")
                candidate = await builder._async_to_candidate(shenjian_row, test_date, test_date)
                if candidate:
                    print(f"   ✅ 候选构建成功!")
                    print(f"      candidate_score: {candidate.get('candidate_score')}")
                    print(f"      support_strength: {candidate.get('support_strength')}")
                    print(f"      support_type: {candidate.get('support_type')}")
                    print(f"      weak_type: {candidate.get('weak_type')}")
                    print(f"      repair_window: {candidate.get('repair_window')}")
                else:
                    print(f"   ❌ 候选构建失败 (返回None)")
                    print(f"      可能被硬门槛过滤")

                    # 手动检查门槛
                    print(f"\n      手动检查硬门槛:")
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
                    print(f"      1. 强势背景: {strong_background} "
                          f"(is_leader={is_leader}, limit_up={limit_up}, "
                          f"recent_limit_up_count={recent_limit_up_count}, rank_order={rank_order})")

                    # 修复窗口
                    stage = str(shenjian_row.get('primary_cycle_stage') or '')
                    action_bias = str(shenjian_row.get('action_bias') or '')
                    is_divergence = bool(shenjian_row.get('is_divergence') or False)
                    is_rebound = bool(shenjian_row.get('is_rebound') or False)
                    is_fermentation = bool(shenjian_row.get('is_fermentation') or False)

                    repair_window = (
                        ('弱转强' in action_bias) or
                        stage in {'divergence', 'rebound', 'fermentation', '分歧', '回流', '发酵', '启动'} or
                        is_divergence or
                        is_rebound or
                        is_fermentation or
                        (recent_limit_up_count >= 2 and pct_chg < 0)
                    )
                    print(f"      2. 修复窗口: {repair_window} "
                          f"(action_bias='{action_bias}', stage='{stage}', "
                          f"recent_limit_up_count={recent_limit_up_count}, pct_chg={pct_chg})")

                    # 支撑强度（需要单独测试）
                    print(f"      3. 支撑强度: 需要单独测试analyze_strict_support")
            else:
                print(f"   ❌ 未找到神剑股份在输入数据中")

        except Exception as e:
            print(f"   ❌ 候选构建测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        # 步骤4: 测试支撑位检测
        print("\n4️⃣ 测试支撑位检测...")
        try:
            support_result = await builder.analyze_strict_support("002361", -3.11, test_date)
            print(f"   ✅ 支撑检测成功")
            print(f"      has_support: {support_result['has_support']}")
            print(f"      support_strength: {support_result.get('support_strength', 0.0) * 100:.1f}/100")
            print(f"      support_type: {support_result.get('support_type', '')}")
            print(f"      support_count: {support_result.get('support_count', 0)}")
        except Exception as e:
            print(f"   ❌ 支撑检测失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        # 步骤5: 测试完整构建流程（只处理少量股票）
        print("\n5️⃣ 测试完整构建流程（限制5只股票）...")
        try:
            # 获取所有股票
            rows = await builder._fetch_candidate_inputs(test_date)
            print(f"   总股票数: {len(rows)}")

            # 只处理前5只股票
            test_rows = rows[:5]
            test_candidates = []

            for i, row in enumerate(test_rows):
                candidate = await builder._async_to_candidate(row, test_date, test_date)
                if candidate:
                    test_candidates.append(candidate)
                    print(f"   {i+1}. {row.get('stock_id')} {row.get('stock_name')} - "
                          f"✅ 入选 (分数: {candidate.get('candidate_score')})")
                else:
                    print(f"   {i+1}. {row.get('stock_id')} {row.get('stock_name')} - ❌ 过滤")

            print(f"   测试结果: {len(test_candidates)}/{len(test_rows)} 只入选")

        except Exception as e:
            print(f"   ❌ 完整构建流程测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        print("\n" + "=" * 60)
        print("✅ 所有测试步骤完成")
        return True

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await builder.close()

async def main():
    success = await test_step_by_step()
    if success:
        print("\n🎉 候选构建器功能正常")
        return 0
    else:
        print("\n⚠️ 候选构建器存在问题，需要进一步调试")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
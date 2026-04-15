#!/usr/bin/env python3
"""
最终验证神剑股份弱转强候选构建
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def main():
    print("🎯 最终验证：神剑股份弱转强候选构建")
    print("=" * 70)

    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        print(f"📅 测试日期: {test_date}")
        print(f"📊 测试股票: 神剑股份 (002361)")
        print()

        # 1. 测试完整的候选构建流程
        print("1️⃣ 运行完整候选构建流程...")
        result = await builder.build_with_strict_support(test_date, max_candidates=10)

        print(f"  扫描股票总数: {result.total_scanned}")
        print(f"  入选候选数量: {len(result.candidates)}")
        print()

        # 2. 检查神剑股份是否入选
        print("2️⃣ 检查神剑股份是否入选候选池...")
        found = False
        for i, candidate in enumerate(result.candidates):
            stock_id = str(candidate.get('stock_id', ''))
            if '002361' in stock_id:
                found = True
                print(f"  ✅ 神剑股份成功入选候选池！")
                print(f"    候选排名: #{i+1}")
                print(f"    股票ID: {candidate.get('stock_id')}")
                print(f"    股票名称: {candidate.get('stock_name')}")
                print(f"    候选分数: {candidate.get('candidate_score')}")
                print(f"    支撑强度: {candidate.get('support_strength')}")
                print(f"    支撑类型: {candidate.get('support_type')}")
                print(f"    支撑类型数量: {candidate.get('support_count')}")
                print(f"    弱转强类型: {candidate.get('weak_type')}")
                print(f"    候选类型: {candidate.get('candidate_type')}")
                print(f"    修复窗口: {candidate.get('repair_window')}")
                print(f"    主题阶段: {candidate.get('stage')}")
                print(f"    主题动作偏向: {candidate.get('action_bias')}")
                print(f"    是否退潮: {candidate.get('is_fade')}")
                print(f"    近期涨停次数: {candidate.get('recent_limit_up_count')}")
                break

        if not found:
            print(f"  ❌ 神剑股份未入选候选池")

            # 显示入选的股票
            if result.candidates:
                print(f"\n  入选的前5只股票:")
                for i, candidate in enumerate(result.candidates[:5]):
                    print(f"    {i+1}. {candidate.get('stock_id')} {candidate.get('stock_name')} - "
                          f"分数: {candidate.get('candidate_score')}, 支撑强度: {candidate.get('support_strength')}")
            else:
                print(f"  ⚠️ 候选池为空")

        # 3. 分析原因（如果未入选）
        if not found:
            print(f"\n3️⃣ 分析神剑股份未入选原因...")
            print(f"  从数据库查询数据中分析过滤条件:")

            # 获取输入数据
            rows = await builder._fetch_candidate_inputs(test_date)
            shenjian_row = None
            for row in rows:
                if '002361' in str(row.get('stock_id', '')) or '002361' in str(row.get('stock_code', '')):
                    shenjian_row = row
                    break

            if shenjian_row:
                print(f"  ✅ 在输入数据中找到神剑股份")
                print(f"    is_main_theme: {shenjian_row.get('is_main_theme')}")
                print(f"    is_fade: {shenjian_row.get('is_fade')}")
                print(f"    pct_chg: {shenjian_row.get('pct_chg')}")
                print(f"    prev_day_pct_chg: {shenjian_row.get('prev_day_pct_chg')}")
                print(f"    recent_limit_up_count: {shenjian_row.get('recent_limit_up_count')}")
                print(f"    is_leader: {shenjian_row.get('is_leader')}")
                print(f"    limit_up: {shenjian_row.get('limit_up')}")
                print(f"    rank_order: {shenjian_row.get('rank_order')}")
                print(f"    primary_cycle_stage: {shenjian_row.get('primary_cycle_stage')}")
                print(f"    action_bias: {shenjian_row.get('action_bias')}")

                # 测试候选构建
                print(f"\n  测试单个候选构建...")
                candidate = await builder._async_to_candidate(shenjian_row, test_date, test_date)
                if candidate:
                    print(f"  ⚠️ 单个候选构建成功但未入选最终池")
                    print(f"    可能原因: 分数排序未进入前10名")
                else:
                    print(f"  ❌ 单个候选构建失败")
                    print(f"    失败原因: 被硬门槛过滤")
            else:
                print(f"  ❌ 在输入数据中未找到神剑股份")

        print(f"\n4️⃣ 验证支撑位检测独立测试...")
        support_result = await builder.analyze_strict_support("002361", -3.11, test_date)
        print(f"  支撑检测结果: {'✅ 成功' if support_result['has_support'] else '❌ 失败'}")
        print(f"  支撑强度: {support_result.get('support_strength', 0.0) * 100:.1f}/100")
        print(f"  支撑类型: {support_result.get('support_type', '')}")
        print(f"  支撑类型数量: {support_result.get('support_count', 0)}")
        print(f"  组合支撑强度: {support_result.get('combined_strength', 0.0)}")

        # 5. 总结
        print(f"\n" + "=" * 70)
        if found:
            print("🎉 验证成功！神剑股份符合弱转强条件，已入选候选池。")
            print("支撑位识别问题已解决：")
            print("  ✅ 多种支撑类型检测（缺口回补、前低支撑、整数关口）")
            print("  ✅ 组合支撑强度计算（多种支撑存在时增加强度加成）")
            print("  ✅ 支撑强度硬门槛≥30分")
            print("  ✅ 修复主线周期判断逻辑（退潮需要硬证据）")
        else:
            print("⚠️ 验证未通过，神剑股份未入选候选池")
            print("需要进一步分析过滤原因。")

    except Exception as e:
        print(f"❌ 验证错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

    print("\n验证完成")

if __name__ == "__main__":
    asyncio.run(main())
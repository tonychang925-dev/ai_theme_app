#!/usr/bin/env python3
"""
快速验证神剑股份候选构建
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def main():
    print("🔍 快速验证神剑股份候选构建")
    print("=" * 60)

    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        # 1. 测试支撑位检测
        print("1️⃣ 测试支撑位检测...")
        support_result = await builder.analyze_strict_support("002361", 0.0, test_date)
        print(f"  支撑检测: {'✅ 成功' if support_result['has_support'] else '❌ 失败'}")
        print(f"  支撑强度: {support_result.get('support_strength', 0.0) * 100:.1f}/100")
        print(f"  支撑类型: {support_result.get('support_type', '')}")
        print(f"  类型数量: {support_result.get('support_count', 0)}")

        # 2. 获取输入数据
        print("\n2️⃣ 获取输入数据...")
        rows = await builder._fetch_candidate_inputs(test_date)
        print(f"  总记录数: {len(rows)}")

        # 查找神剑股份
        shenjian_row = None
        for row in rows:
            if '002361' in str(row.get('stock_id', '')) or '002361' in str(row.get('stock_code', '')):
                shenjian_row = row
                break

        if shenjian_row:
            print(f"  ✅ 找到神剑股份: {shenjian_row.get('stock_name')}")
            print(f"    is_main_theme: {shenjian_row.get('is_main_theme')}")
            print(f"    is_fade: {shenjian_row.get('is_fade')}")
            print(f"    pct_chg: {shenjian_row.get('pct_chg')}")
            print(f"    recent_limit_up_count: {shenjian_row.get('recent_limit_up_count')}")

            # 3. 测试候选构建
            print("\n3️⃣ 测试候选构建...")
            candidate = await builder._async_to_candidate(shenjian_row, test_date, test_date)

            if candidate:
                print(f"  ✅ 候选构建成功!")
                print(f"    candidate_score: {candidate.get('candidate_score')}")
                print(f"    support_strength: {candidate.get('support_strength')}")
                print(f"    candidate_type: {candidate.get('candidate_type')}")
                print(f"    weak_type: {candidate.get('weak_type')}")

                # 4. 测试完整构建流程
                print("\n4️⃣ 测试完整构建流程...")
                result = await builder.build_with_strict_support(test_date, max_candidates=10)
                print(f"  扫描股票: {result.total_scanned}")
                print(f"  入选候选: {len(result.candidates)}")

                # 查找神剑股份是否入选
                found = any('002361' in str(c.get('stock_id', '')) for c in result.candidates)
                if found:
                    print(f"  🎉 神剑股份入选候选池!")
                    for c in result.candidates:
                        if '002361' in str(c.get('stock_id', '')):
                            print(f"    分数: {c.get('candidate_score')}")
                            print(f"    支撑强度: {c.get('support_strength')}")
                            print(f"    支撑类型: {c.get('support_type')}")
                            break
                else:
                    print(f"  ❌ 神剑股份未入选候选池")
                    print(f"  入选的前3只股票:")
                    for i, c in enumerate(result.candidates[:3]):
                        print(f"    {i+1}. {c.get('stock_id')} {c.get('stock_name')} - 分数: {c.get('candidate_score')}")
            else:
                print("  ❌ 候选构建失败 (返回None)")
        else:
            print("  ❌ 未找到神剑股份在输入数据中")
            print("  前5条记录:")
            for i, row in enumerate(rows[:5]):
                print(f"    {i+1}. {row.get('stock_id')} {row.get('stock_name')} - "
                      f"is_main_theme: {row.get('is_main_theme')}, is_fade: {row.get('is_fade')}")

    except Exception as e:
        print(f"❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

    print("\n" + "=" * 60)
    print("验证完成")

if __name__ == "__main__":
    asyncio.run(main())
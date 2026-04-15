#!/usr/bin/env python3
"""
测试增强版支撑位检测功能
验证多种支撑类型识别和组合强度计算
"""
import asyncio
from datetime import date
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_shenjian_enhanced_support():
    """测试神剑股份的增强支撑位检测"""
    print("测试神剑股份(002361)增强支撑位检测")
    print("=" * 70)

    builder = WeakToStrongCandidateBuilder()

    # 测试日期：4月7日（弱转强发生日）
    test_date = date(2026, 4, 7)
    stock_id = "002361"

    try:
        # 使用增强版支撑位分析
        print(f"分析 {stock_id} 在 {test_date} 的支撑位...")
        support_analysis = await builder.analyze_strict_support(stock_id, 0.0, test_date)

        # 打印结果
        print(f"has_support: {support_analysis.get('has_support')}")
        print(f"support_type: {support_analysis.get('support_type')}")
        print(f"support_strength: {support_analysis.get('support_strength'):.3f} (0.0-1.0)")
        print(f"support_count: {support_analysis.get('support_count')}")
        print(f"primary_type: {support_analysis.get('primary_type')}")
        print(f"combined_strength: {support_analysis.get('combined_strength'):.3f}")
        print(f"is_gap_support: {support_analysis.get('is_gap_support')}")

        # 打印所有支撑类型
        support_types = support_analysis.get('support_types', [])
        print(f"\n检测到的支撑类型 ({len(support_types)} 种):")
        for i, st in enumerate(support_types, 1):
            print(f"  {i}. type: {st.get('type')}, strength: {st.get('strength'):.3f}, "
                  f"level: {st.get('level', 0.0):.2f}, "
                  f"desc: {st.get('description', '')}")

        # 验证神剑股份应有缺口支撑
        gap_support_found = any(st.get('type') == 'gap_support' for st in support_types)
        print(f"\n缺口支撑检测: {'✅ 找到' if gap_support_found else '❌ 未找到'}")

        # 验证多种支撑类型
        if len(support_types) >= 2:
            print(f"✅ 检测到多种支撑类型 ({len(support_types)} 种)")
            print(f"   组合强度: {support_analysis.get('combined_strength', 0.0):.3f}")
            print(f"   应高于单一支撑强度: {support_analysis.get('combined_strength', 0.0) > max(st.get('strength', 0.0) for st in support_types) if support_types else False}")
        else:
            print(f"⚠️  只检测到 {len(support_types)} 种支撑类型")

        # 计算支撑强度分数（0-100）
        support_strength_score = support_analysis.get('support_strength', 0.0) * 100.0
        print(f"\n支撑强度分数: {support_strength_score:.1f}/100")
        print(f"是否≥30分（硬门槛）: {'✅ 是' if support_strength_score >= 30.0 else '❌ 否'}")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def test_zhonganke_enhanced_support():
    """测试中安科的增强支撑位检测"""
    print("\n\n测试中安科(600654)增强支撑位检测")
    print("=" * 70)

    builder = WeakToStrongCandidateBuilder()

    # 测试日期：4月10日（弱转强候选日）
    test_date = date(2026, 4, 10)
    stock_id = "600654"

    try:
        # 使用增强版支撑位分析
        print(f"分析 {stock_id} 在 {test_date} 的支撑位...")
        support_analysis = await builder.analyze_strict_support(stock_id, 0.0, test_date)

        # 打印结果
        print(f"has_support: {support_analysis.get('has_support')}")
        print(f"support_type: {support_analysis.get('support_type')}")
        print(f"support_strength: {support_analysis.get('support_strength'):.3f} (0.0-1.0)")
        print(f"support_count: {support_analysis.get('support_count')}")
        print(f"primary_type: {support_analysis.get('primary_type')}")
        print(f"combined_strength: {support_analysis.get('combined_strength'):.3f}")
        print(f"is_gap_support: {support_analysis.get('is_gap_support')}")

        # 打印所有支撑类型
        support_types = support_analysis.get('support_types', [])
        print(f"\n检测到的支撑类型 ({len(support_types)} 种):")
        for i, st in enumerate(support_types, 1):
            print(f"  {i}. type: {st.get('type')}, strength: {st.get('strength'):.3f}, "
                  f"level: {st.get('level', 0.0):.2f}, "
                  f"desc: {st.get('description', '')}")

        # 计算支撑强度分数
        support_strength_score = support_analysis.get('support_strength', 0.0) * 100.0
        print(f"\n支撑强度分数: {support_strength_score:.1f}/100")
        print(f"是否≥30分（硬门槛）: {'✅ 是' if support_strength_score >= 30.0 else '❌ 否'}")

        # 分析中安科是否应有有效支撑
        if support_strength_score >= 30.0:
            print("✅ 中安科应有有效支撑位，符合弱转强条件")
        else:
            print("❌ 中安科支撑强度不足，可能被过滤")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def test_candidate_building():
    """测试完整的候选构建流程"""
    print("\n\n测试完整候选构建流程（4月7日）")
    print("=" * 70)

    builder = WeakToStrongCandidateBuilder()

    test_date = date(2026, 4, 7)

    try:
        # 使用严格支撑位分析的构建器
        print(f"构建 {test_date} 的弱转强候选池（使用严格支撑分析）...")
        result = await builder.build_with_strict_support(test_date, max_candidates=10)

        print(f"扫描股票数: {result.total_scanned}")
        print(f"入选候选数: {len(result.candidates)}")

        # 查找神剑股份
        shenjian_found = False
        for candidate in result.candidates:
            if candidate.get('stock_id') in ['002361', '002361.SZ']:
                shenjian_found = True
                print(f"\n✅ 神剑股份入选候选池!")
                print(f"  候选分数: {candidate.get('candidate_score')}")
                print(f"  支撑类型: {candidate.get('support_type')}")
                print(f"  支撑强度: {candidate.get('support_strength')}")
                print(f"  支撑水平: {candidate.get('support_level')}")

                # 解析证据JSON
                import json
                evidence = json.loads(candidate.get('evidence_json', '{}'))
                support_count = evidence.get('inputs', {}).get('support_count', 0)
                support_types = evidence.get('inputs', {}).get('support_types', [])
                print(f"  支撑类型数量: {support_count}")
                print(f"  详细支撑类型: {support_types}")
                break

        if not shenjian_found:
            print(f"\n❌ 神剑股份未入选候选池")
            print(f"入选的候选股:")
            for i, c in enumerate(result.candidates[:5], 1):
                print(f"{i}. {c.get('stock_id')} {c.get('stock_name')} - "
                      f"分数:{c.get('candidate_score')} 支撑:{c.get('support_strength')}")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def test_async_to_candidate_detailed():
    """详细测试神剑股份在_async_to_candidate方法中的处理"""
    print("\n\n详细测试_async_to_candidate方法 - 神剑股份(002361)")
    print("=" * 70)

    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        # 首先获取神剑股份的输入数据
        rows = await builder._fetch_candidate_inputs(test_date)

        print(f"获取到 {len(rows)} 条股票输入数据")

        # 查找神剑股份
        shenjian_row = None
        for row in rows:
            stock_code = str(row.get("stock_code", ""))
            stock_id = str(row.get("stock_id", ""))
            if "002361" in stock_code or "002361" in stock_id:
                shenjian_row = row
                print(f"找到神剑股份: {stock_id}, {stock_code}")
                break

        if shenjian_row:
            print("\n神剑股份的输入数据:")
            print(f"  stock_id: {shenjian_row.get('stock_id')}")
            print(f"  stock_name: {shenjian_row.get('stock_name')}")
            print(f"  subject_key: {shenjian_row.get('subject_key')}")
            print(f"  theme_name: {shenjian_row.get('theme_name')}")
            print(f"  is_main_theme: {shenjian_row.get('is_main_theme')}")
            print(f"  is_fade: {shenjian_row.get('is_fade')}")
            print(f"  primary_cycle_stage: {shenjian_row.get('primary_cycle_stage')}")
            print(f"  action_bias: {shenjian_row.get('action_bias')}")
            print(f"  is_leader: {shenjian_row.get('is_leader')}")
            print(f"  limit_up: {shenjian_row.get('limit_up')}")
            print(f"  pct_chg: {shenjian_row.get('pct_chg')}")
            print(f"  rank_order: {shenjian_row.get('rank_order')}")
            print(f"  recent_limit_up_count: {shenjian_row.get('recent_limit_up_count')}")
            print(f"  prev_day_pct_chg: {shenjian_row.get('prev_day_pct_chg')}")
            print(f"  prev_day_limit_up: {shenjian_row.get('prev_day_limit_up')}")

            # 测试_async_to_candidate方法
            print("\n调用_async_to_candidate方法...")
            candidate = await builder._async_to_candidate(shenjian_row, test_date, test_date)

            if candidate:
                print("✅ 神剑股份成功构建为候选!")
                print(f"  candidate_score: {candidate.get('candidate_score')}")
                print(f"  support_strength: {candidate.get('support_strength')}")
                print(f"  support_type: {candidate.get('support_type')}")
                print(f"  candidate_type: {candidate.get('candidate_type')}")
                print(f"  weak_type: {candidate.get('weak_type')}")
                print(f"  weak_intensity: {candidate.get('weak_intensity')}")

                # 解析证据JSON
                import json
                evidence = json.loads(candidate.get('evidence_json', '{}'))
                support_count = evidence.get('inputs', {}).get('support_count', 0)
                support_types = evidence.get('inputs', {}).get('support_types', [])
                primary_support_type = evidence.get('inputs', {}).get('primary_support_type', '')
                combined_strength = evidence.get('inputs', {}).get('combined_strength', 0.0)
                print(f"  support_count: {support_count}")
                print(f"  support_types: {support_types}")
                print(f"  primary_support_type: {primary_support_type}")
                print(f"  combined_strength: {combined_strength}")

                # 检查硬门槛
                strong_background = candidate.get('is_leader', False) or candidate.get('limit_up', False) or candidate.get('prev_limit_up_count', 0) >= 2
                print(f"  strong_background检查: {strong_background}")

                # 检查repair_window
                stage = str(shenjian_row.get('primary_cycle_stage', '')).lower()
                action_bias = str(shenjian_row.get('action_bias', ''))
                is_divergence = bool(shenjian_row.get('is_divergence', False))
                is_rebound = bool(shenjian_row.get('is_rebound', False))
                is_fermentation = bool(shenjian_row.get('is_fermentation', False))
                is_fade = bool(shenjian_row.get('is_fade', False))

                repair_window = (
                    ("弱转强" in action_bias)
                    or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"}
                    or is_divergence
                    or is_rebound
                    or is_fermentation
                )
                if is_fade:
                    repair_window = False
                print(f"  repair_window检查: {repair_window}")
                print(f"  is_fade: {is_fade}")
            else:
                print("❌ 神剑股份未被构建为候选（返回None）")

                # 尝试手动检查各个过滤条件
                print("\n手动检查过滤条件:")

                pct_chg = float(shenjian_row.get("pct_chg") or 0.0)
                is_leader = bool(shenjian_row.get("is_leader") or False)
                limit_up = bool(shenjian_row.get("limit_up") or False)
                rank_order = int(shenjian_row.get("rank_order") or 999)
                recent_limit_up_count = int(shenjian_row.get("recent_limit_up_count") or 0)
                prev_day_pct = float(shenjian_row.get("prev_day_pct_chg") or 0.0)
                prev_day_limit_up = bool(shenjian_row.get("prev_day_limit_up") or False)

                stage = str(shenjian_row.get("primary_cycle_stage") or "").lower()
                action_bias = str(shenjian_row.get("action_bias") or "")
                is_divergence = bool(shenjian_row.get("is_divergence") or False)
                is_rebound = bool(shenjian_row.get("is_rebound") or False)
                is_fermentation = bool(shenjian_row.get("is_fermentation") or False)
                is_fade = bool(shenjian_row.get("is_fade") or False)

                # 硬门槛1：强势背景
                strong_background = (
                    is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3
                )
                print(f"  1. strong_background: {strong_background}")
                print(f"     is_leader: {is_leader}")
                print(f"     limit_up: {limit_up}")
                print(f"     recent_limit_up_count >= 2: {recent_limit_up_count >= 2} ({recent_limit_up_count})")
                print(f"     rank_order <= 3: {rank_order <= 3} ({rank_order})")

                # 硬门槛2：分歧修复窗口
                repair_window = (
                    ("弱转强" in action_bias)
                    or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"}
                    or is_divergence
                    or is_rebound
                    or is_fermentation
                )
                if is_fade:
                    repair_window = False
                print(f"  2. repair_window: {repair_window}")
                print(f"     stage: {stage}")
                print(f"     action_bias: {action_bias}")
                print(f"     is_divergence: {is_divergence}")
                print(f"     is_rebound: {is_rebound}")
                print(f"     is_fermentation: {is_fermentation}")
                print(f"     is_fade: {is_fade}")

                # 检查支撑位
                print(f"\n  3. 支撑位检查:")
                stock_id = builder._normalize_stock_id(str(shenjian_row.get("stock_id") or ""), str(shenjian_row.get("stock_code") or ""))
                support_analysis = await builder.analyze_strict_support(stock_id, pct_chg, test_date)
                print(f"     has_support: {support_analysis.get('has_support')}")
                print(f"     support_strength: {support_analysis.get('support_strength', 0.0)}")
                print(f"     support_types: {[st.get('type') for st in support_analysis.get('support_types', [])]}")
                print(f"     support_count: {support_analysis.get('support_count', 0)}")

        else:
            print("❌ 未在输入数据中找到神剑股份")
            print(f"可能的主题过滤原因：is_main_theme = FALSE")
            print(f"前5条股票数据:")
            for i, row in enumerate(rows[:5]):
                print(f"{i+1}. {row.get('stock_id')} {row.get('stock_name')} - is_main_theme: {row.get('is_main_theme')}, is_fade: {row.get('is_fade')}")

    except Exception as e:
        print(f"❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

async def main():
    """主测试函数"""
    print("开始测试增强版支撑位检测功能")
    print("=" * 70)

    await test_shenjian_enhanced_support()
    await test_zhonganke_enhanced_support()
    await test_candidate_building()
    await test_async_to_candidate_detailed()

    print("\n" + "=" * 70)
    print("测试完成")

if __name__ == "__main__":
    asyncio.run(main())
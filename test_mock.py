#!/usr/bin/env python3
"""
使用模拟数据测试神剑股份候选构建
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_with_mock_data():
    print("🧪 使用模拟数据测试神剑股份候选构建")
    print("=" * 60)

    builder = WeakToStrongCandidateBuilder()
    test_date = date(2026, 4, 7)

    try:
        # 基于数据库查询结果创建模拟数据
        # 字段名必须与_fetch_candidate_inputs返回的一致
        mock_row = {
            'stock_code': '002361',
            'stock_id': '002361',
            'stock_name': '神剑股份',
            'subject_key': '9062832',
            'theme_name': '化工',
            'rank_order': 12,
            'pct_chg': -3.11,
            'limit_up': False,
            'is_leader': False,
            'primary_cycle_stage': 'fade',
            'action_bias': '放弃',
            'is_divergence': False,
            'is_rebound': False,
            'is_fermentation': False,
            'is_fade': True,
            'is_main_theme': False,
            'recent_limit_up_count': 4,
            'prev_day_pct_chg': -8.9647,
            'prev_day_limit_up': False
        }

        print("📊 模拟数据:")
        for key, value in mock_row.items():
            print(f"  {key}: {value}")

        print("\n1️⃣ 测试候选构建...")
        candidate = await builder._async_to_candidate(mock_row, test_date, test_date)

        if candidate:
            print("✅ 候选构建成功!")
            print(f"  candidate_score: {candidate.get('candidate_score')}")
            print(f"  support_strength: {candidate.get('support_strength')}")
            print(f"  support_type: {candidate.get('support_type')}")
            print(f"  support_count: {candidate.get('support_count')}")
            print(f"  weak_type: {candidate.get('weak_type')}")
            print(f"  candidate_type: {candidate.get('candidate_type')}")
            print(f"  repair_window: {candidate.get('repair_window')}")
            print(f"  stage: {candidate.get('stage')}")
            print(f"  action_bias: {candidate.get('action_bias')}")
            print(f"  is_fade: {candidate.get('is_fade')}")

            # 验证硬门槛
            print("\n✅ 所有硬门槛验证:")
            print(f"  1. 强势背景: {candidate.get('strong_background', False)}")
            print(f"  2. 修复窗口: {candidate.get('repair_window', False)}")
            print(f"  3. 支撑强度≥30: {candidate.get('support_strength', 0) >= 30}")

            return True
        else:
            print("❌ 候选构建失败 (返回None)")

            # 手动检查门槛
            print("\n🔍 手动检查硬门槛:")
            pct_chg = mock_row['pct_chg']
            prev_day_pct = mock_row['prev_day_pct_chg']
            is_leader = mock_row['is_leader']
            limit_up = mock_row['limit_up']
            rank_order = mock_row['rank_order']
            recent_limit_up_count = mock_row['recent_limit_up_count']
            stage = mock_row['primary_cycle_stage']
            action_bias = mock_row['action_bias']
            is_divergence = mock_row['is_divergence']
            is_rebound = mock_row['is_rebound']
            is_fermentation = mock_row['is_fermentation']

            # 强势背景
            strong_background = (
                is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3
            )
            print(f"  1. 强势背景: {strong_background}")
            print(f"     recent_limit_up_count={recent_limit_up_count} >=2: {recent_limit_up_count >= 2}")

            # 修复窗口
            repair_window = (
                ('弱转强' in action_bias) or
                stage in {'divergence', 'rebound', 'fermentation', '分歧', '回流', '发酵', '启动'} or
                is_divergence or is_rebound or is_fermentation or
                (recent_limit_up_count >= 2 and pct_chg < 0)
            )
            print(f"  2. 修复窗口: {repair_window}")
            print(f"     recent_limit_up_count >= 2 and pct_chg < 0: {recent_limit_up_count >= 2 and pct_chg < 0}")

            # 支撑强度
            print(f"  3. 支撑强度: 单独测试...")
            try:
                support_result = await builder.analyze_strict_support("002361", pct_chg, test_date)
                print(f"     has_support: {support_result['has_support']}")
                print(f"     support_strength: {support_result.get('support_strength', 0.0) * 100:.1f}/100")
                print(f"     >=30: {support_result.get('support_strength', 0.0) * 100 >= 30}")
            except Exception as e:
                print(f"     支撑检测错误: {e}")

            return False

    except Exception as e:
        print(f"❌ 测试错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await builder.close()

async def main():
    success = await test_with_mock_data()
    if success:
        print("\n" + "=" * 60)
        print("🎉 神剑股份候选构建逻辑验证成功!")
        print("   支撑位识别问题已解决，候选构建逻辑正确。")
        print("   问题可能在于数据库查询或数据缺失。")
        return 0
    else:
        print("\n" + "=" * 60)
        print("⚠️ 候选构建逻辑存在问题，需要进一步调试。")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
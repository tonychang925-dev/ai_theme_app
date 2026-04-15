#!/usr/bin/env python3
"""
测试严格支撑位分析集成
测试神剑股份(002361)在4月3日和4月7日的表现
"""
import asyncio
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_shenjian_strict_support():
    """测试神剑股份的严格支撑位分析"""
    builder = WeakToStrongCandidateBuilder()

    test_cases = [
        (date(2026, 4, 3), "❌ 应该被拒绝（支撑强度不足）"),
        (date(2026, 4, 7), "✅ 应该被选中（弱转强候选）")
    ]

    try:
        for trade_date, expected in test_cases:
            print(f"\n{'='*70}")
            print(f"测试神剑股份 - {trade_date}")
            print(f"预期: {expected}")
            print(f"{'='*70}")

            # 使用新的严格支撑位分析方法
            result = await builder.build_with_strict_support(trade_date, max_candidates=20)

            # 查找神剑股份
            found = False
            for candidate in result.candidates:
                stock_id = candidate.get("stock_id")
                if stock_id == "002361" or stock_id == "002361.SZ":
                    found = True
                    print(f"✅ 神剑股份入选候选池!")
                    print(f"  支撑类型: {candidate.get('support_type')}")
                    print(f"  支撑强度: {candidate.get('support_strength')}")
                    print(f"  候选分数: {candidate.get('candidate_score')}")
                    print(f"  弱势类型: {candidate.get('weak_type')}")
                    print(f"  弱势强度: {candidate.get('weak_intensity')}")
                    break

            if not found:
                print(f"❌ 神剑股份未入选候选池")

                # 显示入选的候选股
                if result.candidates:
                    print(f"入选的前{min(5, len(result.candidates))}只股票:")
                    for i, c in enumerate(result.candidates[:5], 1):
                        print(f"{i}. {c.get('stock_id')} {c.get('stock_name')} - "
                              f"支撑:{c.get('support_strength')} 分数:{c.get('candidate_score')}")
                else:
                    print("没有股票入选候选池")

            print(f"扫描: {result.total_scanned}, 选中: {len(result.candidates)}")

    finally:
        await builder.close()

async def main():
    """主测试函数"""
    print("开始测试严格支撑位分析集成...")
    print("=" * 70)

    try:
        await test_shenjian_strict_support()
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
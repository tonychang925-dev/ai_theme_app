#!/usr/bin/env python3
"""
弱转强算法集成测试 - 验证优化方案接入实际项目代码
测试神剑股份在2026-04-07是否出现在候选池中
"""
import asyncio
import sys
from datetime import date
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test_integration():
    print("🚀 弱转强算法集成测试")
    print("=" * 60)

    builder = WeakToStrongCandidateBuilder()
    trade_date = date(2026, 4, 7)

    try:
        print(f"使用build_with_strict_support构建候选池 - {trade_date}")
        result = await builder.build_with_strict_support(
            trade_date,
            max_candidates=100
        )

        print(f"📊 构建结果:")
        print(f"  扫描股票数: {result.total_scanned}")
        print(f"  插入候选数: {result.total_inserted}")

        # 查找神剑股份
        shenjian_found = False
        for candidate in result.candidates:
            stock_id = candidate.get('stock_id', '')
            if '002361' in stock_id:
                shenjian_found = True
                print(f"\n✅ 神剑股份出现在候选池中!")
                print(f"  stock_id: {candidate.get('stock_id')}")
                print(f"  stock_name: {candidate.get('stock_name')}")
                print(f"  candidate_score: {candidate.get('candidate_score')}")
                print(f"  support_strength: {candidate.get('support_strength')}")
                print(f"  support_type: {candidate.get('support_type')}")
                print(f"  weak_type: {candidate.get('weak_type')}")
                print(f"  candidate_type: {candidate.get('candidate_type')}")
                break

        if not shenjian_found:
            print(f"\n❌ 神剑股份未出现在候选池中")
            # 打印前几个候选以了解情况
            print(f"  前5个候选:")
            for i, c in enumerate(result.candidates[:5]):
                print(f"    {i+1}. {c.get('stock_id')} {c.get('stock_name')} 分数:{c.get('candidate_score')}")

        # 验证4月3日被拒绝
        print(f"\n" + "=" * 60)
        print(f"验证4月3日神剑股份被拒绝")
        trade_date_reject = date(2026, 4, 3)
        result_reject = await builder.build_with_strict_support(
            trade_date_reject,
            max_candidates=100
        )

        shenjian_reject = False
        for candidate in result_reject.candidates:
            stock_id = candidate.get('stock_id', '')
            if '002361' in stock_id:
                shenjian_reject = True
                print(f"❌ 神剑股份错误出现在4月3日候选池中")
                print(f"  候选分数: {candidate.get('candidate_score')}")
                break

        if not shenjian_reject:
            print(f"✅ 神剑股份正确未出现在4月3日候选池中")

        return shenjian_found and not shenjian_reject

    except Exception as e:
        print(f"❌ 集成测试错误: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await builder.close()

async def main():
    success = await test_integration()
    if success:
        print(f"\n" + "=" * 60)
        print("🎉 弱转强算法集成测试成功!")
        print("   优化方案已正确接入实际项目代码。")
        return 0
    else:
        print(f"\n" + "=" * 60)
        print("⚠️ 弱转强算法集成测试失败，需要进一步调试。")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
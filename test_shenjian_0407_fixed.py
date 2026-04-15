#!/usr/bin/env python3
"""
测试神剑股份(002361)在4月7日的弱转强候选表现（修复空周期状态后）
"""
import asyncio
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def test_shenjian():
    """测试神剑股份弱转强候选"""
    builder = EnhancedCandidateBuilder()

    trade_date = date(2026, 4, 7)

    print(f"测试神剑股份(002361)弱转强候选 - {trade_date}")
    print("=" * 70)

    try:
        # 使用增强版构建器
        result = await builder.build_enhanced(trade_date, max_formal=20, max_observe=10)

        # 查找神剑股份
        found = False
        for candidate in result.candidates:
            stock_id = candidate.get("stock_id")
            if stock_id == "002361" or stock_id == "002361.SZ":
                found = True
                print(f"✅ 神剑股份入选候选池!")
                print(f"  pool_entry_type: {candidate.get('pool_entry_type')}")
                print(f"  支撑类型: {candidate.get('support_type')}")
                print(f"  支撑强度: {candidate.get('support_strength')}")
                print(f"  候选分数: {candidate.get('candidate_score')}")
                print(f"  弱势类型: {candidate.get('weak_type')}")
                print(f"  弱势强度: {candidate.get('weak_intensity')}")
                print(f"  主线强度分数: {candidate.get('mainline_strength_score')}")
                print(f"  退潮观察: {candidate.get('fade_watch')}")
                print(f"  退潮确认: {candidate.get('fade_confirmed')}")

                # 打印增强特征
                evidence_json = candidate.get("evidence_json", "{}")
                import json
                try:
                    evidence = json.loads(evidence_json)
                    if "enhanced_features" in evidence:
                        print(f"  增强特征: {json.dumps(evidence['enhanced_features'], ensure_ascii=False, indent=2)}")
                except:
                    pass
                break

        if not found:
            print(f"❌ 神剑股份未入选候选池")

            # 显示入选的候选股
            if result.candidates:
                print(f"入选的候选股 ({len(result.candidates)} 只):")
                for i, c in enumerate(result.candidates[:10], 1):
                    print(f"{i}. {c.get('stock_id')} {c.get('stock_name')} - "
                          f"类型:{c.get('pool_entry_type')} 支撑:{c.get('support_strength')} "
                          f"分数:{c.get('candidate_score')}")
            else:
                print("没有股票入选候选池")

        print(f"扫描: {result.total_scanned}, 正式候选: {len([c for c in result.candidates if c.get('pool_entry_type') == 'formal'])}, "
              f"观察候选: {len([c for c in result.candidates if c.get('pool_entry_type') == 'observe_only'])}")

    finally:
        await builder.close()

async def main():
    """主测试函数"""
    print("开始测试神剑股份弱转强候选（修复空周期状态后）...")
    print("=" * 70)

    try:
        await test_shenjian()
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
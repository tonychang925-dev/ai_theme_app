#!/usr/bin/env python3
"""
测试2026-04-07神剑股份弱转强筛选
"""
import asyncio
import sys
import os
from datetime import date
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from real_weak_to_strong_screening_enhanced import RealDatabaseScreener

async def test_shenjian_screening():
    """测试神剑股份弱转强筛选"""
    print("测试神剑股份弱转强筛选 - 2026-04-07")
    print("=" * 70)

    trade_date = date(2026, 4, 7)
    screener = RealDatabaseScreener()

    try:
        # 运行筛选
        result = await screener.run_screening(trade_date, stock_limit=200)

        print(f"\n{'='*70}")
        print("筛选完成！")
        print(f"{'='*70}")

        # 检查是否找到神剑股份
        shenjian_found = False
        shenjian_data = None

        for candidate in result['candidates']:
            if candidate['stock_id'] == "002361":
                shenjian_found = True
                shenjian_data = candidate
                break

        if shenjian_found:
            print(f"✅ 成功识别神剑股份为弱转强候选")
            print(f"\n神剑股份弱转强详情:")
            print(f"  股票: {shenjian_data['stock_name']} ({shenjian_data['stock_id']})")
            print(f"  主题: {shenjian_data['theme_name']}")
            print(f"  强势股评分: {shenjian_data.get('strong_stock_overall_score', 0):.1f}/100")
            print(f"  弱转强评分: {shenjian_data['weak_to_strong_score']:.1f}/100")
            print(f"  前一日: {shenjian_data.get('prev_pct_chg', 'N/A'):.2f}% → 今日: {shenjian_data.get('today_pct_chg', 'N/A'):.2f}%")
            print(f"  信号类型: {shenjian_data.get('signal_type', 'N/A')}")
            print(f"  置信度: {shenjian_data.get('confidence', 0):.1f}%")

            # 检查是否高评分候选
            if shenjian_data['weak_to_strong_score'] >= 70.0:
                print(f"\n  ✅ 高评分弱转强候选（评分 >= 70）")
            else:
                print(f"\n  ⚠️  弱转强评分较低（{shenjian_data['weak_to_strong_score']:.1f}/100）")
        else:
            print(f"❌ 未识别神剑股份为弱转强候选")

            # 显示找到的候选（如果有）
            if result['candidates']:
                print(f"\n找到 {len(result['candidates'])} 个弱转强候选:")
                for i, candidate in enumerate(result['candidates'][:5]):
                    print(f"  {i+1}. {candidate['stock_name']} ({candidate['stock_id']}): 评分{candidate['weak_to_strong_score']:.1f}")
            else:
                print(f"\n未找到任何弱转强候选")

        # 统计信息
        print(f"\n统计信息:")
        print(f"   分析股票数量: {result.get('total_stocks_analyzed', 0)}")
        print(f"   弱转强候选数量: {len(result['candidates'])}")

        if result['candidates']:
            avg_score = sum(c['weak_to_strong_score'] for c in result['candidates']) / len(result['candidates'])
            print(f"   平均弱转强评分: {avg_score:.1f}/100")

        return shenjian_found

    except Exception as e:
        print(f"筛选过程出现错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    found = asyncio.run(test_shenjian_screening())
    print(f"\n测试结果: {'成功识别神剑股份' if found else '未识别神剑股份'}")
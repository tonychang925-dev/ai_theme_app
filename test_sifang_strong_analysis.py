#!/usr/bin/env python3
"""
测试四方精创的强势股分析服务
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from datetime import date

async def test_sifang_analysis():
    """测试四方精创分析"""
    service = StrongStockAnalysisService()

    # 测试四方精创
    stock_id = "300468"
    test_date = date(2026, 4, 10)

    print(f"测试四方精创强势股分析服务")
    print(f"股票: {stock_id}")
    print(f"日期: {test_date}")
    print("=" * 70)

    try:
        # 执行分析
        analysis = await service.analyze_stock_by_pdf_framework(stock_id, test_date)

        print(f"股票名称: {analysis.get('stock_name', 'N/A')}")
        print(f"是否为强势股: {'✅ 是' if analysis['is_strong_stock'] else '❌ 否'}")
        print(f"总体评分: {analysis['overall_score']}/100")

        print(f"\n维度分析:")
        for dim_name, dim_data in analysis['dimensions'].items():
            score = dim_data.get('score', 0)
            print(f"\n{dim_name}: {score}分")

            # 打印原因
            if 'reasons' in dim_data and dim_data['reasons']:
                print(f"  原因:")
                for reason in dim_data['reasons'][:3]:  # 最多显示3个原因
                    print(f"    - {reason}")

            # 打印额外信息
            if dim_name == '是否正宗':
                print(f"  主题: {dim_data.get('theme_name', 'N/A')}")
            elif dim_name == '资金性质':
                print(f"  资金类型: {dim_data.get('capital_type', 'N/A')}")
                if dim_data.get('capital_details'):
                    print(f"  资金详情: {dim_data.get('capital_details')}")
            elif dim_name == '技术形态':
                print(f"  形态: {dim_data.get('pattern', 'N/A')}")
                if dim_data.get('technical_signals'):
                    print(f"  技术信号:")
                    for signal in dim_data.get('technical_signals', [])[:3]:
                        print(f"    - {signal}")
            elif dim_name == '龙头属性':
                print(f"  是否龙头: {dim_data.get('is_leader', 'N/A')}")
                print(f"  排名顺序: {dim_data.get('rank_order', 'N/A')}")
                print(f"  龙头级别: {dim_data.get('dragon_head_level', 'N/A')}")

        if analysis['strengths']:
            print(f"\n✅ 优点:")
            for strength in analysis['strengths']:
                print(f"  {strength}")

        if analysis['weaknesses']:
            print(f"\n⚠️  弱点:")
            for weakness in analysis['weaknesses']:
                print(f"  {weakness}")

        # 检查是否符合强势股条件
        print(f"\n强势股判断标准检查:")
        print(f"  1. 总体评分 >= 60: {analysis['overall_score']} >= 60 => {analysis['overall_score'] >= 60}")

        dragon_head_score = analysis['dimensions'].get('龙头属性', {}).get('score', 0)
        print(f"  2. 龙头属性评分 >= 50: {dragon_head_score} >= 50 => {dragon_head_score >= 50}")

        lingzhang_score = analysis['dimensions'].get('是否领涨', {}).get('score', 0)
        print(f"  3. 是否领涨评分 >= 40: {lingzhang_score} >= 40 => {lingzhang_score >= 40}")

        print(f"  结论: {'符合强势股条件' if analysis['is_strong_stock'] else '不符合强势股条件'}")

    except Exception as e:
        print(f"分析失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await service.close()
        print("\n测试完成")

if __name__ == "__main__":
    asyncio.run(test_sifang_analysis())
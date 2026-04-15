#!/usr/bin/env python3
"""
测试增强版的强势股分析服务
"""
import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from stock_service.services.strong_stock_analysis_service import StrongStockAnalysisService
from datetime import date

async def test_enhanced_analysis():
    """测试增强版分析"""
    service = StrongStockAnalysisService()

    # 测试神剑股份
    stock_id = "002361"
    test_date = date(2026, 4, 10)

    print(f"测试增强版强势股分析服务")
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

        if analysis['strengths']:
            print(f"\n✅ 优点:")
            for strength in analysis['strengths']:
                print(f"  {strength}")

        if analysis['weaknesses']:
            print(f"\n⚠️  弱点:")
            for weakness in analysis['weaknesses']:
                print(f"  {weakness}")

    except Exception as e:
        print(f"分析失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await service.close()
        print("\n测试完成")

if __name__ == "__main__":
    asyncio.run(test_enhanced_analysis())
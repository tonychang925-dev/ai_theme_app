#!/usr/bin/env python3
"""
event_extractor.py 简化测试 - 不依赖pytest
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import Mock, AsyncMock

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

async def test_event_extractor():
    """测试event_extractor的基本功能"""
    print("🧪 测试 event_extractor.py 数据完整性保存")
    print("="*60)
    
    # 创建模拟的LLM解析器
    mock_llm_parser = Mock()
    mock_llm_parser.parse_news = AsyncMock()
    mock_llm_parser.health_check = AsyncMock(return_value=True)
    
    # 模拟AI响应
    mock_ai_response = {
        "event_info": {
            "event_type": "技术突破",
            "summary": "某公司发布了新一代AI模型，性能提升30%，在多项基准测试中表现优异",
            "impact_industries": ["人工智能", "软件", "云计算"],
            "direction": "利好",
            "confidence": 0.85
        },
        "theme_discovery_directive": {
            "action": "CLUSTER",
            "confidence": 0.8,
            "reason": "重要技术突破，可能影响多个行业"
        }
    }
    
    mock_llm_parser.parse_news.return_value = mock_ai_response
    
    # 导入并创建提取器
    from model_service.service.event_extractor import AIEventExtractor
    extractor = AIEventExtractor(mock_llm_parser)
    
    # 测试数据
    test_news = {
        'news_id': 'test_001',
        'title': '某AI公司发布新一代大模型，性能提升30%',
        'content': '''某AI科技公司今日在北京正式发布了新一代人工智能大模型"DeepMind-X"。
该模型在多项国际基准测试中取得了突破性成绩，相比上一代产品性能提升了30%。
核心技术包括创新的注意力机制和高效的训练算法。
公司CEO表示，这一突破将推动AI技术在医疗、金融、教育等领域的应用。
市场分析师预计，该技术将带动相关产业链的发展，包括芯片、云计算、软件服务等。
发布会吸引了来自全球的科技媒体和投资者关注。'''
    }
    
    print("测试用例: 长内容新闻")
    print(f"  标题: {test_news['title']}")
    print(f"  内容长度: {len(test_news['content'])}字符")
    
    # 执行提取
    result = await extractor.extract_event(test_news)
    
    # 验证结果
    tests_passed = []
    tests_failed = []
    
    # 1. 检查结果不为空
    if result is not None:
        tests_passed.append("提取结果不为空")
    else:
        tests_failed.append("提取结果为空")
    
    # 2. 检查是否保存了原始数据
    if 'original_data' in result:
        tests_passed.append("保存了original_data")
        
        # 检查具体字段
        od = result['original_data']
        if od.get('title') == test_news['title']:
            tests_passed.append("正确保存了标题")
        else:
            tests_failed.append(f"标题保存错误: {od.get('title')}")
            
        if 'content' in od and od['content']:
            tests_passed.append("保存了完整内容")
            print(f"  保存的内容长度: {len(od['content'])}字符")
        else:
            tests_failed.append("未保存完整内容")
            
        if od.get('content_length') == len(test_news['content']):
            tests_passed.append("正确计算了内容长度")
        else:
            tests_failed.append(f"内容长度计算错误: {od.get('content_length')}")
    else:
        tests_failed.append("未保存original_data")
    
    # 3. 检查数据完整性标记
    if 'data_integrity' in result:
        tests_passed.append("有data_integrity标记")
        
        di = result['data_integrity']
        if di.get('has_content'):
            tests_passed.append("标记有内容")
        else:
            tests_failed.append("标记无内容")
            
        if di.get('content_length') == len(test_news['content']):
            tests_passed.append("正确标记内容长度")
    else:
        tests_failed.append("无data_integrity标记")
    
    # 4. 检查AI响应保存
    if 'ai_response' in result:
        tests_passed.append("保存了完整AI响应")
    else:
        tests_failed.append("未保存AI响应")
    
    # 打印测试结果
    print(f"\n📊 测试结果: 通过 {len(tests_passed)}/{len(tests_passed)+len(tests_failed)}")
    
    if tests_passed:
        print("\n✅ 通过的测试:")
        for test in tests_passed:
            print(f"  ✓ {test}")
    
    if tests_failed:
        print("\n❌ 失败的测试:")
        for test in tests_failed:
            print(f"  ✗ {test}")
    
    print("\n" + "="*60)
    
    if len(tests_failed) == 0:
        print("🎉 event_extractor 测试通过！")
        return True
    else:
        print("⚠️  event_extractor 测试失败")
        return False

async def test_short_content():
    """测试短内容处理"""
    print("\n🧪 测试短内容处理")
    print("="*60)
    
    from model_service.service.event_extractor import AIEventExtractor
    from unittest.mock import Mock, AsyncMock
    
    mock_llm_parser = Mock()
    mock_llm_parser.parse_news = AsyncMock(return_value={
        "event_info": {
            "event_type": "产品发布",
            "summary": "新产品发布",
            "impact_industries": ["消费电子"],
            "direction": "中性",
            "confidence": 0.7
        },
        "theme_discovery_directive": {
            "action": "CLUSTER",
            "confidence": 0.6,
            "reason": "常规产品更新"
        }
    })
    
    extractor = AIEventExtractor(mock_llm_parser)
    
    # 短内容测试
    test_news = {
        'news_id': 'test_short',
        'title': '新产品发布',
        'content': '短内容'
    }
    
    print(f"测试短内容: {test_news['content']} ({len(test_news['content'])}字符)")
    
    result = await extractor.extract_event(test_news)
    
    if result and result['data_integrity']['content_length'] == 3:
        print("✅ 短内容处理正确")
        return True
    else:
        print("❌ 短内容处理错误")
        return False

async def main():
    """主测试函数"""
    print("🚀 event_extractor 单元测试套件")
    print("测试时间: 2026-01-13")
    print("="*60)
    
    test_results = []
    
    # 运行测试
    try:
        result1 = await test_event_extractor()
        test_results.append(("长内容测试", result1))
    except Exception as e:
        print(f"💥 长内容测试异常: {e}")
        import traceback
        traceback.print_exc()
        test_results.append(("长内容测试", False))
    
    try:
        result2 = await test_short_content()
        test_results.append(("短内容测试", result2))
    except Exception as e:
        print(f"💥 短内容测试异常: {e}")
        test_results.append(("短内容测试", False))
    
    # 汇总结果
    print("\n" + "="*60)
    print("📋 测试汇总:")
    
    all_passed = True
    for test_name, passed in test_results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {test_name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + "="*60)
    if all_passed:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️  有测试失败，请检查代码")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

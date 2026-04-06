#!/usr/bin/env python3
"""
修复后的集成测试
"""
import asyncio
import os
import sys

# 设置Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_integration():
    """测试集成"""
    print("🧪 集成测试")
    print("=" * 60)
    
    # 1. 测试导入
    print("1. 🔍 测试模块导入...")
    try:
        from llm_parser.base_parser import BaseLLMParser
        from model_service.llm_parser.deepseek_parser_0203 import DeepSeekParser
        from llm_parser.factory import LLMParserFactory
        from services.event_extractor import AIEventExtractor
        print("✅ 所有模块导入成功!")
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    
    # 2. 测试API连接
    print("\n2. 🔌 测试API连接...")
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("❌ DEEPSEEK_API_KEY 未设置，无法执行真实集成测试")
        return False
    
    # 3. 测试事件提取
    print("\n3. 📰 测试事件提取...")
    try:
        extractor = AIEventExtractor()
        print("🤖 使用AI提取器")
        
        # 测试新闻
        test_news = {
            'news_id': 'test_integration_001',
            'title': '人工智能大会召开，多家公司发布AI新品',
            'content': '2024年人工智能产业大会在北京召开，华为、百度、阿里等公司发布最新AI产品。',
            'source': '测试',
            'publish_time': '2024-01-15 10:00:00'
        }
        
        print(f"   新闻标题: {test_news['title']}")
        print("   ⏳ 提取中...")
        
        event_data = await extractor.extract_event(test_news)
        
        if event_data:
            print("✅ 事件提取成功!")
            print(f"   事件类型: {event_data.get('event_type')}")
            print(f"   影响方向: {event_data.get('direction')}")
            print(f"   置信度: {event_data.get('confidence')}")
            print(f"   摘要: {event_data.get('summary')}")
        else:
            print("❌ 事件提取失败")
        
        # 关闭提取器
        await extractor.close()
        
    except Exception as e:
        print(f"💥 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = asyncio.run(test_integration())
    print("\n" + "=" * 60)
    if success:
        print("🎉 集成测试成功!")
        print("可以运行: python run_news_event.py --once --verbose --limit 1")
    else:
        print("❌ 集成测试失败")
        print("请检查错误信息")
    print("=" * 60)

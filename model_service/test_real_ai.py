#!/usr/bin/env python3
"""
测试真实AI模型解析
"""
import asyncio
import os
from database import DatabaseManager
from services.event_extractor import AIEventExtractor

async def test_single_news():
    """测试单条新闻的AI解析"""
    print("🧪 测试真实AI模型解析...")
    
    # 获取一条未处理的新闻
    news_list = await DatabaseManager.fetch_pending_news(limit=1)
    
    if not news_list:
        print("📭 没有待处理的新闻")
        return
    
    news_item = news_list[0]
    print(f"📰 测试新闻: {news_item['news_id'][:20]}...")
    print(f"   标题: {news_item['title'][:50]}...")
    
    # 初始化AI提取器
    extractor = AIEventExtractor()
    
    try:
        # 解析新闻
        print("🤖 AI解析中...")
        event_data = await extractor.extract_event(news_item)
        
        if event_data:
            print("✅ AI解析成功!")
            print(f"   事件类型: {event_data.get('event_type')}")
            print(f"   影响行业: {event_data.get('impact_industries')}")
            print(f"   方向: {event_data.get('direction')}")
            print(f"   置信度: {event_data.get('confidence')}")
            print(f"   摘要: {event_data.get('summary')}")
            
            # 保存到数据库
            success = await DatabaseManager.save_event(event_data)
            if success:
                print("💾 事件保存成功!")
            else:
                print("❌ 事件保存失败")
        else:
            print("❌ AI解析失败")
            
    except Exception as e:
        print(f"💥 测试失败: {e}")
    finally:
        await extractor.close()

if __name__ == "__main__":
    # 检查API密钥
    if not os.getenv('DEEPSEEK_API_KEY') and not os.getenv('OPENAI_API_KEY'):
        print("⚠️  请先设置API密钥:")
        print("   export DEEPSEEK_API_KEY='your_key'")
        print("   或 export OPENAI_API_KEY='your_key'")
        exit(1)
    
    asyncio.run(test_single_news())

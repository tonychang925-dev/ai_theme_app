#!/usr/bin/env python3
"""
更新news_crawler_service以触发model_service
"""
import os

# 在news_crawler_service/database.py中添加的代码
trigger_code = '''
async def _trigger_event_extraction(cls, news_items: List[NewsRawItem]):
    """触发事件抽取服务"""
    try:
        import aiohttp
        
        # 准备数据
        news_data = [
            {
                "news_id": item.news_id,
                "title": item.title,
                "content": item.content,
                "source": item.source,
                "publish_date": item.publish_date.isoformat()
            }
            for item in news_items
        ]
        
        # 调用model_service
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={"news_list": news_data},
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 事件抽取触发成功: {{result.get('message')}}")
                else:
                    print(f"⚠️ 事件抽取触发失败: {{response.status}}")
                    
    except Exception as e:
        print(f"❌ 触发事件抽取异常: {{e}}")

# 在save_news_batch方法调用后触发
async def save_news_batch_and_trigger(cls, news_items: List[NewsRawItem]):
    saved_count = await cls.save_news_batch(news_items)
    
    if saved_count > 0:
        # 异步触发，不阻塞
        asyncio.create_task(cls._trigger_event_extraction(news_items))
    
    return saved_count
'''

print("请手动将以下代码添加到 news_crawler_service/database.py 中:")
print("=" * 60)
print(trigger_code)
print("=" * 60)
print("\n添加位置建议:")
print("1. 在 DatabaseManager 类中添加 _trigger_event_extraction 方法")
print("2. 添加 save_news_batch_and_trigger 方法作为增强版保存")
print("3. 或者修改现有的 save_news_batch 方法末尾添加触发逻辑")

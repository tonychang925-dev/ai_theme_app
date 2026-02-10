#!/usr/bin/env python3
"""
更新news_crawler_service/database.py，添加model_service触发逻辑
"""
import re

# 要添加的代码
trigger_code = '''
async def _trigger_event_extraction(self, news_items):
    """触发事件抽取服务"""
    try:
        import aiohttp
        import asyncio
        
        print(f"📤 触发事件抽取: {{len(news_items)}} 条新闻")
        
        # 准备数据
        news_data = [
            {{
                "news_id": item.news_id,
                "title": item.title,
                "content": item.content,
                "source": item.source,
                "publish_date": item.publish_date.isoformat() if hasattr(item.publish_date, "isoformat") else str(item.publish_date)
            }}
            for item in news_items
        ]
        
        # 调用model_service
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={{"news_list": news_data}},
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 事件抽取触发成功: {{result.get('message')}}")
                else:
                    print(f"⚠️ 事件抽取触发失败: {{response.status}}")
                    
    except Exception as e:
        print(f"❌ 触发事件抽取异常: {{e}}")

async def save_news_batch_with_trigger(self, news_items):
    """保存新闻并触发事件抽取"""
    saved_count = await self.save_news_batch(news_items)
    
    if saved_count > 0:
        # 异步触发，不阻塞当前操作
        asyncio.create_task(self._trigger_event_extraction(news_items))
    
    return saved_count
'''

# 读取原文件
with open('news_crawler_service/database.py', 'r') as f:
    content = f.read()

# 在DatabaseManager类中添加方法
# 找到class DatabaseManager:的定义
class_pattern = r'class DatabaseManager:'

if re.search(class_pattern, content):
    # 在类的初始化方法后添加新方法
    modified_content = re.sub(
        r'(class DatabaseManager:.*?)(?=\n\n|\Z)',
        r'\1\n' + trigger_code,
        content,
        flags=re.DOTALL
    )
    
    # 写入更新后的文件
    with open('news_crawler_service/database.py', 'w') as f:
        f.write(modified_content)
    
    print("✅ 成功更新 news_crawler_service/database.py")
    print("   添加了 _trigger_event_extraction 和 save_news_batch_with_trigger 方法")
else:
    print("❌ 未找到 DatabaseManager 类")

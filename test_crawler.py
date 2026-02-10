import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from news_crawler_service.collectors.akshare_cls import AkshareClsCollector
from news_crawler_service.database import init_database, DatabaseManager

async def main():
    # 1. 初始化数据库
    await init_database()
    
    # 2. 创建采集器
    collector = AkshareClsCollector()
    
    # 3. 执行采集
    print("开始采集财联社新闻...")
    news_items = await collector.fetch()
    
    # 4. 保存到数据库
    if news_items:
        saved = await DatabaseManager.save_news_batch(news_items)
        print(f"采集完成: 共{len(news_items)}条，成功保存{saved}条")
        
        # 5. 验证数据
        recent = await DatabaseManager.get_recent_news(5)
        print("最近5条新闻:", recent)
    else:
        print("未采集到新闻")

if __name__ == "__main__":
    asyncio.run(main())